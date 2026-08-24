"""Splits section text into semantically-coherent chunks by detecting
topic shifts between consecutive sentences via embedding similarity
(files/plan.md Step 4.2).
"""

import math
import re
from dataclasses import dataclass

from litellm.utils import token_counter

from adapters.chunking.metadata_extractor import ExtractedSection
from core.ports.llm_port import LLMPort

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_TOKEN_COUNTING_MODEL = "gpt-3.5-turbo"


@dataclass(frozen=True)
class SemanticChunk:
    """A semantically-bounded slice of one `ExtractedSection`, ready for
    Step 4.3's `ChunkerPipeline` to enrich into a full `DocumentChunk`.

    Attributes:
        section_title: Inherited from the source `ExtractedSection`.
        page_number: Inherited from the source `ExtractedSection`.
        text: This chunk's text — one or more sentences, joined.
    """

    section_title: str | None
    page_number: int | None
    text: str


class SemanticChunker:
    """Splits section text into ~target-size chunks, preferring to break
    at sentence-embedding topic shifts over mid-topic cuts.

    Token counts use `litellm.token_counter()` against a fixed reference
    model (`gpt-3.5-turbo`) — an estimate, not an exact count for whatever
    model the resulting chunks are eventually embedded/generated with;
    plan.md's ~400-600 token target is itself approximate.

    Attributes:
        llm: Used only for `embed()` — sentence embeddings to detect
            topic boundaries.
        embedding_model: Model name passed to every `embed()` call
            (caller-driven, same pattern as `LiteLLMAdapter` — this class
            has no opinion on which embedding model is configured).
        target_tokens: Preferred chunk size (files/plan.md: ~400-600).
        overlap_tokens: Trailing tokens of one chunk repeated at the start
            of the next, to preserve cross-boundary context. 0 disables
            overlap entirely.
        similarity_threshold: Consecutive sentences with cosine similarity
            below this are treated as a topic boundary.
    """

    def __init__(
        self,
        llm: LLMPort,
        embedding_model: str,
        target_tokens: int = 500,
        overlap_tokens: int = 50,
        similarity_threshold: float = 0.5,
    ) -> None:
        self._llm = llm
        self._embedding_model = embedding_model
        self._target_tokens = target_tokens
        self._overlap_tokens = overlap_tokens
        self._similarity_threshold = similarity_threshold

    async def chunk(self, sections: list[ExtractedSection]) -> list[SemanticChunk]:
        """Split every section into semantically-bounded chunks.

        Args:
            sections: Output of `MetadataExtractor.extract_sections()`.

        Returns:
            Chunks in document order, each carrying its source section's
            `section_title`/`page_number`.
        """
        chunks: list[SemanticChunk] = []
        for section in sections:
            chunks.extend(await self._chunk_section(section))
        return chunks

    async def _chunk_section(self, section: ExtractedSection) -> list[SemanticChunk]:
        sentences = self._split_sentences(section.text)
        if not sentences:
            return []
        if len(sentences) == 1:
            return [SemanticChunk(section.section_title, section.page_number, sentences[0])]

        boundaries = await self._detect_topic_boundaries(sentences)
        groups = self._group_sentences(sentences, boundaries)
        return [
            SemanticChunk(section.section_title, section.page_number, group) for group in groups
        ]

    def _split_sentences(self, text: str) -> list[str]:
        stripped = text.strip()
        if not stripped:
            return []
        pieces = _SENTENCE_BOUNDARY.split(stripped)
        return [sentence.strip() for sentence in pieces if sentence.strip()]

    async def _detect_topic_boundaries(self, sentences: list[str]) -> set[int]:
        """Sentence indices where a new topic starts. Index 0 is never
        included — the first sentence always starts the first topic."""
        embeddings = await self._llm.embed(sentences, model=self._embedding_model)
        boundaries: set[int] = set()
        for i in range(1, len(sentences)):
            similarity = _cosine_similarity(embeddings[i - 1], embeddings[i])
            if similarity < self._similarity_threshold:
                boundaries.add(i)
        return boundaries

    def _group_sentences(self, sentences: list[str], boundaries: set[int]) -> list[str]:
        groups: list[str] = []
        current = [sentences[0]]
        current_tokens = self._count_tokens(sentences[0])

        for i in range(1, len(sentences)):
            sentence = sentences[i]
            sentence_tokens = self._count_tokens(sentence)
            over_budget = current_tokens + sentence_tokens > self._target_tokens
            if current and (i in boundaries or over_budget):
                groups.append(" ".join(current))
                current = self._overlap_tail(current)
                current_tokens = self._count_tokens(" ".join(current)) if current else 0
            current.append(sentence)
            current_tokens += sentence_tokens

        if current:
            groups.append(" ".join(current))
        return groups

    def _overlap_tail(self, sentences: list[str]) -> list[str]:
        """Trailing sentences to carry into the next chunk, capped at
        `overlap_tokens`. Empty when overlap is disabled."""
        if self._overlap_tokens <= 0:
            return []

        tail: list[str] = []
        tokens = 0
        for sentence in reversed(sentences):
            sentence_tokens = self._count_tokens(sentence)
            if tail and tokens + sentence_tokens > self._overlap_tokens:
                break
            tail.insert(0, sentence)
            tokens += sentence_tokens
        return tail

    def _count_tokens(self, text: str) -> int:
        count: int = token_counter(model=_TOKEN_COUNTING_MODEL, text=text)
        return count


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
