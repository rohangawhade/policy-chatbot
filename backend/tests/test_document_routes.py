import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapters.event_bus.in_memory_event_bus import InMemoryEventBus
from api.dependencies import (
    get_celery_app,
    get_document_chunk_repository,
    get_document_repository,
    get_document_service,
    get_vector_store_port,
)
from api.middleware.auth_middleware import get_current_user
from api.middleware.tenant_context import get_current_employer_id
from api.routes import document_routes
from core.domain.document import Document, DocumentChunk, DocumentStatus
from core.domain.employee import UserRole
from core.ports.repository_ports import DocumentChunkRepository, DocumentRepository
from core.ports.vector_store_port import VectorMatch, VectorRecord, VectorStorePort
from core.services.auth_service import TokenPayload
from core.services.document_service import DocumentService


class _FakeDocumentRepository(DocumentRepository):
    def __init__(self, documents: list[Document] | None = None) -> None:
        self._documents = {document.id: document for document in (documents or [])}

    async def get(self, entity_id: UUID) -> Document | None:
        return self._documents.get(entity_id)

    async def create(self, entity: Document) -> Document:
        self._documents[entity.id] = entity
        return entity

    async def update(self, entity: Document) -> Document:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        self._documents.pop(entity_id, None)

    async def list_by_employer(self, employer_id: UUID) -> list[Document]:
        return [d for d in self._documents.values() if d.employer_id == employer_id]

    async def get_latest_version(self, employer_id: UUID, title: str) -> Document | None:
        matches = [
            d for d in self._documents.values() if d.employer_id == employer_id and d.title == title
        ]
        return max(matches, key=lambda d: d.version) if matches else None

    def set_status(self, document_id: UUID, status: DocumentStatus) -> None:
        self._documents[document_id].status = status

    async def list_all(self, *, employer_id: UUID | None = None) -> list[Document]:
        if employer_id is None:
            return list(self._documents.values())
        return [d for d in self._documents.values() if d.employer_id == employer_id]

    async def mark_queried(self, document_ids: list[UUID]) -> None:
        raise NotImplementedError


class _FakeDocumentChunkRepository(DocumentChunkRepository):
    def __init__(self) -> None:
        self.deactivated_document_ids: list[UUID] = []

    async def get(self, entity_id: UUID) -> DocumentChunk | None:
        raise NotImplementedError

    async def create(self, entity: DocumentChunk) -> DocumentChunk:
        raise NotImplementedError

    async def update(self, entity: DocumentChunk) -> DocumentChunk:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_document(self, document_id: UUID) -> list[DocumentChunk]:
        raise NotImplementedError

    async def deactivate_by_document(self, document_id: UUID) -> None:
        self.deactivated_document_ids.append(document_id)


class _FakeVectorStore(VectorStorePort):
    def __init__(self) -> None:
        self.deleted_calls: list[tuple[str, dict[str, Any]]] = []

    async def upsert(self, namespace: str, records: list[VectorRecord]) -> None:
        raise NotImplementedError

    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        raise NotImplementedError

    async def delete_by_metadata(self, namespace: str, metadata_filter: dict[str, Any]) -> None:
        self.deleted_calls.append((namespace, metadata_filter))


class _FakeCeleryApp:
    def __init__(self) -> None:
        self.sent_tasks: list[dict[str, Any]] = []

    def send_task(self, name: str, kwargs: dict[str, Any] | None = None, **_extra: Any) -> None:
        self.sent_tasks.append({"name": name, "kwargs": kwargs})


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


def _test_app(
    *,
    employer_id: UUID,
    document_repository: DocumentRepository | None = None,
    chunk_repository: DocumentChunkRepository | None = None,
    vector_store: VectorStorePort | None = None,
    celery_app: _FakeCeleryApp | None = None,
    current_user: TokenPayload | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(document_routes.router)
    repository = document_repository or _FakeDocumentRepository()
    app.dependency_overrides[get_document_repository] = lambda: repository
    app.dependency_overrides[get_document_chunk_repository] = lambda: (
        chunk_repository or _FakeDocumentChunkRepository()
    )
    app.dependency_overrides[get_vector_store_port] = lambda: vector_store or _FakeVectorStore()
    app.dependency_overrides[get_document_service] = lambda: DocumentService(
        repository, InMemoryEventBus()
    )
    app.dependency_overrides[get_celery_app] = lambda: celery_app or _FakeCeleryApp()
    app.dependency_overrides[get_current_employer_id] = lambda: employer_id
    app.dependency_overrides[get_current_user] = lambda: current_user or TokenPayload(
        user_id=uuid4(), employer_id=employer_id, role=UserRole.EMPLOYER, token_type="access"
    )
    return app


# --- status / stream (Step 8.3, unchanged) ---------------------------------


def test_status_endpoint_returns_the_documents_current_status() -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id, version=3)
    client = TestClient(
        _test_app(employer_id=employer_id, document_repository=_FakeDocumentRepository([document]))
    )

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
    client = TestClient(
        _test_app(employer_id=employer_id, document_repository=_FakeDocumentRepository([document]))
    )

    response = client.get(f"/api/documents/{document.id}/status")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error_message"] == "corrupt pdf"


