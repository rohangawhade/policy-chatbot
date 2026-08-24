"""Celery task: embeds a document's already-chunked text, indexes it in
the vector store, and persists chunk references (files/plan.md Step
4.4). Thin by design — the actual logic lives in `EmbeddingService`
(core/services/); this module only wires up concrete adapters, bridges
into Celery's synchronous task model, and owns the request-scoped DB
session (a Celery task plays the same "commit here" role the API layer
plays for HTTP requests — files/coding-standards.md's Unit of Work rule;
`PostgresRepository` never commits on its own, only flushes).

Adapters are constructed fresh per task invocation rather than shared at
module level: `PineconeAdapter`'s constructor raises immediately if
`PINECONE_API_KEY` isn't configured (no key at all in dev/CI today, per
`IMPLEMENTATION_STATUS.md`'s Steps 3.2/3.3 notes) — building it at import
time would break every environment without real credentials, including
this one. A shared, worker-startup-scoped instance is a Phase 8/9
concern once real DI wiring exists.
"""

import asyncio
from typing import Any

from adapters.event_bus.in_memory_event_bus import InMemoryEventBus
from adapters.llm.litellm_adapter import LiteLLMAdapter
from adapters.persistence.database import async_session_factory
from adapters.persistence.document_repo import PostgresDocumentChunkRepository
from adapters.vector_store.pinecone_adapter import PineconeAdapter
from config import llm_config, pinecone_config
from core.domain.document import Document, DocumentChunk
from core.services.embedding_service import EmbeddingService
from workers.celery_app import app


@app.task(name="embedding.embed_and_index_document")  # type: ignore[misc]
# `app.task` resolves to `Any` (celery.* has no stubs, per pyproject.toml's
# ignore_missing_imports override) — mypy strict's disallow_untyped_decorators
# still flags decorating with an Any-typed callable itself.
def embed_and_index_document(
    document_data: dict[str, Any],
    chunk_data: list[dict[str, Any]],
    previous_version_data: dict[str, Any] | None = None,
) -> None:
    """Celery entry point.

    Args:
        document_data: A `Document` serialized via
            `.model_dump(mode="json")` — Celery's default JSON
            serializer can't carry `UUID`/`datetime` objects directly.
        chunk_data: `ChunkerPipeline.process()`'s output, each
            `DocumentChunk` serialized the same way.
        previous_version_data: The document this upload replaces
            (`DocumentService.register_upload()`'s `previous`, Step 7.1),
            serialized the same way, or `None` for a title's first-ever
            upload — files/plan.md Step 7.2.
    """
    document = Document.model_validate(document_data)
    chunks = [DocumentChunk.model_validate(chunk) for chunk in chunk_data]
    previous_version = (
        Document.model_validate(previous_version_data)
        if previous_version_data is not None
        else None
    )
    asyncio.run(_embed_and_index(document, chunks, previous_version))


async def _embed_and_index(
    document: Document, chunks: list[DocumentChunk], previous_version: Document | None
) -> None:
    async with async_session_factory() as session:
        service = EmbeddingService(
            llm=LiteLLMAdapter(),
            vector_store=PineconeAdapter(
                api_key=pinecone_config.api_key or "", index_name=pinecone_config.index_name
            ),
            chunk_repository=PostgresDocumentChunkRepository(session),
            event_bus=InMemoryEventBus(),
            embedding_model=llm_config.embedding_model,
        )
        await service.embed_and_store(chunks, document, previous_version)
        await session.commit()
