"""Retrieval-augmented generation orchestration (files/plan.md's
`core/services/rag_service.py` — the single file Steps 6.3-6.6 build up
incrementally, rather than one file per step, per the plan's own folder
structure listing this as "Retrieval + generation orchestration").

Step 6.3 added retrieval: a cache check that can skip retrieval
entirely, query embedding, tenant-scoped Pinecone search, and enrollment
lookup for personal-sounding questions. Step 6.4 added prompt assembly.
This step (6.5) adds streaming generation. Step 6.6 will extend this
same class with conversation memory.
"""

import hashlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

from core.domain.analytics import LLMCostLog, RequestLatencyLog
from core.domain.policy import Enrollment, PolicyType
from core.ports.cache_port import CachePort
from core.ports.llm_port import LLMPort
from core.ports.repository_ports import AnalyticsRepository, EnrollmentRepository
from core.ports.vector_store_port import VectorMatch, VectorStorePort
from core.services.query_router import QueryRouter

_DEFAULT_TOP_K = 5
_DEFAULT_CACHE_TTL_SECONDS = 3600
_DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.5
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
        self, query_text: str, chunks: list[VectorMatch], enrollment: list[Enrollment]
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
            configured threshold. **Not acted on by this class** — Step
            6.6 will use this to persist a `FlaggedResponse` once it has
            a `message_id` to attach it to; `FlaggedResponse` requires
            `conversation_id`/`message_id`, which don't exist until
            Step 6.6 builds conversation memory, so this step can only
            compute and expose the signal, not act on it.
        from_cache: True if this was a cache hit — no LLM call was made,
            nothing was logged to `LLMCostLog`/`RequestLatencyLog`.
    """

    full_text: str
    model: str
    model_tier: str
    complexity_score: float
    top_similarity_score: float | None
    is_low_confidence: bool
    from_cache: bool


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
        employer_id: UUID,
        retrieval: RetrievalResult,
        retrieval_ms: int,
    ) -> None:
        self._service = service
        self._query_text = query_text
        self._employer_id = employer_id
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
        self.metrics = GenerationMetrics(
            full_text=cached_response,
            model="",
            model_tier="",
            complexity_score=0.0,
            top_similarity_score=None,
            is_low_confidence=False,
            from_cache=True,
        )

    async def _stream_generation(self) -> AsyncIterator[str]:
        service = self._service
        retrieval = self._retrieval

        complexity_score = service._query_router.score_complexity(self._query_text)
        model = service._query_router.select_model(complexity_score)
        prompt = service.assemble_prompt(self._query_text, retrieval)

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
        await service._cache_response(self._employer_id, self._query_text, full_text)
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

        top_score = max((chunk.score for chunk in retrieval.chunks), default=None)
        is_low_confidence = top_score is not None and top_score < service._low_confidence_threshold
        self.metrics = GenerationMetrics(
            full_text=full_text,
            model=model,
            model_tier=model_tier,
            complexity_score=complexity_score,
            top_similarity_score=top_score,
            is_low_confidence=is_low_confidence,
            from_cache=False,
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
        analytics_repository: Where `LLMCostLog`/`RequestLatencyLog` are
            recorded after a generation completes (see `query()`'s
            docstring for why this happens as a direct write here,
            unlike Step 6.1's `GuardrailsService`).
        query_router: Selects the model tier for a fresh generation.
        embedding_model: Passed to every `embed()` call — this class has
            no opinion on which embedding model is configured.
        top_k: Chunks retrieved per query.
        cache_ttl_seconds: How long a fresh response stays cached.
        low_confidence_threshold: `GenerationMetrics.is_low_confidence`
            is True when the top retrieved chunk's score is below this
            (files/coding-standards.md section 12's stated default: 0.5).
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
        embedding_model: str,
        top_k: int = _DEFAULT_TOP_K,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
        low_confidence_threshold: float = _DEFAULT_LOW_CONFIDENCE_THRESHOLD,
        prompt_template: PromptTemplate | None = None,
    ) -> None:
        self._llm = llm
        self._cache = cache
        self._vector_store = vector_store
        self._enrollment_repository = enrollment_repository
        self._analytics_repository = analytics_repository
        self._query_router = query_router
        self._embedding_model = embedding_model
        self._top_k = top_k
        self._cache_ttl_seconds = cache_ttl_seconds
        self._low_confidence_threshold = low_confidence_threshold
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
        cache_key = self._cache_key(employer_id, query_text)
        cached_response = await self._cache.get(cache_key)
        if cached_response is not None:
            return RetrievalResult(cached_response=cached_response)

        embeddings = await self._llm.embed([query_text], model=self._embedding_model)
        policy_type = self._detect_policy_type(query_text)
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

        return RetrievalResult(chunks=chunks, enrollment=enrollment)

    def assemble_prompt(self, query_text: str, retrieval: RetrievalResult) -> str:
        """Render the full generation prompt from a `retrieve()` result.

        Callers should check `retrieval.cached_response` first — this
        method doesn't guard against a cache hit itself (there's nothing
        to assemble a prompt from on one; `chunks`/`enrollment` are
        always empty).
        """
        return self._prompt_template.render(query_text, retrieval.chunks, retrieval.enrollment)

    async def query(
        self, query_text: str, employee_id: UUID, employer_id: UUID
    ) -> GenerationStream:
        """Retrieve context, then stream a generated (or cached) response.

        Returns a `GenerationStream` — `async for token in stream` for
        response tokens as they arrive; once that loop ends,
        `stream.metrics` holds the completed generation's cost/latency/
        confidence data.

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
        with the rule's actual intent.

        **Known scope boundary**: does not persist a `FlaggedResponse`
        for a low-confidence response, or publish
        `ChatResponseGeneratedEvent`/`LowConfidenceResponseEvent` — both
        require a `conversation_id`/`message_id` that don't exist until
        Step 6.6 builds conversation memory.
        `GenerationMetrics.is_low_confidence` is returned so a Step 6.6
        caller (which will have a `message_id`) can act on it then.
        """
        retrieval_start = time.monotonic()
        retrieval = await self.retrieve(query_text, employee_id, employer_id)
        retrieval_ms = int((time.monotonic() - retrieval_start) * 1000)
        return GenerationStream(self, query_text, employer_id, retrieval, retrieval_ms)

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

    async def _cache_response(self, employer_id: UUID, query_text: str, full_text: str) -> None:
        cache_key = self._cache_key(employer_id, query_text)
        await self._cache.set(cache_key, full_text, ttl_seconds=self._cache_ttl_seconds)

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

    def _cache_key(self, employer_id: UUID, query_text: str) -> str:
        """Hash of `(employer_id, query_text)`.

        Deliberately without a model tier, unlike Step 3.4's original
        "employer_id + query_text + model_tier" cache-key formula:
        files/plan.md's own Query Flow diagram orders the cache check
        *before* Step 6.2's `QueryRouter` runs, so the tier isn't known
        yet at this point — and a cached answer is valid regardless of
        which tier originally produced it.
        """
        digest = hashlib.sha256(f"{employer_id}:{query_text}".encode()).hexdigest()
        return f"rag_response:{digest}"

    def _detect_policy_type(self, query_text: str) -> PolicyType | None:
        lowered = query_text.lower()
        for policy_type in PolicyType:
            if policy_type.value in lowered:
                return policy_type
        return None

    def _is_personal_query(self, query_text: str) -> bool:
        words = {word.strip(".,!?'\"") for word in query_text.lower().split()}
        return bool(words & _PERSONAL_PRONOUNS)
