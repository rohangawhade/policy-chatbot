"""Document routes (files/plan.md Step 9.3, plus Step 8.3's earlier
status-check endpoints already in this file): upload, list, and delete,
completing the document resource alongside the ingestion-status
endpoints Step 8.3 added early.

Response shape matches the established convention from Step 9.1 (see
`auth_routes.py`'s module docstring) — this file returns its Pydantic
model(s) directly, not wrapped in `files/coding-standards.md` section
7's `APIResponse[T]` envelope.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from api.dependencies import (
    get_celery_app,
    get_document_chunk_repository,
    get_document_repository,
    get_document_service,
    get_vector_store_port,
)
from api.middleware.auth_middleware import get_current_user, require_role
from api.middleware.tenant_context import get_current_employer_id
from config import app_config
from core.domain.document import Document, DocumentStatus
from core.domain.employee import UserRole
from core.domain.policy import PolicyType
from core.ports.repository_ports import DocumentChunkRepository, DocumentRepository
from core.ports.vector_store_port import VectorStorePort
from core.services.auth_service import TokenPayload
from core.services.document_service import DocumentService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# A module-level singleton, not an inline `Depends(require_role(...))` at
# each call site — ruff's B008 flags a bare function call as a parameter
# default (`extend-immutable-calls` only covers the outer `Depends`
# itself), and this is genuinely reusable: both upload and delete are
# "employer or admin only".
_require_uploader_or_admin = require_role(UserRole.EMPLOYER, UserRole.ADMIN)

_POLL_INTERVAL_SECONDS = 2.0
_MAX_STREAM_SECONDS = 300.0
_TERMINAL_STATUSES = (DocumentStatus.READY, DocumentStatus.FAILED)

# The set of formats this route accepts, independent of
# `ProcessorFactory`'s own registry (`adapters/document_processors/`) —
# `api/` may import adapters only for DI wiring (files/coding-standards.md
# section 3), not to call adapter logic directly from a route handler.
# Adding a new document format therefore needs a second, small update
# here too, alongside `ProcessorFactory.register(...)` — an accepted,
# documented coupling, the same shape as the queue-routing "two-place
# change" already established in Steps 8.1/8.2.
_ALLOWED_UPLOAD_CONTENT_TYPES: dict[str, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    "xlsx": frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    "xml": frozenset({"application/xml", "text/xml"}),
}


class DocumentStatusResponse(BaseModel):
    id: UUID
    status: DocumentStatus
    version: int
    error_message: str | None


class DocumentListItemResponse(BaseModel):
    id: UUID
    employer_id: UUID
    title: str
    policy_type: PolicyType | None
    status: DocumentStatus
    version: int


async def _get_owned_document(
    document_repository: DocumentRepository, document_id: UUID, employer_id: UUID
) -> Document:
    document = await document_repository.get(document_id)
    if document is None or document.employer_id != employer_id:
        # Same 404 for "doesn't exist" and "belongs to another employer" —
        # a 403 would leak that the id exists at all, across a tenant
        # boundary that isn't this caller's to know about.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


async def _get_deletable_document(
    document_repository: DocumentRepository, document_id: UUID, current_user: TokenPayload
) -> Document:
    """Same not-found-vs-forbidden reasoning as `_get_owned_document`,
    except an `ADMIN` (no `employer_id` of its own — a superuser scoped
    to no single tenant, `core/domain/employee.py`) may delete any
    employer's document."""
    document = await document_repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if current_user.role != UserRole.ADMIN and document.employer_id != current_user.employer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


def _to_response(document: Document) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        id=document.id,
        status=document.status,
        version=document.version,
        error_message=document.error_message,
    )


def _to_list_item(document: Document) -> DocumentListItemResponse:
    return DocumentListItemResponse(
        id=document.id,
        employer_id=document.employer_id,
        title=document.title,
        policy_type=document.policy_type,
        status=document.status,
        version=document.version,
    )


def _extension_of(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def _resolve_upload_employer_id(current_user: TokenPayload, employer_id_field: UUID | None) -> UUID:
    """`EMPLOYER`-role accounts always upload under their own
    `employer_id` (from the token, never a client-supplied value) — an
    `ADMIN` has none, so it must name one explicitly (files/plan.md's
    "employer/admin only" for this endpoint)."""
    if current_user.employer_id is not None:
        return current_user.employer_id
    if employer_id_field is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="employer_id is required when uploading as an admin account.",
        )
    return employer_id_field


