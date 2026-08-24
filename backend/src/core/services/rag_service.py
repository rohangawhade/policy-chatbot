"""Retrieval-augmented generation orchestration (files/plan.md's
`core/services/rag_service.py` — the single file Steps 6.3-6.6 build up
incrementally, rather than one file per step, per the plan's own folder
structure listing this as "Retrieval + generation orchestration").

This step (6.3) adds retrieval: a cache check that can skip retrieval
entirely, query embedding, tenant-scoped Pinecone search, and enrollment
lookup for personal-sounding questions. Steps 6.4/6.5/6.6 will extend
this same class with prompt assembly, streaming generation, and
conversation memory.
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
    """

    def __init__(
        self,
        llm: LLMPort,
        cache: CachePort,
        vector_store: VectorStorePort,
        enrollment_repository: EnrollmentRepository,
        embedding_model: str,
        top_k: int = _DEFAULT_TOP_K,
    ) -> None:
        self._llm = llm
        self._cache = cache
        self._vector_store = vector_store
        self._enrollment_repository = enrollment_repository
        self._embedding_model = embedding_model
        self._top_k = top_k

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
