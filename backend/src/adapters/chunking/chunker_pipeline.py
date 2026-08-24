"""Orchestrates the chunking stages: raw text -> structural metadata ->
semantic splitting -> persistable `DocumentChunk`s (files/plan.md Step
4.3). Each stage stays a separate, independently-testable class; this
file only sequences them.
"""

from adapters.chunking.metadata_extractor import MetadataExtractor
from adapters.chunking.semantic_chunker import SemanticChunker
from core.domain.document import Document, DocumentChunk


class ChunkerPipeline:
    """Turns a document's raw extracted text into ordered `DocumentChunk`s.

    Attributes:
        metadata_extractor: Splits raw text into heading/page-bounded
            sections.
        semantic_chunker: Splits each section into ~target-size,
            topic-coherent chunks.
    """

    def __init__(
        self, metadata_extractor: MetadataExtractor, semantic_chunker: SemanticChunker
    ) -> None:
        self._metadata_extractor = metadata_extractor
        self._semantic_chunker = semantic_chunker

    async def process(self, text: str, document: Document) -> list[DocumentChunk]:
        """Chunk `text` and enrich each chunk for persistence.

        `document_title`/`policy_type` (files/plan.md's other two
        per-chunk metadata fields) are not attached here — `DocumentChunk`
        has no such columns; the ingestion task that already holds
        `document` builds Pinecone's vector metadata from it directly.

        Args:
            text: Raw text from `DocumentProcessorPort.extract_text()`.
            document: The `Document` this text belongs to — supplies
                `document_id`/`employer_id` and, via caller context,
                `document_title`/`policy_type` for the vector store.

        Returns:
            `DocumentChunk`s in document order, `chunk_index` 0-based.
        """
        sections = self._metadata_extractor.extract_sections(text)
        semantic_chunks = await self._semantic_chunker.chunk(sections)
        return [
            DocumentChunk(
                document_id=document.id,
                employer_id=document.employer_id,
                chunk_index=index,
                text=chunk.text,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
            )
            for index, chunk in enumerate(semantic_chunks)
        ]
