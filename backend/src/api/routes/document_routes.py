"""Document ingestion status endpoints (files/plan.md Step 8.3).

Scoped deliberately narrow: just status-checking (a snapshot endpoint
and an SSE stream), not the full upload/list/delete resource — that's
Phase 9's `POST /api/documents/upload` etc. This step's own plan.md
bullet ("API endpoint to check document processing status. SSE push to
frontend when processing completes.") is really Phase 9 API-route work
pulled forward a step early, so it stays scoped to exactly what it says.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from api.dependencies import get_document_repository
from api.middleware.tenant_context import get_current_employer_id
from core.domain.document import Document, DocumentStatus
from core.ports.repository_ports import DocumentRepository

router = APIRouter(prefix="/api/documents", tags=["documents"])

_POLL_INTERVAL_SECONDS = 2.0
_MAX_STREAM_SECONDS = 300.0
_TERMINAL_STATUSES = (DocumentStatus.READY, DocumentStatus.FAILED)


class DocumentStatusResponse(BaseModel):
    id: UUID
    status: DocumentStatus
    version: int
    error_message: str | None


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


def _to_response(document: Document) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        id=document.id,
        status=document.status,
        version=document.version,
        error_message=document.error_message,
    )


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
