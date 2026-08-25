from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.document import Document
from core.domain.events import (
    ChatMessageReceivedEvent,
    ChatResponseGeneratedEvent,
    DomainEvent,
    LowConfidenceResponseEvent,
)
from core.domain.policy import Enrollment, PolicyType
from core.ports.cache_port import CachePort
from core.ports.event_bus_port import EventBusPort, EventHandler
from core.ports.llm_port import LLMPort, UsageCost
from core.ports.repository_ports import (
    AnalyticsRepository,
    ConversationRepository,
    DocumentRepository,
    EnrollmentRepository,
    MessageRepository,
)
from core.ports.vector_store_port import VectorMatch, VectorStorePort
from core.services.query_router import QueryRouter
from core.services.rag_service import GenerationStream, PromptTemplate, RAGService, RetrievalResult

_MODEL = "mock-embedding-model"
_CHEAP_MODEL = "cheap-model"
_POWERFUL_MODEL = "powerful-model"


class FakeLLM(LLMPort):
    def __init__(self, stream_tokens: list[str] | None = None) -> None:
        self.embed_calls: list[tuple[list[str], str]] = []
        self.generate_stream_calls: list[tuple[str, str]] = []
        self.estimate_cost_calls: list[tuple[str, str, str]] = []
        self._stream_tokens = stream_tokens if stream_tokens is not None else ["hello", " world"]

    async def generate(
        self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
    ) -> str:
        raise NotImplementedError

    async def generate_stream(
        self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
    ) -> AsyncIterator[str]:
        self.generate_stream_calls.append((prompt, model))
        for token in self._stream_tokens:
            yield token

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        self.embed_calls.append((texts, model))
        return [[1.0, 0.0] for _ in texts]

    async def estimate_cost(self, model: str, prompt: str, completion: str) -> UsageCost:
        self.estimate_cost_calls.append((model, prompt, completion))
        return UsageCost(input_tokens=10, output_tokens=5, estimated_cost_usd=0.001)


