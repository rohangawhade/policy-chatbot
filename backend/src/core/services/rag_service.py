"""Retrieval-augmented generation orchestration (files/plan.md's
`core/services/rag_service.py` — the single file Steps 6.3-6.6 build up
incrementally, rather than one file per step, per the plan's own folder
structure listing this as "Retrieval + generation orchestration").

Step 6.3 added retrieval: a cache check that can skip retrieval
entirely, query embedding, tenant-scoped Pinecone search, and enrollment
lookup for personal-sounding questions. This step (6.4) adds prompt
assembly. Steps 6.5/6.6 will extend this same class with streaming
generation and conversation memory.
"""

import hashlib
from dataclasses import dataclass, field
from uuid import UUID

from core.domain.policy import Enrollment, PolicyType
from core.ports.cache_port import CachePort
from core.ports.llm_port import LLMPort
from core.ports.repository_ports import EnrollmentRepository
from core.ports.vector_store_port import VectorMatch, VectorStorePort

_DEFAULT_TOP_K = 5
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


class RAGService:
    """Retrieval-augmented generation orchestration.

    Attributes:
        llm: Used for `embed()` in this step; Step 6.5 will also use it
            for `generate_stream()`.
        cache: Response cache — checked before any retrieval work, so an
            identical recent query never re-embeds or re-searches.
        vector_store: One Pinecone namespace per employer
            (files/plan.md's tenant isolation strategy).
        enrollment_repository: Enrollment lookup for personal questions.
        embedding_model: Passed to every `embed()` call — this class has
            no opinion on which embedding model is configured.
        top_k: Chunks retrieved per query.
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
        embedding_model: str,
        top_k: int = _DEFAULT_TOP_K,
        prompt_template: PromptTemplate | None = None,
    ) -> None:
        self._llm = llm
        self._cache = cache
        self._vector_store = vector_store
        self._enrollment_repository = enrollment_repository
        self._embedding_model = embedding_model
        self._top_k = top_k
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
