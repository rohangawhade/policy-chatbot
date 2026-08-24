from collections.abc import AsyncIterator

from adapters.chunking.metadata_extractor import ExtractedSection
from adapters.chunking.semantic_chunker import SemanticChunk, SemanticChunker, _cosine_similarity
from core.ports.llm_port import LLMPort

_MODEL = "mock-embedding-model"


class FakeEmbeddingLLM(LLMPort):
    """A test double whose `embed()` returns caller-controlled vectors per
    text, so topic-boundary detection can be exercised deterministically —
    unlike `MockLLMAdapter`'s hash-derived vectors, which carry no
    intentional semantic relationship between texts."""

    def __init__(self, vectors: dict[str, list[float]], default: list[float] | None = None) -> None:
        self._vectors = vectors
        self._default = default
        self.embed_calls: list[list[str]] = []

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
        self.embed_calls.append(texts)
        vectors = []
        for text in texts:
            if text in self._vectors:
                vectors.append(self._vectors[text])
            elif self._default is not None:
                vectors.append(self._default)
            else:
                raise KeyError(f"no vector configured for {text!r}")
        return vectors


def _section(
    text: str, title: str | None = "Eligibility", page: int | None = 1
) -> ExtractedSection:
    return ExtractedSection(section_title=title, page_number=page, text=text)


async def test_empty_section_text_produces_no_chunks() -> None:
    llm = FakeEmbeddingLLM({})
    chunker = SemanticChunker(llm, _MODEL)

    chunks = await chunker.chunk([_section("   ")])

    assert chunks == []


async def test_single_sentence_section_is_one_chunk_without_calling_embed() -> None:
    llm = FakeEmbeddingLLM({})
    chunker = SemanticChunker(llm, _MODEL)

    chunks = await chunker.chunk([_section("You must work 30 hours per week.")])

    assert chunks == [
        SemanticChunk(
            section_title="Eligibility", page_number=1, text="You must work 30 hours per week."
        )
    ]
    assert llm.embed_calls == []


async def test_similar_sentences_stay_in_one_chunk() -> None:
    text = "Employees are eligible after 90 days. Eligibility starts on the first of the month."
    same_vector = [1.0, 0.0, 0.0]
    llm = FakeEmbeddingLLM(
        {
            "Employees are eligible after 90 days.": same_vector,
            "Eligibility starts on the first of the month.": same_vector,
        }
    )
    chunker = SemanticChunker(llm, _MODEL, similarity_threshold=0.5)

    chunks = await chunker.chunk([_section(text)])

    assert len(chunks) == 1
    assert chunks[0].text == text


async def test_dissimilar_sentences_split_into_separate_chunks() -> None:
    text = "Employees are eligible after 90 days. The dental plan covers two cleanings per year."
    llm = FakeEmbeddingLLM(
        {
            "Employees are eligible after 90 days.": [1.0, 0.0],
            "The dental plan covers two cleanings per year.": [0.0, 1.0],
        }
    )
    chunker = SemanticChunker(llm, _MODEL, similarity_threshold=0.5, overlap_tokens=0)

    chunks = await chunker.chunk([_section(text)])

    assert [c.text for c in chunks] == [
        "Employees are eligible after 90 days.",
        "The dental plan covers two cleanings per year.",
    ]


async def test_token_budget_splits_even_without_a_topic_boundary() -> None:
    same_vector = [1.0, 0.0]
    sentence_a = "Employees are eligible after ninety consecutive calendar days of full time work."
    sentence_b = "Coverage begins on the first day of the month following the eligibility date."
    llm = FakeEmbeddingLLM({sentence_a: same_vector, sentence_b: same_vector})
    chunker = SemanticChunker(llm, _MODEL, target_tokens=10, overlap_tokens=0)

    chunks = await chunker.chunk([_section(f"{sentence_a} {sentence_b}")])

    assert [c.text for c in chunks] == [sentence_a, sentence_b]


async def test_overlap_repeats_a_sentence_across_chunk_boundaries() -> None:
    same_vector = [1.0, 0.0]
    sentence_a = "First sentence of the section here."
    sentence_b = "Second sentence adds more detail."
    sentence_c = "Third sentence closes the topic out."
    llm = FakeEmbeddingLLM({s: same_vector for s in (sentence_a, sentence_b, sentence_c)})
    chunker = SemanticChunker(llm, _MODEL, target_tokens=8, overlap_tokens=20)

    chunks = await chunker.chunk([_section(f"{sentence_a} {sentence_b} {sentence_c}")])

    assert len(chunks) >= 2
    all_text = " ".join(c.text for c in chunks)
    assert any(all_text.count(s) > 1 for s in (sentence_a, sentence_b, sentence_c))


async def test_zero_overlap_never_repeats_a_sentence_across_chunks() -> None:
    same_vector = [1.0, 0.0]
    sentence_a = "First sentence of the section here."
    sentence_b = "Second sentence adds more detail."
    sentence_c = "Third sentence closes the topic out."
    llm = FakeEmbeddingLLM({s: same_vector for s in (sentence_a, sentence_b, sentence_c)})
    chunker = SemanticChunker(llm, _MODEL, target_tokens=8, overlap_tokens=0)

    chunks = await chunker.chunk([_section(f"{sentence_a} {sentence_b} {sentence_c}")])

    all_text = " ".join(c.text for c in chunks)
    assert all_text.count(sentence_a) == 1
    assert all_text.count(sentence_b) == 1
    assert all_text.count(sentence_c) == 1


async def test_overlap_tail_stops_once_the_overlap_budget_is_exceeded() -> None:
    same_vector = [1.0, 0.0]
    sentence_a = "Alpha sentence number one here."
    sentence_b = "Bravo sentence number two here."
    sentence_c = "Charlie sentence number three here."
    sentence_d = "Delta sentence number four here."
    sentences = (sentence_a, sentence_b, sentence_c, sentence_d)
    llm = FakeEmbeddingLLM({s: same_vector for s in sentences})
    chunker = SemanticChunker(llm, _MODEL, target_tokens=20, overlap_tokens=10)

    chunks = await chunker.chunk([_section(" ".join(sentences))])

    assert [c.text for c in chunks] == [
        f"{sentence_a} {sentence_b} {sentence_c}",
        f"{sentence_c} {sentence_d}",
    ]


async def test_multiple_sections_each_keep_their_own_title_and_page() -> None:
    llm = FakeEmbeddingLLM({})
    chunker = SemanticChunker(llm, _MODEL)

    sections = [
        _section("Only one sentence here.", title="Eligibility", page=1),
        _section("Only one sentence there.", title="Coverage", page=2),
    ]
    chunks = await chunker.chunk(sections)

    assert [(c.section_title, c.page_number) for c in chunks] == [
        ("Eligibility", 1),
        ("Coverage", 2),
    ]


def test_cosine_similarity_of_identical_vectors_is_one() -> None:
    assert _cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_cosine_similarity_of_orthogonal_vectors_is_zero() -> None:
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_with_a_zero_vector_is_zero() -> None:
    assert _cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
