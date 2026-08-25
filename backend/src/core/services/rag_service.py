"""Retrieval-augmented generation orchestration (files/plan.md's
`core/services/rag_service.py` — the single file Steps 6.3-6.6 build up
incrementally, rather than one file per step, per the plan's own folder
structure listing this as "Retrieval + generation orchestration").

Step 6.3 added retrieval: a cache check that can skip retrieval
entirely, query embedding, tenant-scoped Pinecone search, and enrollment
lookup for personal-sounding questions. Step 6.4 added prompt assembly.
Step 6.5 added streaming generation. This step (6.6) adds conversation
memory — the last incremental piece of this file.
"""

import hashlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

from core.domain.analytics import FlaggedResponse, LLMCostLog, RequestLatencyLog
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.events import (
    ChatMessageReceivedEvent,
    ChatResponseGeneratedEvent,
    LowConfidenceResponseEvent,
)
from core.domain.policy import Enrollment, PolicyType
from core.ports.cache_port import CachePort
from core.ports.event_bus_port import EventBusPort
from core.ports.llm_port import LLMPort
from core.ports.repository_ports import (
    AnalyticsRepository,
    ConversationRepository,
    DocumentRepository,
    EnrollmentRepository,
    MessageRepository,
)
from core.ports.vector_store_port import VectorMatch, VectorStorePort
from core.services.query_router import QueryRouter

_DEFAULT_TOP_K = 5
_DEFAULT_CACHE_TTL_SECONDS = 3600
_DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.5
_DEFAULT_HISTORY_LIMIT = 20
_LOW_CONFIDENCE_FLAG_REASON = "low_retrieval_confidence"
_PERSONAL_PRONOUNS = frozenset({"my", "i", "me", "i'm", "i've", "mine", "myself"})

_ROLE_DEFINITION = (
    "You are PolicyPal, a benefits assistant for this employee's employer. You "
    "help employees understand their health, dental, vision, life, and "
    "disability benefits."
)
_DOMAIN_RESTRICTION = (
    "Answer using ONLY the retrieved policy excerpts and enrollment information "
    "below. Never invent or assume information that isn't explicitly stated in "
    "the provided context — if the context doesn't contain enough information "
    "to answer confidently, say so directly instead of guessing. Always cite "
    "which document and section your answer is drawn from."
)
_NO_CONTEXT_NOTICE = (
    "No relevant policy excerpts were found for this question. Say so plainly "
    "and suggest the employee rephrase or contact HR, rather than guessing."
)


@dataclass(frozen=True, kw_only=True)
class RetrievalResult:
    """Either a cached final response (retrieval/generation can be
    skipped entirely) or the context available to write a fresh one.

    Attributes:
        cached_response: A previously-generated answer for this exact
            query, or `None` on a cache miss.
        chunks: Retrieved document chunks — always empty on a cache hit.
        enrollment: The employee's enrollments, only fetched for a
            personal-sounding query; empty otherwise or on a cache hit.
    """

    cached_response: str | None = None
    chunks: list[VectorMatch] = field(default_factory=list)
    enrollment: list[Enrollment] = field(default_factory=list)
    policy_type: PolicyType | None = None