def test_status_endpoint_404s_for_an_unknown_document() -> None:
    client = TestClient(_test_app(employer_id=uuid4()))

    response = client.get(f"/api/documents/{uuid4()}/status")

    assert response.status_code == 404


def test_status_endpoint_404s_for_a_document_owned_by_another_employer() -> None:
    document = _document(employer_id=uuid4())
    client = TestClient(
        _test_app(employer_id=uuid4(), document_repository=_FakeDocumentRepository([document]))
    )

    response = client.get(f"/api/documents/{document.id}/status")

    assert response.status_code == 404


def test_stream_endpoint_404s_for_an_unknown_document() -> None:
    client = TestClient(_test_app(employer_id=uuid4()))

    response = client.get(f"/api/documents/{uuid4()}/status/stream")

    assert response.status_code == 404


def test_stream_endpoint_emits_a_single_event_for_an_already_terminal_document() -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id, status=DocumentStatus.READY)
    client = TestClient(
        _test_app(employer_id=employer_id, document_repository=_FakeDocumentRepository([document]))
    )

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


# --- POST /upload (Step 9.3) -----------------------------------------------


def test_upload_document_creates_a_processing_document_and_enqueues_ingestion(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_routes.app_config, "upload_dir", str(tmp_path))
    employer_id = uuid4()
    celery_app = _FakeCeleryApp()
    client = TestClient(_test_app(employer_id=employer_id, celery_app=celery_app))

    response = client.post(
        "/api/documents/upload",
        files={"file": ("policy.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        data={"title": "Health Plan SPD", "policy_type": "health"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing"
    assert body["version"] == 1

    assert len(celery_app.sent_tasks) == 1
    task = celery_app.sent_tasks[0]
    assert task["name"] == "ingestion.process_document_upload"
    assert task["kwargs"]["document_data"]["id"] == body["id"]
    assert task["kwargs"]["document_data"]["employer_id"] == str(employer_id)
    assert task["kwargs"]["document_data"]["policy_type"] == "health"
    assert task["kwargs"]["previous_version_data"] is None

    saved_files = list(tmp_path.rglob("*.pdf"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == b"%PDF-1.4 fake content"


def test_upload_document_bumps_the_version_on_a_second_upload_with_the_same_title(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_routes.app_config, "upload_dir", str(tmp_path))
    employer_id = uuid4()
    existing = _document(employer_id=employer_id, title="Health Plan SPD", version=1)
    repository = _FakeDocumentRepository([existing])
    celery_app = _FakeCeleryApp()
    client = TestClient(
        _test_app(employer_id=employer_id, document_repository=repository, celery_app=celery_app)
    )

    response = client.post(
        "/api/documents/upload",
        files={"file": ("policy.pdf", b"new content", "application/pdf")},
        data={"title": "Health Plan SPD"},
    )

    assert response.status_code == 202
    assert response.json()["version"] == 2
    assert celery_app.sent_tasks[0]["kwargs"]["previous_version_data"]["id"] == str(existing.id)


def test_upload_document_rejects_an_unsupported_file_type() -> None:
    client = TestClient(_test_app(employer_id=uuid4()))

    response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"title": "Notes"},
    )

    assert response.status_code == 422


def test_upload_document_rejects_a_content_type_mismatch() -> None:
    client = TestClient(_test_app(employer_id=uuid4()))

    response = client.post(
        "/api/documents/upload",
        files={"file": ("policy.pdf", b"hello", "text/plain")},
        data={"title": "Health Plan SPD"},
    )

    assert response.status_code == 422


def test_upload_document_rejects_a_file_over_the_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(document_routes.app_config, "max_upload_size_mb", 0)
    client = TestClient(_test_app(employer_id=uuid4()))

    response = client.post(
        "/api/documents/upload",
        files={"file": ("policy.pdf", b"more than zero bytes", "application/pdf")},
        data={"title": "Health Plan SPD"},
    )

    assert response.status_code == 413


def test_upload_document_403s_for_an_employee_role() -> None:
    employer_id = uuid4()
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            current_user=TokenPayload(
                user_id=uuid4(),
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.post(
        "/api/documents/upload",
        files={"file": ("policy.pdf", b"hello", "application/pdf")},
        data={"title": "Health Plan SPD"},
    )

    assert response.status_code == 403


def test_upload_document_as_admin_requires_an_explicit_employer_id(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_routes.app_config, "upload_dir", str(tmp_path))
    client = TestClient(
        _test_app(
            employer_id=uuid4(),
            current_user=TokenPayload(
                user_id=uuid4(), employer_id=None, role=UserRole.ADMIN, token_type="access"
            ),
        )
    )

    without_employer_id = client.post(
        "/api/documents/upload",
        files={"file": ("policy.pdf", b"hello", "application/pdf")},
        data={"title": "Health Plan SPD"},
    )
    assert without_employer_id.status_code == 422

    target_employer_id = uuid4()
    with_employer_id = client.post(
        "/api/documents/upload",
        files={"file": ("policy.pdf", b"hello", "application/pdf")},
        data={"title": "Health Plan SPD", "employer_id": str(target_employer_id)},
    )
    assert with_employer_id.status_code == 202
    assert with_employer_id.json()["status"] == "processing"


# --- GET /documents (list, Step 9.3) ---------------------------------------


def test_list_documents_returns_only_the_current_employers_documents() -> None:
    employer_id = uuid4()
    mine = _document(employer_id=employer_id, title="Mine")
    someone_elses = _document(employer_id=uuid4(), title="Theirs")
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            document_repository=_FakeDocumentRepository([mine, someone_elses]),
        )
    )

    response = client.get("/api/documents")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(mine.id)
    assert body[0]["title"] == "Mine"


# --- DELETE /documents/{id} (Step 9.3) --------------------------------------


def test_delete_document_purges_vectors_deactivates_chunks_and_removes_the_row() -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id)
    repository = _FakeDocumentRepository([document])
    chunk_repository = _FakeDocumentChunkRepository()
    vector_store = _FakeVectorStore()
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            document_repository=repository,
            chunk_repository=chunk_repository,
            vector_store=vector_store,
        )
    )

    response = client.delete(f"/api/documents/{document.id}")

    assert response.status_code == 204
    assert vector_store.deleted_calls == [(str(employer_id), {"document_id": str(document.id)})]
    assert chunk_repository.deactivated_document_ids == [document.id]
    # Not `asyncio.run(repository.get(...))`: calling that from a sync
    # test function while `TestClient` also manages its own event loop
    # segfaults under coverage.py on Linux CI (found the hard way — see
    # IMPLEMENTATION_STATUS.md's Step 9.3 entry). The fake's own dict is
    # already synchronous and just as direct.
    assert document.id not in repository._documents


