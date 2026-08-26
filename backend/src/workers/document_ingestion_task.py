"""Celery task: the full document-ingestion pipeline (files/plan.md Step
8.2) — detect file type, extract text, chunk, embed/index, update
status, publish completion. Thin by design, same as
`workers/embedding_task.py` (Step 4.4/7.2): wires concrete adapters and
owns the request-scoped DB session, delegating actual logic to
`ProcessorFactory`, `ChunkerPipeline`, and `EmbeddingService`.
`EmbeddingService.embed_and_store()` is called directly as a plain
method call rather than by enqueueing `embedding_task`'s own Celery task
and waiting on it — chaining a synchronous wait on another queued task
from inside a task risks worker starvation, and there's no reason to
queue a second time for work already running in this worker process.
`embedding_task.embed_and_index_document` remains independently useful
on its own (re-embedding an already-chunked document without redoing
extraction) — this task doesn't replace it, it's a fuller pipeline on
top of the same shared `EmbeddingService`.

Scope boundary: `Document.source_path` is read as a local filesystem
path — every `DocumentProcessorPort` implementation (`PDFProcessor`/
`DOCXProcessor`/`XLSXProcessor`/`XMLProcessor`, Step 3.6) opens it
directly via its underlying library (`fitz.open`, `docx.Document`,
etc.), and no file-storage port/adapter (S3 or otherwise) exists
anywhere in this codebase — plan.md's port list (Step 2.2) doesn't
include one. If uploads eventually land in S3, downloading to a local
temp path first is the future upload route's (Phase 9) job, not this
task's.
"""

import asyncio
import time
from typing import Any
from uuid import uuid4

import structlog

from adapters.chunking.chunker_pipeline import ChunkerPipeline
from adapters.chunking.metadata_extractor import MetadataExtractor
from adapters.chunking.semantic_chunker import SemanticChunker
from adapters.document_processors.processor_factory import ProcessorFactory
from adapters.event_bus.in_memory_event_bus import InMemoryEventBus
from adapters.llm.litellm_adapter import LiteLLMAdapter
from adapters.persistence.database import async_session_factory, engine
from adapters.persistence.document_repo import (
    PostgresDocumentChunkRepository,
    PostgresDocumentRepository,
)
from adapters.vector_store.pinecone_adapter import PineconeAdapter
from config import llm_config, pinecone_config
from core.domain.document import Document, DocumentStatus
from core.domain.events import DocumentProcessedEvent
from core.services.embedding_service import EmbeddingService
from workers.celery_app import app

logger = structlog.get_logger(__name__)


@app.task(
    name="ingestion.process_document_upload",
    # Whole-attempt retry (Step 8.1's convention) — a transient failure
    # anywhere in extraction/chunking/embedding gets 3 attempts with
    # exponential backoff before landing in the dead-letter queue.
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)  # type: ignore[misc]
# `app.task` resolves to `Any` (celery.* has no stubs, per pyproject.toml's
# ignore_missing_imports override) — mypy strict's disallow_untyped_decorators
# still flags decorating with an Any-typed callable itself.
def process_document_upload(
    document_data: dict[str, Any],
    previous_version_data: dict[str, Any] | None = None,
) -> None:
    """Celery entry point.

    Args:
        document_data: A `Document` serialized via
            `.model_dump(mode="json")` — Celery's default JSON
            serializer can't carry `UUID`/`datetime` objects directly.
            The row this describes must already exist in Postgres
            (created by `DocumentService.register_upload()`, Step 7.1)
            — this task processes it, it doesn't create it.
        previous_version_data: The document this upload replaces
            (`register_upload()`'s `previous`), serialized the same
            way, or `None` for a title's first-ever upload —
            files/plan.md Step 7.2's vector/chunk replacement, run as
            part of this same pipeline via `EmbeddingService`.
    """
    document = Document.model_validate(document_data)
    previous_version = (
        Document.model_validate(previous_version_data)
        if previous_version_data is not None
        else None
    )
    asyncio.run(_process_document_upload(document, previous_version))


async def _process_document_upload(document: Document, previous_version: Document | None) -> None:
    structlog.contextvars.bind_contextvars(
        correlation_id=str(uuid4()), employer_id=str(document.employer_id)
    )
    start = time.monotonic()
    logger.info(
        "document_ingestion_started",
        document_id=str(document.id),
        source_type=document.source_type,
    )
    try:
        async with async_session_factory() as session:
            document_repository = PostgresDocumentRepository(session)
            event_bus = InMemoryEventBus()
            llm = LiteLLMAdapter()

            try:
                processor = ProcessorFactory.get(document.source_type)
                text = processor.extract_text(document.source_path)

                chunker = ChunkerPipeline(
                    MetadataExtractor(),
                    SemanticChunker(llm=llm, embedding_model=llm_config.embedding_model),
                )
                chunks = await chunker.process(text, document)

                embedding_service = EmbeddingService(
                    llm=llm,
                    vector_store=PineconeAdapter(
                        api_key=pinecone_config.api_key or "unconfigured",
                        index_name=pinecone_config.index_name,
                    ),
                    chunk_repository=PostgresDocumentChunkRepository(session),
                    event_bus=event_bus,
                    embedding_model=llm_config.embedding_model,
                )
                await embedding_service.embed_and_store(chunks, document, previous_version)
            except Exception as exc:
                logger.exception(
                    "document_ingestion_failed", document_id=str(document.id), error=str(exc)
                )
                document.status = DocumentStatus.FAILED
                document.error_message = str(exc)
                await document_repository.update(document)
                await session.commit()
                raise

            document.status = DocumentStatus.READY
            document.error_message = None
            await document_repository.update(document)

            await event_bus.publish(
                DocumentProcessedEvent(document_id=document.id, employer_id=document.employer_id)
            )
            await session.commit()
            logger.info(
                "document_ingestion_completed",
                document_id=str(document.id),
                chunk_count=len(chunks),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
    finally:
        structlog.contextvars.clear_contextvars()
        # See the matching comment in `embedding_task.py`: `engine`
        # (adapters/persistence/database.py) is a module-level singleton
        # shared across every task this worker process ever runs, but
        # each task gets its own fresh event loop via `asyncio.run()`
        # (below) — a pooled connection from *this* loop fails with
        # "attached to a different loop" if the *next* task's different
        # loop reuses it. Disposing here leaves the pool empty for that
        # next task. Real bug, not hypothetical — found via this exact
        # step's real-stack validation the moment a real worker
        # processed a second task.
        await engine.dispose()