def _save_upload(employer_id: UUID, extension: str, content: bytes) -> Path:
    upload_dir = Path(app_config.upload_dir) / str(employer_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"{uuid4()}.{extension}"
    destination.write_bytes(content)
    return destination


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    policy_type: PolicyType | None = Form(None),
    employer_id: UUID | None = Form(None),
    current_user: TokenPayload = Depends(_require_uploader_or_admin),
    document_repository: DocumentRepository = Depends(get_document_repository),
    document_service: DocumentService = Depends(get_document_service),
    celery_app: Any = Depends(get_celery_app),
) -> DocumentStatusResponse:
    """Upload a benefits document for ingestion (employer or admin only).

    Validates the file (extension, content type, size), saves it to
    local disk (`APP_UPLOAD_DIR` — no S3/blob-storage port exists, per
    Step 8.2's explicit scope note), registers it as a `Document` row
    (`DocumentService.register_upload()`, Step 7.1 — re-uploading the
    same `title` under the same employer bumps the version
    automatically rather than creating an unrelated document), then
    hands it to `ingestion.process_document_upload` (Step 8.2) via
    Celery for the actual extraction/chunking/embedding. Returns
    immediately with the new `PROCESSING` document — poll `/status` or
    `/status/stream` (Step 8.3) for completion.
    """
    target_employer_id = _resolve_upload_employer_id(current_user, employer_id)

    # `UploadFile.filename` is typed `str | None`, but FastAPI's own
    # multipart parsing never actually delivers a `File(...)` parameter
    # with an empty/missing filename — a part with no filename fails
    # request validation before an `UploadFile` is ever constructed
    # (confirmed empirically while writing this route's tests: neither
    # `("", ...)` nor `(None, ...)` reaches this function at all). A type
    # narrowing, not a real HTTP-error branch.
    assert file.filename is not None
    extension = _extension_of(file.filename)
    allowed_content_types = _ALLOWED_UPLOAD_CONTENT_TYPES.get(extension)
    if allowed_content_types is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: .{extension or '?'}",
        )
    if file.content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Content type {file.content_type!r} doesn't match a .{extension} file.",
        )

    content = await file.read()
    max_bytes = app_config.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {app_config.max_upload_size_mb}MB upload limit.",
        )

    previous = await document_repository.get_latest_version(target_employer_id, title)
    destination = _save_upload(target_employer_id, extension, content)
    created = await document_service.register_upload(
        employer_id=target_employer_id,
        title=title,
        source_type=extension,
        source_path=str(destination),
        policy_type=policy_type,
    )
    celery_app.send_task(
        "ingestion.process_document_upload",
        kwargs={
            "document_data": created.model_dump(mode="json"),
            "previous_version_data": previous.model_dump(mode="json") if previous else None,
        },
    )
    return _to_response(created)