def test_delete_document_404s_for_an_unknown_document() -> None:
    client = TestClient(_test_app(employer_id=uuid4()))

    response = client.delete(f"/api/documents/{uuid4()}")

    assert response.status_code == 404


def test_delete_document_404s_for_another_employers_document() -> None:
    document = _document(employer_id=uuid4())
    client = TestClient(
        _test_app(employer_id=uuid4(), document_repository=_FakeDocumentRepository([document]))
    )

    response = client.delete(f"/api/documents/{document.id}")

    assert response.status_code == 404


def test_delete_document_allows_an_admin_to_delete_any_employers_document() -> None:
    document = _document(employer_id=uuid4())
    client = TestClient(
        _test_app(
            employer_id=uuid4(),
            document_repository=_FakeDocumentRepository([document]),
            current_user=TokenPayload(
                user_id=uuid4(), employer_id=None, role=UserRole.ADMIN, token_type="access"
            ),
        )
    )

    response = client.delete(f"/api/documents/{document.id}")

    assert response.status_code == 204


def test_delete_document_403s_for_an_employee_role() -> None:
    employer_id = uuid4()
    document = _document(employer_id=employer_id)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            document_repository=_FakeDocumentRepository([document]),
            current_user=TokenPayload(
                user_id=uuid4(),
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.delete(f"/api/documents/{document.id}")

    assert response.status_code == 403
