from adapters.llm.mock_llm_adapter import MockLLMAdapter
from core.ports.llm_port import LLMPort


def test_is_an_llm_port() -> None:
    assert isinstance(MockLLMAdapter(), LLMPort)


async def test_generate_returns_a_non_empty_canned_string() -> None:
    result = await MockLLMAdapter().generate("what's my deductible?", model="any-model")

    assert isinstance(result, str)
    assert result != ""


async def test_generate_ignores_prompt_and_model_and_is_deterministic() -> None:
    adapter = MockLLMAdapter()

    first = await adapter.generate("prompt one", model="model-a")
    second = await adapter.generate("a completely different prompt", model="model-b")

    assert first == second


async def test_generate_stream_yields_tokens_that_join_back_to_the_canned_response() -> None:
    adapter = MockLLMAdapter()

    tokens = [token async for token in adapter.generate_stream("hi", model="any-model")]
    full_response = await adapter.generate("hi", model="any-model")

    assert len(tokens) > 1
    assert "".join(tokens).strip() == full_response


async def test_embed_returns_one_vector_per_input_text_in_order() -> None:
    vectors = await MockLLMAdapter().embed(["first", "second"], model="any-embed-model")

    assert len(vectors) == 2
    assert all(isinstance(value, float) for vector in vectors for value in vector)


async def test_embed_is_deterministic_for_the_same_text() -> None:
    adapter = MockLLMAdapter()

    first = await adapter.embed(["same text"], model="any-embed-model")
    second = await adapter.embed(["same text"], model="any-embed-model")

    assert first == second


async def test_embed_produces_different_vectors_for_different_text() -> None:
    adapter = MockLLMAdapter()

    vectors = await adapter.embed(["alpha", "beta"], model="any-embed-model")

    assert vectors[0] != vectors[1]


async def test_embed_vectors_have_the_configured_dimensionality() -> None:
    vectors = await MockLLMAdapter().embed(["text"], model="any-embed-model")

    assert len(vectors[0]) == 16
