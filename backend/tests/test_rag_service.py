from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from core.domain.policy import Enrollment
from core.ports.cache_port import CachePort
from core.ports.llm_port import LLMPort
from core.ports.repository_ports import EnrollmentRepository
from core.ports.vector_store_port import VectorMatch, VectorStorePort
from core.services.rag_service import PromptTemplate, RAGService, RetrievalResult

_MODEL = "mock-embedding-model"


class FakeLLM(LLMPort):
    def __init__(self) -> None:
        self.embed_calls: list[tuple[list[str], str]] = []

    async def generate(
        self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
    ) -> str:
        raise NotImplementedError

    async def generate_stream(
        self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
    ) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""  # pragma: no cover

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        self.embed_calls.append((texts, model))
        return [[1.0, 0.0] for _ in texts]


class FakeCache(CachePort):
    def __init__(self, stored: dict[str, str] | None = None) -> None:
        self._stored = stored or {}
        self.get_calls: list[str] = []

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self._stored.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        raise NotImplementedError


class FakeVectorStore(VectorStorePort):
    def __init__(self, matches: list[VectorMatch] | None = None) -> None:
        self._matches = matches or []
        self.query_calls: list[tuple[str, list[float], int, dict[str, Any] | None]] = []

    async def upsert(self, namespace: str, records: list[Any]) -> None:
        raise NotImplementedError

    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        self.query_calls.append((namespace, vector, top_k, metadata_filter))
        return self._matches

    async def delete_by_metadata(self, namespace: str, metadata_filter: dict[str, Any]) -> None:
        raise NotImplementedError


class FakeEnrollmentRepository(EnrollmentRepository):
    def __init__(self, enrollments: list[Enrollment] | None = None) -> None:
        self._enrollments = enrollments or []
        self.list_by_employee_calls: list[UUID] = []

    async def get(self, entity_id: UUID) -> Enrollment | None:
        raise NotImplementedError

    async def create(self, entity: Enrollment) -> Enrollment:
        raise NotImplementedError

    async def update(self, entity: Enrollment) -> Enrollment:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employee(self, employee_id: UUID) -> list[Enrollment]:
        self.list_by_employee_calls.append(employee_id)
        return self._enrollments

    async def list_by_policy(self, policy_id: UUID) -> list[Enrollment]:
        raise NotImplementedError


def _service(
    llm: FakeLLM,
    cache: FakeCache,
    vector_store: FakeVectorStore,
    enrollment_repository: FakeEnrollmentRepository,
    top_k: int = 5,
) -> RAGService:
    return RAGService(
        llm, cache, vector_store, enrollment_repository, embedding_model=_MODEL, top_k=top_k
    )


async def test_cache_hit_short_circuits_before_any_retrieval_work() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm, vector_store, enrollment_repo = FakeLLM(), FakeVectorStore(), FakeEnrollmentRepository()
    service = _service(llm, FakeCache(), vector_store, enrollment_repo)
    cache_key = service._cache_key(employer_id, "What's my deductible?")
    service = _service(llm, FakeCache({cache_key: "cached answer"}), vector_store, enrollment_repo)

    result = await service.retrieve("What's my deductible?", employee_id, employer_id)

    assert result.cached_response == "cached answer"
    assert result.chunks == []
    assert result.enrollment == []
    assert llm.embed_calls == []
    assert vector_store.query_calls == []
    assert enrollment_repo.list_by_employee_calls == []


async def test_cache_miss_embeds_and_searches_pinecone() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    match = VectorMatch(id="chunk-1", score=0.9, metadata={})
    llm, vector_store = FakeLLM(), FakeVectorStore([match])
    service = _service(llm, FakeCache(), vector_store, FakeEnrollmentRepository())

    result = await service.retrieve("What is generally covered?", employee_id, employer_id)

    assert result.cached_response is None
    assert result.chunks == [match]
    assert llm.embed_calls == [(["What is generally covered?"], _MODEL)]
    assert len(vector_store.query_calls) == 1
    namespace, _vector, top_k, metadata_filter = vector_store.query_calls[0]
    assert namespace == str(employer_id)
    assert top_k == 5
    assert metadata_filter is None


async def test_detected_policy_type_becomes_a_metadata_filter() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    vector_store = FakeVectorStore()
    service = _service(FakeLLM(), FakeCache(), vector_store, FakeEnrollmentRepository())

    await service.retrieve("What's my dental deductible?", employee_id, employer_id)

    _namespace, _vector, _top_k, metadata_filter = vector_store.query_calls[0]
    assert metadata_filter == {"policy_type": "dental"}


async def test_custom_top_k_is_passed_to_the_vector_store() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    vector_store = FakeVectorStore()
    service = _service(FakeLLM(), FakeCache(), vector_store, FakeEnrollmentRepository(), top_k=10)

    await service.retrieve("What is covered?", employee_id, employer_id)

    assert vector_store.query_calls[0][2] == 10