@router.get("")
async def list_documents(
    employer_id: UUID | None = None,
    current_user: TokenPayload = Depends(get_current_user),
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> list[DocumentListItemResponse]:
    """Lists documents for the caller's own tenant (`EMPLOYER`/`EMPLOYEE`
    accounts -- the `employer_id` query param is ignored for them, the
    token's own value always wins, same not-client-supplied rule as
    every other tenant-scoped read in this codebase) or, for an `ADMIN`
    account (which has no `employer_id` of its own,
    `core/domain/employee.py`), every document across every tenant,
    optionally narrowed to one employer via the query param -- the
    admin-dashboard document-management screen (files/plan.md Step
    10.4) needs to browse and manage documents it didn't necessarily
    upload itself."""
    if current_user.employer_id is not None:
        documents = await document_repository.list_by_employer(current_user.employer_id)
    else:
        documents = await document_repository.list_all(employer_id=employer_id)
    return [_to_list_item(document) for document in documents]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: TokenPayload = Depends(_require_uploader_or_admin),
    document_repository: DocumentRepository = Depends(get_document_repository),
    chunk_repository: DocumentChunkRepository = Depends(get_document_chunk_repository),
    vector_store: VectorStorePort = Depends(get_vector_store_port),
) -> None:
    """Remove a document and its vectors (employer or admin only).

    **Known gap, not addressed by this step**: cached RAG responses
    built from this document's chunks (`RAGService`'s Redis cache,
    Step 3.4/6.3) are not invalidated here — `invalidate_version_cache()`
    (Step 7.3) exists but still has no caller anywhere in the app (a
    standing gap tracked in IMPLEMENTATION_STATUS.md since that step,
    blocked on the same missing event-subscriber infrastructure as
    Step 6.1's `GuardrailRejectionEvent`). A deleted document's stale
    answers can outlive it in cache until that's resolved.
    """
    document = await _get_deletable_document(document_repository, document_id, current_user)
    # Best-effort: an unreachable/misconfigured vector store (already
    # retried by `PineconeAdapter` itself where the failure is
    # retryable) must not block deleting the user's own document -- it
    # would otherwise leave the document stuck and undeletable purely
    # because of an unrelated third-party outage. Worst case is a
    # handful of orphaned vectors under a `document_id` Postgres no
    # longer knows about, which the RAG pipeline never surfaces since
    # retrieval is always scoped to documents that still exist there.
    try:
        await vector_store.delete_by_metadata(
            str(document.employer_id), {"document_id": str(document.id)}
        )
    except Exception as exc:
        logger.exception(
            "document_vector_cleanup_failed", document_id=str(document.id), error=str(exc)
        )
    await chunk_repository.deactivate_by_document(document.id)
    await document_repository.delete(document.id)


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: UUID,
    employer_id: UUID = Depends(get_current_employer_id),
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentStatusResponse:
    """A single snapshot of `document_ingestion_task`'s (Step 8.2)
    progress — `processing`/`ready`/`failed`, plus `error_message` when
    failed."""
    document = await _get_owned_document(document_repository, document_id, employer_id)
    return _to_response(document)


@router.get("/{document_id}/status/stream")
async def stream_document_status(
    document_id: UUID,
    employer_id: UUID = Depends(get_current_employer_id),
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> StreamingResponse:
    """SSE stream of `Document.status` until it reaches a terminal state
    (`ready`/`failed`) or `_MAX_STREAM_SECONDS` elapses, whichever comes
    first — an immediate first event, then re-checked every
    `_POLL_INTERVAL_SECONDS`.

    **Implemented as polling, not a true push, as a deliberate scope
    decision**: files/coding-standards.md section 12's event-bus-first
    rule doesn't fit here — there's no event-subscriber-registration
    infrastructure anywhere in this app yet (a standing gap tracked in
    IMPLEMENTATION_STATUS.md since Step 6.1; wiring a real push, e.g.
    Redis pub/sub from `document_ingestion_task.py`, is that
    infrastructure's own future step, not this endpoint's job to build
    prematurely). A single-resource status poll at a few-second interval
    is an honestly-scoped interim implementation of "SSE push," not a
    placeholder pretending to be something it isn't — clients already
    get a real `text/event-stream` they can consume with `EventSource`.
    """
    await _get_owned_document(document_repository, document_id, employer_id)
    return StreamingResponse(
        _stream_status_events(document_repository, document_id, employer_id),
        media_type="text/event-stream",
    )


async def _stream_status_events(
    document_repository: DocumentRepository,
    document_id: UUID,
    employer_id: UUID,
    *,
    poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
    max_duration_seconds: float = _MAX_STREAM_SECONDS,
) -> AsyncIterator[str]:
    elapsed = 0.0
    while True:
        document = await document_repository.get(document_id)
        if document is None or document.employer_id != employer_id:
            # The document vanished or changed ownership mid-stream —
            # response headers are already sent at this point, so there's
            # nothing left to raise an HTTPException into; stop silently.
            return
        yield _format_sse_event(document)
        if document.status in _TERMINAL_STATUSES or elapsed >= max_duration_seconds:
            return
        await asyncio.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds


def _format_sse_event(document: Document) -> str:
    payload = {"status": document.status.value, "error_message": document.error_message}
    return f"data: {json.dumps(payload)}\n\n"