@dataclass(frozen=True, kw_only=True)
class PromptTemplate:
    """Named slots for the RAG prompt (files/plan.md Step 6.4) — iterate
    on wording here without touching `RAGService`'s orchestration logic.

    `LLMPort.generate`/`generate_stream` take a single `prompt: str`
    (files/coding-standards.md's port has no separate system/user
    message split), so `render()` assembles everything — role,
    restrictions, context, question — into one string.

    Attributes:
        role_definition: Who the assistant is and its scope.
        domain_restriction: Off-topic/no-hallucination/cite-sources rules.
        no_context_notice: Shown instead of retrieved excerpts when
            nothing relevant was found, so the model says so plainly
            rather than answering from nowhere.
    """

    role_definition: str = _ROLE_DEFINITION
    domain_restriction: str = _DOMAIN_RESTRICTION
    no_context_notice: str = _NO_CONTEXT_NOTICE

    def render(
        self,
        query_text: str,
        chunks: list[VectorMatch],
        enrollment: list[Enrollment],
        history: list[Message] | None = None,
    ) -> str:
        sections = [self.role_definition, "", self.domain_restriction]

        sections.append("")
        if chunks:
            sections.append("Retrieved policy excerpts:")
            sections.extend(self._format_chunk(chunk) for chunk in chunks)
        else:
            sections.append(self.no_context_notice)

        if enrollment:
            sections.append("")
            sections.append("Employee's current enrollments:")
            sections.extend(self._format_enrollment(record) for record in enrollment)

        if history:
            sections.append("")
            sections.append("Conversation so far:")
            sections.extend(self._format_history_message(message) for message in history)

        sections.append("")
        sections.append(f"Employee's question: {query_text}")

        return "\n".join(sections)

    def _format_chunk(self, chunk: VectorMatch) -> str:
        title = chunk.metadata.get("document_title", "an unknown document")
        section = chunk.metadata.get("section_title")
        text = chunk.metadata.get("text", "")
        source = f"{title}, {section}" if section else str(title)
        return f"- [Source: {source}] {text}"

    def _format_enrollment(self, enrollment: Enrollment) -> str:
        # Enrollment only carries a policy_id, not the policy's name/type —
        # a PolicyRepository join to show a human-readable policy name is a
        # reasonable future improvement, not required for this step.
        status = "active" if enrollment.is_active else "inactive"
        enrolled_date = enrollment.enrolled_at.date()
        return f"- Policy {enrollment.policy_id} — {status}, enrolled {enrolled_date}"

    def _format_history_message(self, message: Message) -> str:
        speaker = "Employee" if message.role == MessageRole.USER else "Assistant"
        return f"{speaker}: {message.content}"


@dataclass(frozen=True, kw_only=True)
class GenerationMetrics:
    """Everything about a completed generation a caller can act on —
    available via `GenerationStream.metrics` only after its tokens are
    fully consumed (`LLMPort.generate_stream()` only becomes fully known
    — total tokens, full text — once exhausted, not as it streams).

    Attributes:
        full_text: The complete response, including any appended source
            citations — exactly what was cached.
        model: The model actually used (`""` on a cache hit).
        model_tier: `"cheap"` or `"powerful"` (`""` on a cache hit).
        complexity_score: `QueryRouter.score_complexity()`'s result
            (`0.0` on a cache hit — routing never ran).
        top_similarity_score: The highest-scoring retrieved chunk's
            score, or `None` if no chunks were retrieved (including on
            a cache hit).
        is_low_confidence: True if `top_similarity_score` is below the
            configured threshold — when True, a `FlaggedResponse` has
            already been persisted and a `LowConfidenceResponseEvent`
            published (Step 6.6; Step 6.5 could only compute this signal,
            not act on it, since `FlaggedResponse` needs the
            `conversation_id`/`message_id` this step now provides).
        from_cache: True if this was a cache hit — no LLM call was made,
            nothing was logged to `LLMCostLog`/`RequestLatencyLog`.
        conversation_id: The conversation this turn was recorded in
            (newly created if the caller didn't pass one to `query()`).
        message_id: The persisted assistant `Message`'s id.
    """

    full_text: str
    model: str
    model_tier: str
    complexity_score: float
    top_similarity_score: float | None
    is_low_confidence: bool
    from_cache: bool
    conversation_id: UUID
    message_id: UUID


