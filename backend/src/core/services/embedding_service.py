"""Embeds and indexes a document's already-chunked text — the last stage
of the chunking/embedding pipeline (files/plan.md Step 4.4). Depends only
on ports, so it's testable without any real LLM, vector store, database,
or event bus (files/coding-standards.md section 1's SRP example names
this exact class as `ChunkerPipeline`'s sibling collaborator).
"""

from typing import Any

from core.domain.document import Document, DocumentChunk
from core.domain.events import DocumentEmbeddedEvent, DocumentVersionReplacedEvent
from core.ports.event_bus_port import EventBusPort
from core.ports.llm_port import LLMPort
from core.ports.repository_ports import DocumentChunkRepository
from core.ports.vector_store_port import VectorRecord, VectorStorePort


class EmbeddingService:
    """Embeds chunk text, upserts it to the vector store, persists chunk
    references for traceability, and publishes completion.

    Attributes:
        llm: Used only for `embed()`.
        vector_store: One Pinecone namespace per employer
            (`document.employer_id`) — files/plan.md's tenant isolation
            strategy.
        chunk_repository: Persists each `DocumentChunk` for traceability.
        event_bus: Publishes `DocumentEmbeddedEvent` on completion.
        embedding_model: Passed to every `embed()` call — this class has
            no opinion on which embedding model is configured, same
            pattern as `SemanticChunker` (Step 4.2).
    """

    def __init__(
        self,
        llm: LLMPort,
        vector_store: VectorStorePort,
        chunk_repository: DocumentChunkRepository,
        event_bus: EventBusPort,
        embedding_model: str,
    ) -> None:
        self._llm = llm
        self._vector_store = vector_store
        self._chunk_repository = chunk_repository
        self._event_bus = event_bus
        self._embedding_model = embedding_model

    async def embed_and_store(
        self,
        chunks: list[DocumentChunk],
        document: Document,
        previous_version: Document | None = None,
    ) -> None:
        """Embed, index, and persist `chunks`, then publish completion.

        Args:
            chunks: Output of `ChunkerPipeline.process()`. An empty list
                is a valid, uneventful completion (not an error) — only
                the completion event is published.
            document: The chunks' source document — supplies
                `employer_id` (the Pinecone namespace) and the
                `document_title`/`policy_type`/`version` fields the
                vector metadata needs (files/plan.md Step 4.1's original
                per-chunk metadata list; `DocumentChunk` itself has no
                columns for them — see Step 4.3's note).
            previous_version: The `Document` row this upload replaces
                (`DocumentService.register_upload()`'s `previous`, Step
                7.1), or `None` for a title's first-ever upload. When
                given, its vectors are purged and its chunk references
                soft-deleted *before* the new document is indexed
                (files/plan.md Step 7.2's ordering), and
                `DocumentVersionReplacedEvent` is published alongside the
                usual `DocumentEmbeddedEvent`.
        """
        if previous_version is not None:
            await self._vector_store.delete_by_metadata(
                str(document.employer_id), {"document_id": str(previous_version.id)}
            )
            await self._chunk_repository.deactivate_by_document(previous_version.id)

        if chunks:
            embeddings = await self._llm.embed(
                [chunk.text for chunk in chunks],
                model=self._embedding_model,
                input_type="passage",
            )
            records = [
                self._to_vector_record(chunk, embedding, document)
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ]
            await self._vector_store.upsert(str(document.employer_id), records)

        for chunk in chunks:
            await self._chunk_repository.create(chunk)

        await self._event_bus.publish(
            DocumentEmbeddedEvent(
                document_id=document.id,
                employer_id=document.employer_id,
                chunk_count=len(chunks),
            )
        )

        if previous_version is not None:
            await self._event_bus.publish(
                DocumentVersionReplacedEvent(
                    document_id=document.id,
                    old_document_id=previous_version.id,
                    employer_id=document.employer_id,
                    old_version=previous_version.version,
                    new_version=document.version,
                )
            )

    def _to_vector_record(
        self, chunk: DocumentChunk, embedding: list[float], document: Document
    ) -> VectorRecord:
        # Vector metadata is intentionally a mix of str/int — Pinecone's
        # own metadata contract (VectorRecord.metadata is dict[str, Any]).
        metadata: dict[str, Any] = {
            "employer_id": str(document.employer_id),
            "document_id": str(document.id),
            "document_title": document.title,
            "document_version": document.version,
            "chunk_index": chunk.chunk_index,
            # Pinecone is the only place a retrieval query gets the chunk's
            # actual content back — DocumentChunk's Postgres row exists for
            # traceability, but a query() match is (id, score, metadata)
            # only, with no join back to Postgres. Chunks are ~400-600
            # tokens, well under Pinecone's per-vector metadata limit.
            "text": chunk.text,
        }
        if document.policy_type is not None:
            metadata["policy_type"] = document.policy_type.value
        if chunk.section_title is not None:
            metadata["section_title"] = chunk.section_title
        if chunk.page_number is not None:
            metadata["page_number"] = chunk.page_number
        return VectorRecord(id=str(chunk.id), values=embedding, metadata=metadata)