async def test_personal_query_fetches_enrollment() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    enrollment = Enrollment(employee_id=employee_id, policy_id=uuid4())
    enrollment_repo = FakeEnrollmentRepository([enrollment])
    service = _service(FakeLLM(), FakeCache(), FakeVectorStore(), enrollment_repo)

    result = await service.retrieve("What am I covered for?", employee_id, employer_id)

    assert result.enrollment == [enrollment]
    assert enrollment_repo.list_by_employee_calls == [employee_id]


async def test_non_personal_query_does_not_fetch_enrollment() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    existing = Enrollment(employee_id=employee_id, policy_id=uuid4())
    enrollment_repo = FakeEnrollmentRepository([existing])
    service = _service(FakeLLM(), FakeCache(), FakeVectorStore(), enrollment_repo)

    result = await service.retrieve(
        "What is the standard coverage policy?", employee_id, employer_id
    )

    assert result.enrollment == []
    assert enrollment_repo.list_by_employee_calls == []


async def test_cache_key_is_deterministic_for_the_same_inputs() -> None:
    service = _service(FakeLLM(), FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())
    employer_id = uuid4()

    key_one = service._cache_key(employer_id, "What's my deductible?")
    key_two = service._cache_key(employer_id, "What's my deductible?")

    assert key_one == key_two


async def test_cache_key_differs_across_employers_for_the_same_query() -> None:
    service = _service(FakeLLM(), FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())

    key_one = service._cache_key(uuid4(), "What's my deductible?")
    key_two = service._cache_key(uuid4(), "What's my deductible?")

    assert key_one != key_two


async def test_cache_key_differs_across_queries_for_the_same_employer() -> None:
    service = _service(FakeLLM(), FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())
    employer_id = uuid4()

    key_one = service._cache_key(employer_id, "What's my deductible?")
    key_two = service._cache_key(employer_id, "What's my copay?")

    assert key_one != key_two


def _match(
    *, document_title: str = "SPD.pdf", section_title: str | None = None, text: str = ""
) -> VectorMatch:
    metadata: dict[str, Any] = {"document_title": document_title, "text": text}
    if section_title is not None:
        metadata["section_title"] = section_title
    return VectorMatch(id="chunk-1", score=0.9, metadata=metadata)


def _enrollment(**overrides: Any) -> Enrollment:
    defaults: dict[str, Any] = {
        "employee_id": uuid4(),
        "policy_id": uuid4(),
        "enrolled_at": datetime(2024, 1, 15, tzinfo=UTC),
        "is_active": True,
    }
    defaults.update(overrides)
    return Enrollment(**defaults)


def test_render_with_no_context_includes_the_no_context_notice() -> None:
    template = PromptTemplate()

    prompt = template.render("What's my deductible?", [], [])

    assert template.role_definition in prompt
    assert template.domain_restriction in prompt
    assert template.no_context_notice in prompt
    assert "Retrieved policy excerpts" not in prompt
    assert "current enrollments" not in prompt
    assert "Employee's question: What's my deductible?" in prompt


def test_render_includes_each_chunk_with_source_attribution() -> None:
    template = PromptTemplate()
    chunk = _match(
        document_title="SPD.pdf", section_title="Eligibility", text="You must work 30 hours."
    )

    prompt = template.render("query", [chunk], [])

    assert "Retrieved policy excerpts:" in prompt
    assert "[Source: SPD.pdf, Eligibility]" in prompt
    assert "You must work 30 hours." in prompt
    assert template.no_context_notice not in prompt


def test_render_omits_the_section_when_a_chunk_has_none() -> None:
    template = PromptTemplate()
    chunk = _match(document_title="SPD.pdf", section_title=None, text="Some body text.")

    prompt = template.render("query", [chunk], [])

    assert "[Source: SPD.pdf]" in prompt


def test_render_includes_enrollment_when_present() -> None:
    template = PromptTemplate()
    enrollment = _enrollment(is_active=True)

    prompt = template.render("query", [], [enrollment])

    assert "Employee's current enrollments:" in prompt
    assert str(enrollment.policy_id) in prompt
    assert "active" in prompt
    assert "2024-01-15" in prompt


def test_render_marks_an_inactive_enrollment() -> None:
    template = PromptTemplate()
    enrollment = _enrollment(is_active=False)

    prompt = template.render("query", [], [enrollment])

    assert "inactive" in prompt


def test_assemble_prompt_delegates_to_the_prompt_template() -> None:
    service = _service(FakeLLM(), FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())
    chunk = _match(text="Chunk body.")
    retrieval = RetrievalResult(chunks=[chunk], enrollment=[])

    prompt = service.assemble_prompt("What's covered?", retrieval)

    assert "Chunk body." in prompt
    assert "Employee's question: What's covered?" in prompt


def test_assemble_prompt_uses_a_custom_prompt_template() -> None:
    custom_template = PromptTemplate(role_definition="You are a custom test assistant.")
    service = RAGService(
        FakeLLM(),
        FakeCache(),
        FakeVectorStore(),
        FakeEnrollmentRepository(),
        embedding_model=_MODEL,
        prompt_template=custom_template,
    )

    prompt = service.assemble_prompt("query", RetrievalResult())

    assert "You are a custom test assistant." in prompt
