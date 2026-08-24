from typing import Any
from uuid import uuid4

import pytest

from config import llm_config
from core.domain.document import Document, DocumentChunk, DocumentStatus
from workers import embedding_task
from workers.celery_app import app


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


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class _FakeSessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakePineconeAdapter:
    def __init__(self, *, api_key: str, index_name: str) -> None:
        self.api_key = api_key
        self.index_name = index_name


class _FakeChunkRepository:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session


class _FakeEmbeddingService:
    instances: list["_FakeEmbeddingService"] = []

    def __init__(
        self,
        llm: object,
        vector_store: object,
        chunk_repository: object,
        event_bus: object,
        embedding_model: str,
    ) -> None:
        self.llm = llm
        self.vector_store = vector_store
        self.chunk_repository = chunk_repository
        self.event_bus = event_bus
        self.embedding_model = embedding_model
        self.embed_and_store_calls: list[tuple[list[DocumentChunk], Document]] = []
        _FakeEmbeddingService.instances.append(self)

    async def embed_and_store(self, chunks: list[DocumentChunk], document: Document) -> None:
        self.embed_and_store_calls.append((chunks, document))


def test_task_is_registered_on_the_celery_app() -> None:
    assert "embedding.embed_and_index_document" in app.tasks


def test_document_and_chunk_survive_a_json_round_trip() -> None:
    document = _document()
    chunk = _chunk(document, 0, section_title="Eligibility", page_number=2)

    document_data = document.model_dump(mode="json")
    chunk_data = chunk.model_dump(mode="json")

    assert Document.model_validate(document_data) == document
    assert DocumentChunk.model_validate(chunk_data) == chunk


async def test_embed_and_index_wires_adapters_and_commits_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeEmbeddingService.instances.clear()
    fake_session = _FakeSession()
    monkeypatch.setattr(
        embedding_task, "async_session_factory", lambda: _FakeSessionContext(fake_session)
    )
    monkeypatch.setattr(embedding_task, "LiteLLMAdapter", lambda: "fake-llm")
    monkeypatch.setattr(embedding_task, "PineconeAdapter", _FakePineconeAdapter)
    monkeypatch.setattr(embedding_task, "PostgresDocumentChunkRepository", _FakeChunkRepository)
    monkeypatch.setattr(embedding_task, "InMemoryEventBus", lambda: "fake-bus")
    monkeypatch.setattr(embedding_task, "EmbeddingService", _FakeEmbeddingService)

    document = _document()
    chunks = [_chunk(document, 0)]

    await embedding_task._embed_and_index(document, chunks)

    assert fake_session.committed is True
    assert len(_FakeEmbeddingService.instances) == 1
    service = _FakeEmbeddingService.instances[0]
    assert service.llm == "fake-llm"
    assert service.event_bus == "fake-bus"
    assert isinstance(service.chunk_repository, _FakeChunkRepository)
    assert service.chunk_repository.session is fake_session
    assert service.embedding_model == llm_config.embedding_model
    assert service.embed_and_store_calls == [(chunks, document)]


def test_task_deserializes_json_args_and_delegates_to_embed_and_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    chunks = [_chunk(document, 0)]
    calls: list[tuple[Document, list[DocumentChunk]]] = []

    async def fake_embed_and_index(document: Document, chunks: list[DocumentChunk]) -> None:
        calls.append((document, chunks))

    monkeypatch.setattr(embedding_task, "_embed_and_index", fake_embed_and_index)

    embedding_task.embed_and_index_document(
        document.model_dump(mode="json"), [c.model_dump(mode="json") for c in chunks]
    )

    assert calls == [(document, chunks)]
