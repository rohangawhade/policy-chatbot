from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from core.domain.document import Document, DocumentChunk, DocumentStatus
from core.domain.events import DocumentEmbeddedEvent, DomainEvent
from core.domain.policy import PolicyType
from core.ports.event_bus_port import EventBusPort, EventHandler
from core.ports.llm_port import LLMPort
from core.ports.repository_ports import DocumentChunkRepository
from core.ports.vector_store_port import VectorRecord, VectorStorePort
from core.services.embedding_service import EmbeddingService

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
        return [[float(len(text)), 0.0] for text in texts]


class FakeVectorStore(VectorStorePort):
    def __init__(self) -> None:
        self.upsert_calls: list[tuple[str, list[VectorRecord]]] = []

    async def upsert(self, namespace: str, records: list[VectorRecord]) -> None:
        self.upsert_calls.append((namespace, records))

    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[Any]:
        raise NotImplementedError

    async def delete_by_metadata(self, namespace: str, metadata_filter: dict[str, Any]) -> None:
        raise NotImplementedError


class FakeChunkRepository(DocumentChunkRepository):
    def __init__(self) -> None:
        self.created: list[DocumentChunk] = []

    async def get(self, entity_id: UUID) -> DocumentChunk | None:
        raise NotImplementedError

    async def create(self, entity: DocumentChunk) -> DocumentChunk:
        self.created.append(entity)
        return entity

    async def update(self, entity: DocumentChunk) -> DocumentChunk:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_document(self, document_id: UUID) -> list[DocumentChunk]:
        raise NotImplementedError

    async def deactivate_by_document(self, document_id: UUID) -> None:
        raise NotImplementedError


class FakeEventBus(EventBusPort):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError


def _document(**overrides: Any) -> Document:
    defaults: dict[str, Any] = {
        "employer_id": uuid4(),
        "title": "Summary Plan Description",
        "source_type": "pdf",
        "source_path": "s3://bucket/spd.pdf",
        "status": DocumentStatus.PROCESSING,
    }
    defaults.update(overrides)
    return Document(**defaults)


def _chunk(document: Document, index: int, **overrides: Any) -> DocumentChunk:
    defaults: dict[str, Any] = {
        "document_id": document.id,
        "employer_id": document.employer_id,
        "chunk_index": index,
        "text": f"Chunk {index} text.",
    }
    defaults.update(overrides)
    return DocumentChunk(**defaults)


class _Fakes:
    def __init__(self) -> None:
        self.llm = FakeLLM()
        self.vector_store = FakeVectorStore()
        self.repo = FakeChunkRepository()
        self.bus = FakeEventBus()
        self.service = EmbeddingService(
            self.llm, self.vector_store, self.repo, self.bus, embedding_model=_MODEL
        )


async def test_embeds_each_chunks_text_with_the_configured_model() -> None:
    fakes = _Fakes()
    document = _document()
    chunks = [_chunk(document, 0), _chunk(document, 1)]

    await fakes.service.embed_and_store(chunks, document)

    assert fakes.llm.embed_calls == [([c.text for c in chunks], _MODEL)]


async def test_upserts_one_vector_record_per_chunk_to_the_employer_namespace() -> None:
    fakes = _Fakes()
    document = _document()
    chunks = [_chunk(document, 0), _chunk(document, 1)]

    await fakes.service.embed_and_store(chunks, document)

    assert len(fakes.vector_store.upsert_calls) == 1
    namespace, records = fakes.vector_store.upsert_calls[0]
    assert namespace == str(document.employer_id)
    assert [r.id for r in records] == [str(c.id) for c in chunks]


async def test_vector_metadata_includes_document_and_chunk_context() -> None:
    fakes = _Fakes()
    document = _document(policy_type=PolicyType.DENTAL, version=2)
    chunk = _chunk(document, 0, section_title="Eligibility", page_number=3)

    await fakes.service.embed_and_store([chunk], document)

    _, records = fakes.vector_store.upsert_calls[0]
    assert records[0].metadata == {
        "employer_id": str(document.employer_id),
        "document_id": str(document.id),
        "document_title": document.title,
        "document_version": 2,
        "chunk_index": 0,
        "text": chunk.text,
        "policy_type": "dental",
        "section_title": "Eligibility",
        "page_number": 3,
    }


async def test_vector_metadata_omits_optional_fields_when_unset() -> None:
    fakes = _Fakes()
    document = _document(policy_type=None)
    chunk = _chunk(document, 0, section_title=None, page_number=None)

    await fakes.service.embed_and_store([chunk], document)

    _, records = fakes.vector_store.upsert_calls[0]
    assert "policy_type" not in records[0].metadata
    assert "section_title" not in records[0].metadata
    assert "page_number" not in records[0].metadata


async def test_persists_every_chunk_via_the_repository() -> None:
    fakes = _Fakes()
    document = _document()
    chunks = [_chunk(document, 0), _chunk(document, 1), _chunk(document, 2)]

    await fakes.service.embed_and_store(chunks, document)

    assert fakes.repo.created == chunks


async def test_publishes_document_embedded_event_with_the_chunk_count() -> None:
    fakes = _Fakes()
    document = _document()
    chunks = [_chunk(document, 0), _chunk(document, 1)]

    await fakes.service.embed_and_store(chunks, document)

    assert len(fakes.bus.published) == 1
    event = fakes.bus.published[0]
    assert isinstance(event, DocumentEmbeddedEvent)
    assert event.document_id == document.id
    assert event.employer_id == document.employer_id
    assert event.chunk_count == 2


async def test_empty_chunk_list_skips_embedding_and_indexing_but_still_publishes() -> None:
    fakes = _Fakes()
    document = _document()

    await fakes.service.embed_and_store([], document)

    assert fakes.llm.embed_calls == []
    assert fakes.vector_store.upsert_calls == []
    assert fakes.repo.created == []
    assert len(fakes.bus.published) == 1
    event = fakes.bus.published[0]
    assert isinstance(event, DocumentEmbeddedEvent)
    assert event.document_id == document.id
    assert event.employer_id == document.employer_id
    assert event.chunk_count == 0
