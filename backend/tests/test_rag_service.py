from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from core.domain.policy import Enrollment
from core.ports.cache_port import CachePort
from core.ports.llm_port import LLMPort
from core.ports.repository_ports import EnrollmentRepository
from core.ports.vector_store_port import VectorMatch, VectorStorePort
from core.services.rag_service import RAGService

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
