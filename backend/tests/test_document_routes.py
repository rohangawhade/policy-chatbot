import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_document_repository
from api.middleware.tenant_context import get_current_employer_id
from api.routes import document_routes
from core.domain.document import Document, DocumentStatus
from core.ports.repository_ports import DocumentRepository


class _FakeDocumentRepository(DocumentRepository):
    def __init__(self, documents: list[Document] | None = None) -> None:
        self._documents = {document.id: document for document in (documents or [])}

    async def get(self, entity_id: UUID) -> Document | None:
        return self._documents.get(entity_id)

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

    def set_status(self, document_id: UUID, status: DocumentStatus) -> None:
        self._documents[document_id].status = status


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


def _test_app(repository: DocumentRepository, employer_id: UUID) -> FastAPI:
    app = FastAPI()
    app.include_router(document_routes.router)
    app.dependency_overrides[get_document_repository] = lambda: repository
    app.dependency_overrides[get_current_employer_id] = lambda: employer_id
    return app


def test_status_endpoint_returns_the_documents_current_status() -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id, version=3)
    client = TestClient(_test_app(_FakeDocumentRepository([document]), employer_id))

    response = client.get(f"/api/documents/{document.id}/status")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(document.id),
        "status": "processing",
        "version": 3,
        "error_message": None,
    }


def test_status_endpoint_includes_the_error_message_when_failed() -> None:
    employer_id = uuid4()
    document = _document(
        employer_id=employer_id, status=DocumentStatus.FAILED, error_message="corrupt pdf"
    )
    client = TestClient(_test_app(_FakeDocumentRepository([document]), employer_id))

    response = client.get(f"/api/documents/{document.id}/status")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error_message"] == "corrupt pdf"


def test_status_endpoint_404s_for_an_unknown_document() -> None:
    client = TestClient(_test_app(_FakeDocumentRepository([]), uuid4()))

    response = client.get(f"/api/documents/{uuid4()}/status")

    assert response.status_code == 404


def test_status_endpoint_404s_for_a_document_owned_by_another_employer() -> None:
    document = _document(employer_id=uuid4())
    client = TestClient(_test_app(_FakeDocumentRepository([document]), uuid4()))

    response = client.get(f"/api/documents/{document.id}/status")

    assert response.status_code == 404


def test_stream_endpoint_404s_for_an_unknown_document() -> None:
    client = TestClient(_test_app(_FakeDocumentRepository([]), uuid4()))

    response = client.get(f"/api/documents/{uuid4()}/status/stream")

    assert response.status_code == 404


def test_stream_endpoint_emits_a_single_event_for_an_already_terminal_document() -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id, status=DocumentStatus.READY)
    client = TestClient(_test_app(_FakeDocumentRepository([document]), employer_id))

    with client.stream("GET", f"/api/documents/{document.id}/status/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert body.count("data: ") == 1
    assert '"status": "ready"' in body


async def test_stream_generator_polls_until_a_terminal_status_then_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id, status=DocumentStatus.PROCESSING)
    repository = _FakeDocumentRepository([document])
    sleep_calls: list[float] = []

    async def _fast_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) == 2:
            repository.set_status(document.id, DocumentStatus.READY)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    events = [
        event
        async for event in document_routes._stream_status_events(
            repository, document.id, employer_id, poll_interval_seconds=0.01
        )
    ]

    assert len(events) == 3
    assert '"status": "processing"' in events[0]
    assert '"status": "processing"' in events[1]
    assert '"status": "ready"' in events[2]
    assert sleep_calls == [0.01, 0.01]


async def test_stream_generator_stops_after_max_duration_even_without_a_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id, status=DocumentStatus.PROCESSING)
    repository = _FakeDocumentRepository([document])

    async def _fast_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    events = [
        event
        async for event in document_routes._stream_status_events(
            repository,
            document.id,
            employer_id,
            poll_interval_seconds=1.0,
            max_duration_seconds=2.0,
        )
    ]

    assert len(events) == 3
    assert all('"status": "processing"' in event for event in events)


async def test_stream_generator_stops_silently_if_the_document_disappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id, status=DocumentStatus.PROCESSING)
    repository = _FakeDocumentRepository([document])

    async def _fast_sleep(seconds: float) -> None:
        del repository._documents[document.id]

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    events = [
        event
        async for event in document_routes._stream_status_events(
            repository, document.id, employer_id, poll_interval_seconds=0.01
        )
    ]

    assert len(events) == 1


async def test_stream_generator_stops_silently_if_ownership_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id, status=DocumentStatus.PROCESSING)
    repository = _FakeDocumentRepository([document])

    async def _fast_sleep(seconds: float) -> None:
        repository._documents[document.id] = document.model_copy(update={"employer_id": uuid4()})

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    events = [
        event
        async for event in document_routes._stream_status_events(
            repository, document.id, employer_id, poll_interval_seconds=0.01
        )
    ]

    assert len(events) == 1