class GenerationStream:
    """An async-iterable stream of response tokens from
    `RAGService.query()`.

    Iterate with `async for token in stream`. After the stream is fully
    consumed, `stream.metrics` holds the completed generation's cost/
    latency/confidence data — `None` before that point, since
    `generate_stream()` doesn't expose totals until it finishes.
    """

    def __init__(
        self,
        service: "RAGService",
        query_text: str,
        employee_id: UUID,
        employer_id: UUID,
        conversation_id: UUID | None,
        history: list[Message],
        retrieval: RetrievalResult,
        retrieval_ms: int,
    ) -> None:
        self._service = service
        self._query_text = query_text
        self._employee_id = employee_id
        self._employer_id = employer_id
        self._conversation_id = conversation_id
        self._history = history
        self._retrieval = retrieval
        self._retrieval_ms = retrieval_ms
        self.metrics: GenerationMetrics | None = None

    async def __aiter__(self) -> AsyncIterator[str]:
        if self._retrieval.cached_response is not None:
            async for token in self._stream_cached(self._retrieval.cached_response):
                yield token
            return
        async for token in self._stream_generation():
            yield token

    async def _stream_cached(self, cached_response: str) -> AsyncIterator[str]:
        yield cached_response
        conversation_id, message_id = await self._service._persist_turn(
            employee_id=self._employee_id,
            employer_id=self._employer_id,
            conversation_id=self._conversation_id,
            query_text=self._query_text,
            full_text=cached_response,
            model=None,
            policy_type=self._retrieval.policy_type,
        )
        self.metrics = GenerationMetrics(
            full_text=cached_response,
            model="",
            model_tier="",
            complexity_score=0.0,
            top_similarity_score=None,
            is_low_confidence=False,
            from_cache=True,
            conversation_id=conversation_id,
            message_id=message_id,
        )

    async def _stream_generation(self) -> AsyncIterator[str]:
        service = self._service
        retrieval = self._retrieval

        complexity_score = service._query_router.score_complexity(self._query_text)
        model = service._query_router.select_model(complexity_score)
        prompt = service.assemble_prompt(self._query_text, retrieval, self._history)

        llm_start = time.monotonic()
        pieces: list[str] = []
        async for token in service._llm.generate_stream(prompt, model=model):
            pieces.append(token)
            yield token
        llm_ms = int((time.monotonic() - llm_start) * 1000)

        citations = service._format_citations(retrieval.chunks)
        if citations:
            pieces.append(citations)
            yield citations

        full_text = "".join(pieces)
        model_tier = service._query_router.tier_for_model(model)
        await service._cache_response(
            self._employer_id, self._query_text, full_text, retrieval.policy_type
        )
        await service._log_generation(
            employer_id=self._employer_id,
            model=model,
            model_tier=model_tier,
            complexity_score=complexity_score,
            prompt=prompt,
            full_text=full_text,
            retrieval_ms=self._retrieval_ms,
            llm_ms=llm_ms,
        )

        conversation_id, message_id = await service._persist_turn(
            employee_id=self._employee_id,
            employer_id=self._employer_id,
            conversation_id=self._conversation_id,
            query_text=self._query_text,
            full_text=full_text,
            model=model,
            policy_type=retrieval.policy_type,
        )

        top_score = max((chunk.score for chunk in retrieval.chunks), default=None)
        is_low_confidence = top_score is not None and top_score < service._low_confidence_threshold
        await service._finalize_turn(
            employer_id=self._employer_id,
            conversation_id=conversation_id,
            message_id=message_id,
            model=model,
            query_text=self._query_text,
            policy_type=retrieval.policy_type,
            top_score=top_score,
            is_low_confidence=is_low_confidence,
        )

        self.metrics = GenerationMetrics(
            full_text=full_text,
            model=model,
            model_tier=model_tier,
            complexity_score=complexity_score,
            top_similarity_score=top_score,
            is_low_confidence=is_low_confidence,
            from_cache=False,
            conversation_id=conversation_id,
            message_id=message_id,
        )


