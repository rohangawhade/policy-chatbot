import asyncio
import contextlib
from typing import Any
from uuid import uuid4

import pytest

from config import pinecone_config
from core.domain.document import Document, DocumentChunk, DocumentStatus
from core.domain.events import DocumentProcessedEvent, DomainEvent
from workers import document_ingestion_task
from workers.celery_app import app


def _document(**overrides: Any) -> Document:
    defaults: dict[str, Any] = {
        "employer_id": uuid4(),
        "title": "Summary Plan Description",
        "source_type": "pdf",
        "source_path": "/tmp/spd.pdf",
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
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


class _FakeSessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakeDocumentRepository:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        self.updated: list[Document] = []

    async def update(self, entity: Document) -> Document:
        self.updated.append(entity.model_copy())
        return entity


class _FakeChunkRepository:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session


class _FakePineconeAdapter:
    def __init__(self, *, api_key: str, index_name: str) -> None:
        self.api_key = api_key
        self.index_name = index_name


class _FakeProcessor:
    def __init__(self, text: str = "extracted text", *, raises: Exception | None = None) -> None:
        self.text = text
        self.raises = raises
        self.extract_text_calls: list[str] = []

    def extract_text(self, file_path: str) -> str:
        self.extract_text_calls.append(file_path)
        if self.raises is not None:
            raise self.raises
        return self.text


class _FakeProcessorFactory:
    instance: _FakeProcessor | None = None
    get_calls: list[str] = []

    @classmethod
    def get(cls, extension: str) -> _FakeProcessor:
        cls.get_calls.append(extension)
        assert cls.instance is not None
        return cls.instance


class _FakeChunkerPipeline:
    instances: list["_FakeChunkerPipeline"] = []
    chunks_to_return: list[DocumentChunk] = []
    raises: Exception | None = None

    def __init__(self, metadata_extractor: object, semantic_chunker: object) -> None:
        self.metadata_extractor = metadata_extractor
        self.semantic_chunker = semantic_chunker
        self.process_calls: list[tuple[str, Document]] = []
        _FakeChunkerPipeline.instances.append(self)

    async def process(self, text: str, document: Document) -> list[DocumentChunk]:
        self.process_calls.append((text, document))
        if _FakeChunkerPipeline.raises is not None:
            raise _FakeChunkerPipeline.raises
        return _FakeChunkerPipeline.chunks_to_return


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
        self.embed_and_store_calls: list[tuple[list[DocumentChunk], Document, Document | None]] = []
        _FakeEmbeddingService.instances.append(self)

    async def embed_and_store(
        self,
        chunks: list[DocumentChunk],
        document: Document,
        previous_version: Document | None = None,
    ) -> None:
        self.embed_and_store_calls.append((chunks, document, previous_version))


def _patch_collaborators(
    monkeypatch: pytest.MonkeyPatch,
    fake_session: _FakeSession,
    *,
    extracted_text: str = "extracted text",
    processor_raises: Exception | None = None,
    chunks_to_return: list[DocumentChunk] | None = None,
    chunker_raises: Exception | None = None,
) -> None:
    _FakeProcessorFactory.instance = _FakeProcessor(extracted_text, raises=processor_raises)
    _FakeProcessorFactory.get_calls = []
    _FakeChunkerPipeline.instances = []
    _FakeChunkerPipeline.chunks_to_return = chunks_to_return or []
    _FakeChunkerPipeline.raises = chunker_raises
    _FakeEmbeddingService.instances = []

    monkeypatch.setattr(pinecone_config, "api_key", None)
    monkeypatch.setattr(
        document_ingestion_task, "async_session_factory", lambda: _FakeSessionContext(fake_session)
    )
    monkeypatch.setattr(document_ingestion_task, "LiteLLMAdapter", lambda: "fake-llm")
    monkeypatch.setattr(document_ingestion_task, "PineconeAdapter", _FakePineconeAdapter)
    monkeypatch.setattr(
        document_ingestion_task, "PostgresDocumentRepository", _FakeDocumentRepository
    )
    monkeypatch.setattr(
        document_ingestion_task, "PostgresDocumentChunkRepository", _FakeChunkRepository
    )
    monkeypatch.setattr(document_ingestion_task, "ProcessorFactory", _FakeProcessorFactory)
    monkeypatch.setattr(document_ingestion_task, "ChunkerPipeline", _FakeChunkerPipeline)
    monkeypatch.setattr(document_ingestion_task, "EmbeddingService", _FakeEmbeddingService)


def test_task_is_registered_on_the_celery_app() -> None:
    assert "ingestion.process_document_upload" in app.tasks


def test_task_has_a_retry_policy() -> None:
    task = app.tasks["ingestion.process_document_upload"]

    assert task.autoretry_for == (Exception,)
    assert task.retry_backoff is True
    assert task.retry_kwargs == {"max_retries": 3}


def test_document_survives_a_json_round_trip() -> None:
    document = _document()

    document_data = document.model_dump(mode="json")

    assert Document.model_validate(document_data) == document


async def test_successful_ingestion_extracts_chunks_embeds_and_marks_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession()
    document = _document()
    chunks = [_chunk(document, 0)]
    _patch_collaborators(
        monkeypatch, fake_session, extracted_text="hello world", chunks_to_return=chunks
    )

    await document_ingestion_task._process_document_upload(document, None)

    assert _FakeProcessorFactory.get_calls == ["pdf"]
    assert _FakeProcessorFactory.instance is not None
    assert _FakeProcessorFactory.instance.extract_text_calls == ["/tmp/spd.pdf"]

    chunker = _FakeChunkerPipeline.instances[0]
    assert chunker.process_calls == [("hello world", document)]

    service = _FakeEmbeddingService.instances[0]
    assert service.embed_and_store_calls == [(chunks, document, None)]
    assert service.llm == "fake-llm"


async def test_uses_the_pinecone_embedding_adapter_when_a_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession()
    document = _document()
    _patch_collaborators(monkeypatch, fake_session, chunks_to_return=[_chunk(document, 0)])
    monkeypatch.setattr(pinecone_config, "api_key", "real-key")
    monkeypatch.setattr(
        document_ingestion_task,
        "PineconeEmbeddingAdapter",
        lambda *, pinecone_api_key: "fake-pinecone-llm",
    )

    await document_ingestion_task._process_document_upload(document, None)

    service = _FakeEmbeddingService.instances[0]
    assert service.llm == "fake-pinecone-llm"

    assert document.status == DocumentStatus.READY
    assert document.error_message is None
    assert fake_session.commit_count == 1


async def test_successful_ingestion_publishes_document_processed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession()
    document = _document()
    published: list[DomainEvent] = []
    _patch_collaborators(monkeypatch, fake_session)

    class _CapturingEventBus:
        async def publish(self, event: DomainEvent) -> None:
            published.append(event)

    monkeypatch.setattr(document_ingestion_task, "InMemoryEventBus", _CapturingEventBus)

    await document_ingestion_task._process_document_upload(document, None)

    assert len(published) == 1
    event = published[0]
    assert isinstance(event, DocumentProcessedEvent)
    assert event.document_id == document.id
    assert event.employer_id == document.employer_id


async def test_ingestion_passes_previous_version_through_to_embedding_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession()
    document = _document()
    previous_version = _document(employer_id=document.employer_id, version=1)
    _patch_collaborators(monkeypatch, fake_session)

    await document_ingestion_task._process_document_upload(document, previous_version)

    service = _FakeEmbeddingService.instances[0]
    assert service.embed_and_store_calls == [([], document, previous_version)]


async def test_extraction_failure_marks_the_document_failed_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession()
    document = _document()
    _patch_collaborators(monkeypatch, fake_session, processor_raises=ValueError("corrupt pdf"))

    with pytest.raises(ValueError, match="corrupt pdf"):
        await document_ingestion_task._process_document_upload(document, None)

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "corrupt pdf"
    assert fake_session.commit_count == 1


async def test_chunking_failure_marks_the_document_failed_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession()
    document = _document()
    _patch_collaborators(monkeypatch, fake_session, chunker_raises=RuntimeError("chunking blew up"))

    with pytest.raises(RuntimeError, match="chunking blew up"):
        await document_ingestion_task._process_document_upload(document, None)

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "chunking blew up"


async def test_failure_does_not_publish_document_processed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession()
    document = _document()
    published: list[DomainEvent] = []
    _patch_collaborators(monkeypatch, fake_session, processor_raises=ValueError("boom"))

    class _CapturingEventBus:
        async def publish(self, event: DomainEvent) -> None:
            published.append(event)

    monkeypatch.setattr(document_ingestion_task, "InMemoryEventBus", _CapturingEventBus)

    with contextlib.suppress(ValueError):
        await document_ingestion_task._process_document_upload(document, None)

    assert published == []


def test_task_deserializes_json_args_and_delegates_to_process_document_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    calls: list[tuple[Document, Document | None]] = []

    async def fake_process(document: Document, previous_version: Document | None) -> None:
        calls.append((document, previous_version))

    monkeypatch.setattr(document_ingestion_task, "_process_document_upload", fake_process)

    def run_without_a_real_event_loop(coro: Any) -> None:
        with contextlib.suppress(StopIteration):
            coro.send(None)

    monkeypatch.setattr(asyncio, "run", run_without_a_real_event_loop)

    document_ingestion_task.process_document_upload(document.model_dump(mode="json"))

    assert calls == [(document, None)]


def test_task_deserializes_a_previous_version_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    previous_version = _document(employer_id=document.employer_id, version=1)
    calls: list[tuple[Document, Document | None]] = []

    async def fake_process(document: Document, previous_version: Document | None) -> None:
        calls.append((document, previous_version))

    monkeypatch.setattr(document_ingestion_task, "_process_document_upload", fake_process)

    def run_without_a_real_event_loop(coro: Any) -> None:
        with contextlib.suppress(StopIteration):
            coro.send(None)

    monkeypatch.setattr(asyncio, "run", run_without_a_real_event_loop)

    document_ingestion_task.process_document_upload(
        document.model_dump(mode="json"), previous_version.model_dump(mode="json")
    )

    assert calls == [(document, previous_version)]