class FakeCache(CachePort):
    def __init__(self, stored: dict[str, str] | None = None) -> None:
        self._stored = stored or {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.delete_by_prefix_calls: list[str] = []

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self._stored.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.set_calls.append((key, value, ttl_seconds))
        self._stored[key] = value

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    async def delete_by_prefix(self, prefix: str) -> None:
        self.delete_by_prefix_calls.append(prefix)
        for key in [key for key in self._stored if key.startswith(prefix)]:
            del self._stored[key]


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


class FakeAnalyticsRepository(AnalyticsRepository):
    def __init__(self) -> None:
        self.llm_cost_logs: list[LLMCostLog] = []
        self.latency_logs: list[RequestLatencyLog] = []
        self.flagged_responses: list[FlaggedResponse] = []

    async def record_llm_cost(self, log: LLMCostLog) -> None:
        self.llm_cost_logs.append(log)

    async def record_latency(self, log: RequestLatencyLog) -> None:
        self.latency_logs.append(log)

    async def record_flagged_response(self, flagged: FlaggedResponse) -> None:
        self.flagged_responses.append(flagged)

    async def record_guardrail_rejection(self, rejection: GuardrailRejection) -> None:
        raise NotImplementedError

    async def list_llm_costs(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[LLMCostLog]:
        raise NotImplementedError

    async def list_latencies(
        self,
        *,
        employer_id: UUID | None = None,
        model_tier: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[RequestLatencyLog]:
        raise NotImplementedError

    async def list_flagged_responses(
        self, *, employer_id: UUID | None = None, status: FlaggedResponseStatus | None = None
    ) -> list[FlaggedResponse]:
        raise NotImplementedError

    async def get_flagged_response(self, flagged_response_id: UUID) -> FlaggedResponse | None:
        raise NotImplementedError

    async def update_flagged_response_status(
        self, flagged_response_id: UUID, status: FlaggedResponseStatus
    ) -> FlaggedResponse:
        raise NotImplementedError

    async def list_guardrail_rejections(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[GuardrailRejection]:
        raise NotImplementedError


class FakeConversationRepository(ConversationRepository):
    def __init__(self) -> None:
        self.created: list[Conversation] = []

    async def get(self, entity_id: UUID) -> Conversation | None:
        raise NotImplementedError

    async def create(self, entity: Conversation) -> Conversation:
        self.created.append(entity)
        return entity

    async def update(self, entity: Conversation) -> Conversation:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employee(self, employee_id: UUID) -> list[Conversation]:
        raise NotImplementedError

    async def list_active_since(
        self, since: datetime, *, employer_id: UUID | None = None
    ) -> list[Conversation]:
        raise NotImplementedError


class FakeMessageRepository(MessageRepository):
    def __init__(self, history: list[Message] | None = None) -> None:
        self.created: list[Message] = []
        self._history = history or []
        self.list_by_conversation_calls: list[tuple[UUID, int]] = []

    async def get(self, entity_id: UUID) -> Message | None:
        raise NotImplementedError

    async def create(self, entity: Message) -> Message:
        self.created.append(entity)
        return entity

    async def update(self, entity: Message) -> Message:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_conversation(
        self, conversation_id: UUID, *, limit: int = 20
    ) -> list[Message]:
        self.list_by_conversation_calls.append((conversation_id, limit))
        return self._history

    async def list_for_analytics(
        self,
        *,
        employer_id: UUID | None = None,
        role: MessageRole | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Message]:
        raise NotImplementedError


class FakeDocumentRepository(DocumentRepository):
    def __init__(self) -> None:
        self.mark_queried_calls: list[list[UUID]] = []

    async def get(self, entity_id: UUID) -> Document | None:
        raise NotImplementedError

    async def create(self, entity: Document) -> Document:
        raise NotImplementedError

    async def update(self, entity: Document) -> Document:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employer(self, employer_id: UUID) -> list[Document]:
        raise NotImplementedError

    async def get_latest_version(self, employer_id: UUID, title: str) -> Document | None:
        raise NotImplementedError

    async def list_all(self, *, employer_id: UUID | None = None) -> list[Document]:
        raise NotImplementedError

    async def mark_queried(self, document_ids: list[UUID]) -> None:
        self.mark_queried_calls.append(document_ids)


class FakeEventBus(EventBusPort):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError


def _router(threshold: float = 0.4) -> QueryRouter:
    return QueryRouter(_CHEAP_MODEL, _POWERFUL_MODEL, threshold)


def _service(
    llm: FakeLLM,
    cache: FakeCache,
    vector_store: FakeVectorStore,
    enrollment_repository: FakeEnrollmentRepository,
    analytics_repository: FakeAnalyticsRepository | None = None,
    query_router: QueryRouter | None = None,
    conversation_repository: FakeConversationRepository | None = None,
    message_repository: FakeMessageRepository | None = None,
    event_bus: FakeEventBus | None = None,
    document_repository: FakeDocumentRepository | None = None,
    top_k: int = 5,
    low_confidence_threshold: float = 0.5,
) -> RAGService:
    return RAGService(
        llm,
        cache,
        vector_store,
        enrollment_repository,
        analytics_repository or FakeAnalyticsRepository(),
        query_router or _router(),
        conversation_repository or FakeConversationRepository(),
        message_repository or FakeMessageRepository(),
        event_bus or FakeEventBus(),
        document_repository or FakeDocumentRepository(),
        embedding_model=_MODEL,
        top_k=top_k,
        low_confidence_threshold=low_confidence_threshold,
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


async def test_retrieve_marks_every_matched_documents_id_as_queried() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    document_id = uuid4()
    matches = [
        VectorMatch(id="chunk-1", score=0.9, metadata={"document_id": str(document_id)}),
        VectorMatch(id="chunk-2", score=0.8, metadata={"document_id": str(document_id)}),
    ]
    document_repository = FakeDocumentRepository()
    service = _service(
        FakeLLM(),
        FakeCache(),
        FakeVectorStore(matches),
        FakeEnrollmentRepository(),
        document_repository=document_repository,
    )

    await service.retrieve("What is generally covered?", employee_id, employer_id)

    assert document_repository.mark_queried_calls == [[document_id]]


async def test_retrieve_marks_no_documents_queried_when_chunks_have_no_document_id() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    document_repository = FakeDocumentRepository()
    service = _service(
        FakeLLM(),
        FakeCache(),
        FakeVectorStore([VectorMatch(id="chunk-1", score=0.9, metadata={})]),
        FakeEnrollmentRepository(),
        document_repository=document_repository,
    )

    await service.retrieve("What is generally covered?", employee_id, employer_id)

    assert document_repository.mark_queried_calls == [[]]


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


async def test_cache_key_differs_across_policy_types_for_the_same_query() -> None:
    service = _service(FakeLLM(), FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())
    employer_id = uuid4()

    key_dental = service._cache_key(employer_id, "What's my deductible?", PolicyType.DENTAL)
    key_vision = service._cache_key(employer_id, "What's my deductible?", PolicyType.VISION)
    key_none = service._cache_key(employer_id, "What's my deductible?", None)

    assert len({key_dental, key_vision, key_none}) == 3


async def test_cache_key_for_a_detected_policy_type_shares_the_invalidation_prefix() -> None:
    service = _service(FakeLLM(), FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())
    employer_id = uuid4()

    key = service._cache_key(employer_id, "What's my dental deductible?", PolicyType.DENTAL)

    assert key.startswith(service._cache_key_prefix(employer_id, PolicyType.DENTAL))


async def test_retrieve_uses_the_detected_policy_types_cache_key() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm, vector_store = FakeLLM(), FakeVectorStore()
    probe_service = _service(llm, FakeCache(), vector_store, FakeEnrollmentRepository())
    expected_key = probe_service._cache_key(
        employer_id, "What's my dental deductible?", PolicyType.DENTAL
    )
    cache = FakeCache({expected_key: "cached dental answer"})
    service = _service(llm, cache, vector_store, FakeEnrollmentRepository())

    result = await service.retrieve("What's my dental deductible?", employee_id, employer_id)

    assert result.cached_response == "cached dental answer"
    assert result.policy_type == PolicyType.DENTAL


async def test_invalidate_version_cache_deletes_by_the_employer_and_policy_type_prefix() -> None:
    cache = FakeCache()
    service = _service(FakeLLM(), cache, FakeVectorStore(), FakeEnrollmentRepository())
    employer_id = uuid4()

    await service.invalidate_version_cache(employer_id, PolicyType.DENTAL)

    assert cache.delete_by_prefix_calls == [
        service._cache_key_prefix(employer_id, PolicyType.DENTAL)
    ]


async def test_invalidate_version_cache_with_no_policy_type_only_targets_untyped_queries() -> None:
    cache = FakeCache()
    service = _service(FakeLLM(), cache, FakeVectorStore(), FakeEnrollmentRepository())
    employer_id = uuid4()
    dental_key = service._cache_key(employer_id, "dental query", PolicyType.DENTAL)
    untyped_key = service._cache_key(employer_id, "generic query", None)
    await cache.set(dental_key, "dental answer")
    await cache.set(untyped_key, "generic answer")

    await service.invalidate_version_cache(employer_id, None)

    assert await cache.get(dental_key) == "dental answer"
    assert await cache.get(untyped_key) is None


async def test_query_caches_using_the_detected_policy_types_key() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["dental answer"])
    cache = FakeCache()
    service = _service(llm, cache, FakeVectorStore(), FakeEnrollmentRepository())
    expected_key = service._cache_key(
        employer_id, "What's my dental deductible?", PolicyType.DENTAL
    )

    stream = await service.query("What's my dental deductible?", employee_id, employer_id)
    await _consume(stream)

    assert len(cache.set_calls) == 1
    key, _value, _ttl = cache.set_calls[0]
    assert key == expected_key


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
        FakeAnalyticsRepository(),
        _router(),
        FakeConversationRepository(),
        FakeMessageRepository(),
        FakeEventBus(),
        FakeDocumentRepository(),
        embedding_model=_MODEL,
        prompt_template=custom_template,
    )

    prompt = service.assemble_prompt("query", RetrievalResult())

    assert "You are a custom test assistant." in prompt


async def _consume(stream: GenerationStream) -> list[str]:
    return [token async for token in stream]


async def test_query_cache_hit_yields_cached_text_without_calling_the_llm() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm, analytics = FakeLLM(), FakeAnalyticsRepository()
    service = _service(llm, FakeCache(), FakeVectorStore(), FakeEnrollmentRepository(), analytics)
    cache_key = service._cache_key(employer_id, "What's my deductible?")
    cache = FakeCache({cache_key: "cached answer"})
    service = _service(llm, cache, FakeVectorStore(), FakeEnrollmentRepository(), analytics)

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    tokens = await _consume(stream)

    assert tokens == ["cached answer"]
    assert stream.metrics is not None
    assert stream.metrics.from_cache is True
    assert stream.metrics.full_text == "cached answer"
    assert stream.metrics.model == ""
    assert stream.metrics.top_similarity_score is None
    assert stream.metrics.is_low_confidence is False
    assert llm.generate_stream_calls == []
    assert cache.set_calls == []
    assert analytics.llm_cost_logs == []
    assert analytics.latency_logs == []


async def test_query_streams_tokens_from_the_llm_on_a_cache_miss() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["Your ", "deductible ", "is $500."])
    service = _service(llm, FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    tokens = await _consume(stream)

    assert "".join(tokens).startswith("Your deductible is $500.")
    assert len(llm.generate_stream_calls) == 1
    assert stream.metrics is not None
    assert stream.metrics.from_cache is False


async def test_query_appends_source_citations_when_chunks_have_titles() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    match = VectorMatch(id="c1", score=0.9, metadata={"document_title": "SPD.pdf"})
    llm = FakeLLM(stream_tokens=["answer"])
    service = _service(llm, FakeCache(), FakeVectorStore([match]), FakeEnrollmentRepository())

    stream = await service.query("What's my dental deductible?", employee_id, employer_id)
    tokens = await _consume(stream)

    full_text = "".join(tokens)
    assert "Sources: SPD.pdf" in full_text
    assert stream.metrics is not None
    assert stream.metrics.full_text == full_text


async def test_query_omits_citations_when_no_chunks_were_retrieved() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    service = _service(llm, FakeCache(), FakeVectorStore([]), FakeEnrollmentRepository())

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    tokens = await _consume(stream)

    assert "Sources:" not in "".join(tokens)


async def test_query_caches_the_full_response_after_streaming() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["full answer"])
    cache = FakeCache()
    service = _service(llm, cache, FakeVectorStore(), FakeEnrollmentRepository())
    expected_key = service._cache_key(employer_id, "What's my deductible?")

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert len(cache.set_calls) == 1
    key, value, ttl = cache.set_calls[0]
    assert key == expected_key
    assert value == "full answer"
    assert ttl == 3600


async def test_query_logs_llm_cost_and_latency_after_streaming() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    analytics = FakeAnalyticsRepository()
    service = _service(llm, FakeCache(), FakeVectorStore(), FakeEnrollmentRepository(), analytics)

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert len(analytics.llm_cost_logs) == 1
    cost_log = analytics.llm_cost_logs[0]
    assert cost_log.employer_id == employer_id
    assert cost_log.model == _CHEAP_MODEL
    assert cost_log.model_tier == "cheap"
    assert cost_log.input_tokens == 10
    assert cost_log.output_tokens == 5
    assert cost_log.estimated_cost_usd == 0.001

    assert len(analytics.latency_logs) == 1
    latency_log = analytics.latency_logs[0]
    assert latency_log.employer_id == employer_id
    assert latency_log.model_tier == "cheap"
    assert latency_log.total_ms >= 0


async def test_query_selects_the_powerful_model_for_a_complex_query() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    service = _service(llm, FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())

    stream = await service.query(
        "Compare health vs dental coverage for my family", employee_id, employer_id
    )
    await _consume(stream)

    assert llm.generate_stream_calls[0][1] == _POWERFUL_MODEL
    assert stream.metrics is not None
    assert stream.metrics.model_tier == "powerful"


async def test_query_selects_the_cheap_model_for_a_simple_query() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    service = _service(llm, FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert llm.generate_stream_calls[0][1] == _CHEAP_MODEL
    assert stream.metrics is not None
    assert stream.metrics.model_tier == "cheap"


async def test_query_flags_low_confidence_below_the_threshold() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    match = VectorMatch(id="c1", score=0.2, metadata={})
    llm = FakeLLM(stream_tokens=["answer"])
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore([match]),
        FakeEnrollmentRepository(),
        low_confidence_threshold=0.5,
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert stream.metrics is not None
    assert stream.metrics.top_similarity_score == 0.2
    assert stream.metrics.is_low_confidence is True


async def test_query_does_not_flag_confidence_at_or_above_the_threshold() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    match = VectorMatch(id="c1", score=0.9, metadata={})
    llm = FakeLLM(stream_tokens=["answer"])
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore([match]),
        FakeEnrollmentRepository(),
        low_confidence_threshold=0.5,
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert stream.metrics is not None
    assert stream.metrics.is_low_confidence is False


async def test_query_top_similarity_score_is_none_without_retrieved_chunks() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    service = _service(llm, FakeCache(), FakeVectorStore([]), FakeEnrollmentRepository())

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert stream.metrics is not None
    assert stream.metrics.top_similarity_score is None
    assert stream.metrics.is_low_confidence is False


async def test_metrics_is_none_before_the_stream_is_consumed() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    service = _service(llm, FakeCache(), FakeVectorStore(), FakeEnrollmentRepository())

    stream = await service.query("What's my deductible?", employee_id, employer_id)

    assert stream.metrics is None


def test_render_includes_conversation_history() -> None:
    template = PromptTemplate()
    history = [
        Message(conversation_id=uuid4(), employer_id=uuid4(), role=MessageRole.USER, content="Hi"),
        Message(
            conversation_id=uuid4(),
            employer_id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="Hello, how can I help?",
        ),
    ]

    prompt = template.render("follow-up question", [], [], history)

    assert "Conversation so far:" in prompt
    assert "Employee: Hi" in prompt
    assert "Assistant: Hello, how can I help?" in prompt


def test_render_omits_history_section_when_there_is_none() -> None:
    template = PromptTemplate()

    prompt = template.render("query", [], [], None)

    assert "Conversation so far:" not in prompt


async def test_query_starts_a_new_conversation_when_none_is_given() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    conversation_repo = FakeConversationRepository()
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore(),
        FakeEnrollmentRepository(),
        conversation_repository=conversation_repo,
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert len(conversation_repo.created) == 1
    new_conversation = conversation_repo.created[0]
    assert new_conversation.employee_id == employee_id
    assert new_conversation.employer_id == employer_id
    assert stream.metrics is not None
    assert stream.metrics.conversation_id == new_conversation.id


async def test_query_continues_an_existing_conversation_without_creating_a_new_one() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    existing_conversation_id = uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    conversation_repo = FakeConversationRepository()
    message_repo = FakeMessageRepository()
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore(),
        FakeEnrollmentRepository(),
        conversation_repository=conversation_repo,
        message_repository=message_repo,
    )

    stream = await service.query(
        "Follow-up question", employee_id, employer_id, existing_conversation_id
    )
    await _consume(stream)

    assert conversation_repo.created == []
    assert stream.metrics is not None
    assert stream.metrics.conversation_id == existing_conversation_id
    assert message_repo.list_by_conversation_calls == [(existing_conversation_id, 20)]


async def test_query_persists_the_user_and_assistant_messages() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["Your ", "answer."])
    message_repo = FakeMessageRepository()
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore(),
        FakeEnrollmentRepository(),
        message_repository=message_repo,
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert len(message_repo.created) == 2
    user_message, assistant_message = message_repo.created
    assert user_message.role == MessageRole.USER
    assert user_message.content == "What's my deductible?"
    assert assistant_message.role == MessageRole.ASSISTANT
    assert assistant_message.content == "Your answer."
    assert assistant_message.model_used == _CHEAP_MODEL


async def test_query_publishes_chat_message_received_and_response_generated_events() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm = FakeLLM(stream_tokens=["answer"])
    event_bus = FakeEventBus()
    service = _service(
        llm, FakeCache(), FakeVectorStore(), FakeEnrollmentRepository(), event_bus=event_bus
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    received_events = [e for e in event_bus.published if isinstance(e, ChatMessageReceivedEvent)]
    generated_events = [e for e in event_bus.published if isinstance(e, ChatResponseGeneratedEvent)]
    assert len(received_events) == 1
    assert received_events[0].employee_id == employee_id
    assert received_events[0].employer_id == employer_id
    assert len(generated_events) == 1
    assert generated_events[0].model_used == _CHEAP_MODEL
    assert generated_events[0].conversation_id == stream.metrics.conversation_id  # type: ignore[union-attr]


async def test_query_low_confidence_persists_flagged_response_and_publishes_event() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    match = VectorMatch(id="c1", score=0.2, metadata={})
    llm = FakeLLM(stream_tokens=["answer"])
    analytics = FakeAnalyticsRepository()
    event_bus = FakeEventBus()
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore([match]),
        FakeEnrollmentRepository(),
        analytics_repository=analytics,
        event_bus=event_bus,
        low_confidence_threshold=0.5,
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert len(analytics.flagged_responses) == 1
    flagged = analytics.flagged_responses[0]
    assert flagged.employer_id == employer_id
    assert flagged.top_similarity_score == 0.2
    assert flagged.flag_reason == "low_retrieval_confidence"
    low_confidence_events = [
        e for e in event_bus.published if isinstance(e, LowConfidenceResponseEvent)
    ]
    assert len(low_confidence_events) == 1
    assert low_confidence_events[0].top_similarity_score == 0.2


async def test_query_high_confidence_does_not_flag_or_publish() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    match = VectorMatch(id="c1", score=0.9, metadata={})
    llm = FakeLLM(stream_tokens=["answer"])
    analytics = FakeAnalyticsRepository()
    event_bus = FakeEventBus()
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore([match]),
        FakeEnrollmentRepository(),
        analytics_repository=analytics,
        event_bus=event_bus,
        low_confidence_threshold=0.5,
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert analytics.flagged_responses == []
    assert not any(isinstance(e, LowConfidenceResponseEvent) for e in event_bus.published)


async def test_query_cache_hit_still_persists_a_conversation_turn() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm, message_repo = FakeLLM(), FakeMessageRepository()
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore(),
        FakeEnrollmentRepository(),
        message_repository=message_repo,
    )
    cache_key = service._cache_key(employer_id, "What's my deductible?")
    cache = FakeCache({cache_key: "cached answer"})
    service = _service(
        llm, cache, FakeVectorStore(), FakeEnrollmentRepository(), message_repository=message_repo
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert len(message_repo.created) == 2
    assert message_repo.created[1].content == "cached answer"
    assert message_repo.created[1].model_used is None
    assert stream.metrics is not None
    assert stream.metrics.conversation_id is not None
    assert stream.metrics.message_id is not None


async def test_query_cache_hit_does_not_publish_response_generated_event() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    llm, event_bus = FakeLLM(), FakeEventBus()
    service = _service(
        llm, FakeCache(), FakeVectorStore(), FakeEnrollmentRepository(), event_bus=event_bus
    )
    cache_key = service._cache_key(employer_id, "What's my deductible?")
    cache = FakeCache({cache_key: "cached answer"})
    service = _service(
        llm, cache, FakeVectorStore(), FakeEnrollmentRepository(), event_bus=event_bus
    )

    stream = await service.query("What's my deductible?", employee_id, employer_id)
    await _consume(stream)

    assert not any(isinstance(e, ChatResponseGeneratedEvent) for e in event_bus.published)
    # The user's message is still recorded as received, even on a cache hit.
    assert any(isinstance(e, ChatMessageReceivedEvent) for e in event_bus.published)


async def test_query_passes_conversation_history_into_the_prompt() -> None:
    employer_id, employee_id = uuid4(), uuid4()
    conversation_id = uuid4()
    history = [
        Message(
            conversation_id=conversation_id,
            employer_id=employer_id,
            role=MessageRole.USER,
            content="What plans are available?",
        )
    ]
    llm = FakeLLM(stream_tokens=["answer"])
    message_repo = FakeMessageRepository(history=history)
    service = _service(
        llm,
        FakeCache(),
        FakeVectorStore(),
        FakeEnrollmentRepository(),
        message_repository=message_repo,
    )

    stream = await service.query(
        "And what about dental?", employee_id, employer_id, conversation_id
    )
    await _consume(stream)

    prompt = llm.generate_stream_calls[0][0]
    assert "What plans are available?" in prompt
