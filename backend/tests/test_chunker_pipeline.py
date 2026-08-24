from collections.abc import AsyncIterator
from uuid import uuid4

from adapters.chunking.chunker_pipeline import ChunkerPipeline
from adapters.chunking.metadata_extractor import MetadataExtractor
from adapters.chunking.semantic_chunker import SemanticChunker
from core.domain.document import Document, DocumentStatus
from core.ports.llm_port import LLMPort

_MODEL = "mock-embedding-model"


class ConstantEmbeddingLLM(LLMPort):
    """Every text embeds to the same vector, so `SemanticChunker` never
    detects a topic boundary — isolates these tests from chunking-algorithm
    nuances (covered by `test_semantic_chunker.py`) and keeps them focused
    on `ChunkerPipeline`'s own orchestration/enrichment."""

    async def generate(
        self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
    ) -> str:
        raise NotImplementedError

    async def generate_stream(
        self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
    ) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""  # pragma: no cover

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _pipeline(target_tokens: int = 500) -> ChunkerPipeline:
    chunker = SemanticChunker(ConstantEmbeddingLLM(), _MODEL, target_tokens=target_tokens)
    return ChunkerPipeline(MetadataExtractor(), chunker)


def _document() -> Document:
    return Document(
        employer_id=uuid4(),
        title="Summary Plan Description",
        source_type="pdf",
        source_path="s3://bucket/spd.pdf",
        status=DocumentStatus.PROCESSING,
    )


async def test_empty_text_produces_no_chunks() -> None:
    document = _document()

    chunks = await _pipeline().process("   ", document)

    assert chunks == []


async def test_single_section_produces_one_enriched_chunk() -> None:
    document = _document()

    chunks = await _pipeline().process("Your annual deductible is $500.", document)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.document_id == document.id
    assert chunk.employer_id == document.employer_id
    assert chunk.chunk_index == 0
    assert chunk.text == "Your annual deductible is $500."
    assert chunk.section_title is None
    assert chunk.page_number is None
    assert chunk.is_active is True


async def test_chunk_indices_are_sequential_and_zero_based() -> None:
    document = _document()
    text = "ELIGIBILITY\nWho can enroll.\fCOVERAGE\nWhat is covered."

    chunks = await _pipeline().process(text, document)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert len(chunks) >= 2


async def test_section_title_and_page_number_propagate_from_extraction() -> None:
    document = _document()
    text = "ELIGIBILITY\nWho can enroll.\fCOVERAGE\nWhat is covered."

    chunks = await _pipeline().process(text, document)

    assert [(c.section_title, c.page_number) for c in chunks] == [
        ("ELIGIBILITY", 1),
        ("COVERAGE", 2),
    ]


async def test_every_chunk_shares_the_same_document_and_employer_id() -> None:
    document = _document()
    text = "ELIGIBILITY\nWho can enroll.\fCOVERAGE\nWhat is covered."

    chunks = await _pipeline().process(text, document)

    assert all(c.document_id == document.id for c in chunks)
    assert all(c.employer_id == document.employer_id for c in chunks)
