"""Celery task: embeds a document's already-chunked text, indexes it in
the vector store, and persists chunk references (files/plan.md Step
4.4). Thin by design — the actual logic lives in `EmbeddingService`
(core/services/); this module only wires up concrete adapters, bridges
into Celery's synchronous task model, and owns the request-scoped DB
session (a Celery task plays the same "commit here" role the API layer
plays for HTTP requests — files/coding-standards.md's Unit of Work rule;
`PostgresRepository` never commits on its own, only flushes).

Adapters are constructed fresh per task invocation rather than shared at
module level — a shared, worker-startup-scoped instance is a Phase 8/9
concern once real DI wiring exists. `PineconeAdapter`'s `api_key` falls
back to `"unconfigured"`, never `""`: the Pinecone SDK treats an empty
string as falsy and falls through to reading `PINECONE_API_KEY` from the
environment itself, raising `PineconeConfigurationError` at
*construction* if that's unset too (no key at all in dev/CI today, per
`IMPLEMENTATION_STATUS.md`'s Steps 3.2/3.3 notes) — a real bug an
earlier version of this fallback had, found via Step 9.2's test suite.
"""

import asyncio
from typing import Any

from adapters.event_bus.in_memory_event_bus import InMemoryEventBus
from adapters.llm.litellm_adapter import LiteLLMAdapter
from adapters.persistence.database import async_session_factory, engine
from adapters.persistence.document_repo import PostgresDocumentChunkRepository
from adapters.vector_store.pinecone_adapter import PineconeAdapter
from config import llm_config, pinecone_config
from core.domain.document import Document, DocumentChunk
from core.services.embedding_service import EmbeddingService
from workers.celery_app import app


@app.task(
    name="embedding.embed_and_index_document",
    # Whole-attempt retry (Step 8.1) — broader in scope than the
    # per-call tenacity retries already inside LiteLLMAdapter/
    # PineconeAdapter/PostgresDocumentChunkRepository (those absorb a
    # single flaky network call; this absorbs the task attempt as a
    # whole, e.g. a worker restart mid-run) — 3 attempts, exponential
    # backoff, matching this app's existing retry-ceiling convention.
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)  # type: ignore[misc]
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
    try:
        async with async_session_factory() as session:
            service = EmbeddingService(
                llm=LiteLLMAdapter(),
                vector_store=PineconeAdapter(
                    api_key=pinecone_config.api_key or "unconfigured",
                    index_name=pinecone_config.index_name,
                ),
                chunk_repository=PostgresDocumentChunkRepository(session),
                event_bus=InMemoryEventBus(),
                embedding_model=llm_config.embedding_model,
            )
            await service.embed_and_store(chunks, document, previous_version)
            await session.commit()
    finally:
        # `engine` (adapters/persistence/database.py) is a module-level
        # singleton shared across every task this worker process ever
        # runs, but each task gets its own fresh event loop via
        # `asyncio.run()` (below) — an asyncpg connection checked back
        # into the pool at the end of *this* loop is bound to it, and
        # reusing it from the next task's *different* loop fails with
        # "attached to a different loop" / "another operation is in
        # progress". Disposing here leaves the pool empty for the next
        # task, which then opens fresh connections on its own loop.
        # Real bug, not a hypothetical — found via Step 9.3's real-stack
        # validation the moment a real worker processed two tasks in a
        # row; invisible in every unit test (each test's own `db_session`
        # fixture builds a throwaway engine, Step 3.5) and in this file's
        # own prior "verified against the real stack" pass (Step 4.4),
        # which only ever ran a single task per worker lifetime.
        await engine.dispose()