class RAGService:
    """Retrieval-augmented generation orchestration.

    Attributes:
        llm: Used for `embed()`/`generate_stream()`/`estimate_cost()`.
        cache: Response cache — checked before any retrieval work, so an
            identical recent query never re-embeds, re-searches, or
            re-generates; also where a fresh response is cached once
            generated.
        vector_store: One Pinecone namespace per employer
            (files/plan.md's tenant isolation strategy).
        enrollment_repository: Enrollment lookup for personal questions.
        analytics_repository: Where `LLMCostLog`/`RequestLatencyLog`/
            `FlaggedResponse` are recorded (see `query()`'s docstring
            for why cost/latency happen as a direct write here, unlike
            Step 6.1's `GuardrailsService`).
        query_router: Selects the model tier for a fresh generation.
        conversation_repository: Creates a new `Conversation` when
            `query()` isn't given an existing `conversation_id`.
        message_repository: Persists each turn's user/assistant
            `Message` pair and loads history for follow-up questions.
        event_bus: Publishes `ChatMessageReceivedEvent`/
            `ChatResponseGeneratedEvent`/`LowConfidenceResponseEvent`.
        document_repository: `mark_queried()` is called on every
            retrieved chunk's source document (Step 9.6's document-health
            "zero query hits" signal) — this class never reads a
            `Document` row, only marks one as having been matched.
        embedding_model: Passed to every `embed()` call — this class has
            no opinion on which embedding model is configured.
        top_k: Chunks retrieved per query.
        cache_ttl_seconds: How long a fresh response stays cached.
        low_confidence_threshold: `GenerationMetrics.is_low_confidence`
            is True when the top retrieved chunk's score is below this
            (files/coding-standards.md section 12's stated default: 0.5).
        history_limit: Messages loaded from an existing conversation as
            context (`MessageRepository.list_by_conversation()`'s own
            default, Step 3.5).
        prompt_template: Defaults to a `PromptTemplate()` with the
            standard wording — override to A/B test or localize prompts
            without touching this class.
    """

    def __init__(
        self,
        llm: LLMPort,
        cache: CachePort,
        vector_store: VectorStorePort,
        enrollment_repository: EnrollmentRepository,
        analytics_repository: AnalyticsRepository,
        query_router: QueryRouter,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
        event_bus: EventBusPort,
        document_repository: DocumentRepository,
        embedding_model: str,
        top_k: int = _DEFAULT_TOP_K,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
        low_confidence_threshold: float = _DEFAULT_LOW_CONFIDENCE_THRESHOLD,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
        prompt_template: PromptTemplate | None = None,
    ) -> None:
        self._llm = llm
        self._cache = cache
        self._vector_store = vector_store
        self._enrollment_repository = enrollment_repository
        self._analytics_repository = analytics_repository
        self._query_router = query_router
        self._conversation_repository = conversation_repository
        self._message_repository = message_repository
        self._event_bus = event_bus
        self._document_repository = document_repository
        self._embedding_model = embedding_model
        self._top_k = top_k
        self._cache_ttl_seconds = cache_ttl_seconds
        self._low_confidence_threshold = low_confidence_threshold
        self._history_limit = history_limit
        self._prompt_template = prompt_template or PromptTemplate()

    async def retrieve(
        self, query_text: str, employee_id: UUID, employer_id: UUID
    ) -> RetrievalResult:
        """Check the cache, then search Pinecone and fetch enrollment if
        there's no cache hit.

        Args:
            query_text: The user's raw question.
            employee_id: Whose enrollment to fetch for a personal query.
            employer_id: Tenant scope for both the cache key and the
                Pinecone namespace — always the authenticated request's
                value (files/plan.md Step 5.3's `get_current_employer_id`),
                never a client-supplied value.
        """
        # Detected before the cache check (not after, as in Steps 6.3-6.6)
        # so it can be folded into the cache key itself — Step 7.3 needs
        # "invalidate every cached query for this employer + policy type"
        # to be a real, prefix-scannable operation, which requires
        # policy_type to be part of the key at both read and write time.
        policy_type = self._detect_policy_type(query_text)
        cache_key = self._cache_key(employer_id, query_text, policy_type)
        cached_response = await self._cache.get(cache_key)
        if cached_response is not None:
            return RetrievalResult(cached_response=cached_response, policy_type=policy_type)

        embeddings = await self._llm.embed([query_text], model=self._embedding_model)
        metadata_filter = {"policy_type": policy_type.value} if policy_type else None
        chunks = await self._vector_store.query(
            str(employer_id),
            embeddings[0],
            top_k=self._top_k,
            metadata_filter=metadata_filter,
        )

        enrollment: list[Enrollment] = []
        if self._is_personal_query(query_text):
            enrollment = await self._enrollment_repository.list_by_employee(employee_id)

        await self._mark_matched_documents_queried(chunks)

        return RetrievalResult(chunks=chunks, enrollment=enrollment, policy_type=policy_type)

    async def _mark_matched_documents_queried(self, chunks: list[VectorMatch]) -> None:
        document_ids: set[UUID] = set()
        for chunk in chunks:
            raw_id = chunk.metadata.get("document_id")
            if raw_id:
                document_ids.add(UUID(str(raw_id)))
        await self._document_repository.mark_queried(list(document_ids))

    def assemble_prompt(
        self,
        query_text: str,
        retrieval: RetrievalResult,
        history: list[Message] | None = None,
    ) -> str:
        """Render the full generation prompt from a `retrieve()` result.

        Callers should check `retrieval.cached_response` first — this
        method doesn't guard against a cache hit itself (there's nothing
        to assemble a prompt from on one; `chunks`/`enrollment` are
        always empty).

        Args:
            history: The conversation's last `history_limit` messages,
                oldest first (`MessageRepository.list_by_conversation()`'s
                order) — `None`/empty for a new conversation.
        """
        return self._prompt_template.render(
            query_text, retrieval.chunks, retrieval.enrollment, history
        )

    async def query(
        self,
        query_text: str,
        employee_id: UUID,
        employer_id: UUID,
        conversation_id: UUID | None = None,
    ) -> GenerationStream:
        """Retrieve context, then stream a generated (or cached) response.

        Returns a `GenerationStream` — `async for token in stream` for
        response tokens as they arrive; once that loop ends,
        `stream.metrics` holds the completed generation's cost/latency/
        confidence data, including the `conversation_id`/`message_id`
        this turn was recorded under.

        Args:
            conversation_id: An existing conversation to continue — its
                last `history_limit` messages become context, and this
                turn's message pair is appended to it. `None` starts a
                new conversation (including on a cache hit — a cached
                answer is still a real turn in the employee's history).

        **Direct-write exception to files/coding-standards.md section
        12's fire-and-forget-via-event-bus rule**: `LLMCostLog`/
        `RequestLatencyLog` are written directly to
        `analytics_repository` here, not published as events for a
        subscriber (unlike Step 6.1's `GuardrailsService`, which does
        follow that rule — no subscriber-registration infrastructure
        exists anywhere in the app yet, see that step's note). This
        write happens strictly *after* every token has already reached
        the caller (the `async for` loop over `generate_stream()` has
        finished), so it adds zero perceived latency to the user's
        response — the one case where a direct write doesn't conflict
        with the rule's actual intent. Conversation/message persistence
        and `FlaggedResponse`/event publishing (this step) are not
        subject to that exception — nothing about them needs the
        response to have finished streaming first, so they follow
        section 12's rule normally via the event bus, except for
        conversation/message rows themselves, which — like
        `LLMCostLog`/`RequestLatencyLog` — are core to the turn actually
        having happened, not observability data, so they're persisted
        directly (matching how `EmbeddingService`, Step 4.4, persists
        `DocumentChunk` rows directly rather than through an event).
        """
        retrieval_start = time.monotonic()
        retrieval = await self.retrieve(query_text, employee_id, employer_id)
        retrieval_ms = int((time.monotonic() - retrieval_start) * 1000)
        history = await self._load_history(conversation_id)
        return GenerationStream(
            self,
            query_text,
            employee_id,
            employer_id,
            conversation_id,
            history,
            retrieval,
            retrieval_ms,
        )

    async def _load_history(self, conversation_id: UUID | None) -> list[Message]:
        if conversation_id is None:
            return []
        return await self._message_repository.list_by_conversation(
            conversation_id, limit=self._history_limit
        )

    async def _persist_turn(
        self,
        *,
        employee_id: UUID,
        employer_id: UUID,
        conversation_id: UUID | None,
        query_text: str,
        full_text: str,
        model: str | None,
        policy_type: PolicyType | None,
    ) -> tuple[UUID, UUID]:
        """Ensure a conversation exists, persist the user/assistant
        message pair, publish `ChatMessageReceivedEvent`, and return
        `(conversation_id, assistant_message_id)`.
        """
        if conversation_id is None:
            conversation = await self._conversation_repository.create(
                Conversation(employee_id=employee_id, employer_id=employer_id)
            )
            conversation_id = conversation.id

        user_message = await self._message_repository.create(
            Message(
                conversation_id=conversation_id,
                employer_id=employer_id,
                role=MessageRole.USER,
                content=query_text,
                policy_type=policy_type,
            )
        )
        await self._event_bus.publish(
            ChatMessageReceivedEvent(
                conversation_id=conversation_id,
                employer_id=employer_id,
                employee_id=employee_id,
                message_id=user_message.id,
            )
        )

        assistant_message = await self._message_repository.create(
            Message(
                conversation_id=conversation_id,
                employer_id=employer_id,
                role=MessageRole.ASSISTANT,
                content=full_text,
                model_used=model,
            )
        )
        return conversation_id, assistant_message.id

    async def _finalize_turn(
        self,
        *,
        employer_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        model: str,
        query_text: str,
        policy_type: PolicyType | None,
        top_score: float | None,
        is_low_confidence: bool,
    ) -> None:
        """Publish `ChatResponseGeneratedEvent`, and — only when
        low-confidence — persist a `FlaggedResponse` and publish
        `LowConfidenceResponseEvent`. Only called for a fresh generation
        (a cache hit has no new `model` and was never re-scored)."""
        await self._event_bus.publish(
            ChatResponseGeneratedEvent(
                conversation_id=conversation_id,
                employer_id=employer_id,
                message_id=message_id,
                model_used=model,
            )
        )
        if not is_low_confidence:
            return

        await self._analytics_repository.record_flagged_response(
            FlaggedResponse(
                employer_id=employer_id,
                conversation_id=conversation_id,
                message_id=message_id,
                query_text=query_text,
                top_similarity_score=top_score,
                flag_reason=_LOW_CONFIDENCE_FLAG_REASON,
                policy_type=policy_type,
            )
        )
        await self._event_bus.publish(
            LowConfidenceResponseEvent(
                conversation_id=conversation_id,
                employer_id=employer_id,
                message_id=message_id,
                top_similarity_score=top_score if top_score is not None else 0.0,
            )
        )

    def _format_citations(self, chunks: list[VectorMatch]) -> str:
        sources: list[str] = []
        for chunk in chunks:
            title = chunk.metadata.get("document_title")
            if not title or title in sources:
                continue
            sources.append(str(title))
        if not sources:
            return ""
        return "\n\nSources: " + "; ".join(sources)

    async def _cache_response(
        self,
        employer_id: UUID,
        query_text: str,
        full_text: str,
        policy_type: PolicyType | None,
    ) -> None:
        cache_key = self._cache_key(employer_id, query_text, policy_type)
        await self._cache.set(cache_key, full_text, ttl_seconds=self._cache_ttl_seconds)

    async def invalidate_version_cache(
        self, employer_id: UUID, policy_type: PolicyType | None
    ) -> None:
        """Purge every cached response for `employer_id` + `policy_type`
        (files/plan.md Step 7.3) — call this whenever a document version
        changes, so a stale cached answer built from the old version
        can't outlive the document it was generated from.

        `policy_type=None` invalidates only queries that didn't detect a
        policy type (a document without one, e.g. a general handbook) —
        it does **not** mean "invalidate everything for this employer".
        A caller invalidating several policy types calls this once per
        type.
        """
        await self._cache.delete_by_prefix(self._cache_key_prefix(employer_id, policy_type))

    async def _log_generation(
        self,
        *,
        employer_id: UUID,
        model: str,
        model_tier: str,
        complexity_score: float,
        prompt: str,
        full_text: str,
        retrieval_ms: int,
        llm_ms: int,
    ) -> None:
        usage = await self._llm.estimate_cost(model, prompt, full_text)
        await self._analytics_repository.record_llm_cost(
            LLMCostLog(
                employer_id=employer_id,
                model=model,
                model_tier=model_tier,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost_usd=usage.estimated_cost_usd,
                query_complexity_score=complexity_score,
            )
        )
        await self._analytics_repository.record_latency(
            RequestLatencyLog(
                employer_id=employer_id,
                total_ms=retrieval_ms + llm_ms,
                retrieval_ms=retrieval_ms,
                llm_ms=llm_ms,
                model_tier=model_tier,
            )
        )

    def _cache_key_prefix(self, employer_id: UUID, policy_type: PolicyType | None) -> str:
        """The employer + policy-type-scoped portion of a cache key,
        shared by `_cache_key()` (appends a query hash) and
        `invalidate_version_cache()` (Step 7.3 — deletes every key
        starting with this prefix). Deriving both from one method is
        what guarantees a write and a later bulk-invalidate can never
        drift apart.
        """
        policy_type_segment = policy_type.value if policy_type is not None else "none"
        return f"rag_response:{employer_id}:{policy_type_segment}:"

    def _cache_key(
        self, employer_id: UUID, query_text: str, policy_type: PolicyType | None = None
    ) -> str:
        """`(employer_id, policy_type)` prefix (see `_cache_key_prefix`)
        plus a hash of the query text.

        Deliberately without a model tier, unlike Step 3.4's original
        "employer_id + query_text + model_tier" cache-key formula:
        files/plan.md's own Query Flow diagram orders the cache check
        *before* Step 6.2's `QueryRouter` runs, so the tier isn't known
        yet at this point — and a cached answer is valid regardless of
        which tier originally produced it.

        `policy_type` is embedded as a literal segment rather than
        folded into the hash (Step 7.3) so that "every cached query for
        this employer + policy type" is a real, prefix-scannable key
        space — a pure hash of `(employer_id, query_text)` couldn't be
        bulk-invalidated without enumerating every key in the store.
        """
        digest = hashlib.sha256(f"{employer_id}:{query_text}".encode()).hexdigest()
        return f"{self._cache_key_prefix(employer_id, policy_type)}{digest}"

    def _detect_policy_type(self, query_text: str) -> PolicyType | None:
        lowered = query_text.lower()
        for policy_type in PolicyType:
            if policy_type.value in lowered:
                return policy_type
        return None

    def _is_personal_query(self, query_text: str) -> bool:
        words = {word.strip(".,!?'\"") for word in query_text.lower().split()}
        return bool(words & _PERSONAL_PRONOUNS)
