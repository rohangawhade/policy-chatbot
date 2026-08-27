import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import litellm
import pytest
from litellm.exceptions import APIConnectionError
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.types.utils import (
    Choices,
    Delta,
    EmbeddingResponse,
    Message,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
)
from tenacity.wait import wait_exponential_jitter

from adapters.llm.litellm_adapter import LiteLLMAdapter
from config import retry_config
from core.ports.llm_port import LLMPort


@pytest.fixture(autouse=True)
def _no_real_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


def _connection_error() -> APIConnectionError:
    return APIConnectionError("boom", llm_provider="test-provider", model="test-model")


def test_is_an_llm_port() -> None:
    assert isinstance(LiteLLMAdapter(), LLMPort)


def test_generation_retry_is_sourced_from_retry_config_not_hardcoded() -> None:
    retrying = LiteLLMAdapter.generate.retry

    assert retrying.stop.max_attempt_number == retry_config.llm_generation_max_attempts
    assert isinstance(retrying.wait, wait_exponential_jitter)
    assert retrying.wait.initial == retry_config.base_delay_seconds
    assert retrying.wait.max == retry_config.max_delay_seconds


def test_embedding_retry_is_sourced_from_retry_config_not_hardcoded() -> None:
    retrying = LiteLLMAdapter.embed.retry

    assert retrying.stop.max_attempt_number == retry_config.llm_embedding_max_attempts
    assert isinstance(retrying.wait, wait_exponential_jitter)


async def test_generate_returns_the_message_content_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = ModelResponse(choices=[Choices(message=Message(content="hello there"))])
    mock_acompletion = AsyncMock(return_value=response)
    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)

    result = await LiteLLMAdapter().generate("hi", model="test-model")

    assert result == "hello there"
    mock_acompletion.assert_awaited_once()
    assert mock_acompletion.await_args.kwargs["stream"] is False


async def test_generate_returns_empty_string_when_content_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = ModelResponse(choices=[Choices(message=Message(content=None))])
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(return_value=response))

    result = await LiteLLMAdapter().generate("hi", model="test-model")

    assert result == ""


async def test_generate_retries_on_a_retryable_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = ModelResponse(choices=[Choices(message=Message(content="recovered"))])
    mock_acompletion = AsyncMock(side_effect=[_connection_error(), response])
    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)

    result = await LiteLLMAdapter().generate("hi", model="test-model")

    assert result == "recovered"
    assert mock_acompletion.await_count == 2


async def test_generate_gives_up_after_three_attempts_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_acompletion = AsyncMock(side_effect=_connection_error())
    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)

    with pytest.raises(APIConnectionError):
        await LiteLLMAdapter().generate("hi", model="test-model")

    assert mock_acompletion.await_count == 3


async def test_generate_does_not_retry_a_non_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_acompletion = AsyncMock(side_effect=ValueError("bad request"))
    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)

    with pytest.raises(ValueError, match="bad request"):
        await LiteLLMAdapter().generate("hi", model="test-model")

    assert mock_acompletion.await_count == 1


async def test_generate_raises_type_error_when_litellm_returns_a_streaming_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_stream = MagicMock(spec=CustomStreamWrapper)
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(return_value=fake_stream))

    with pytest.raises(TypeError, match="non-streaming ModelResponse"):
        await LiteLLMAdapter().generate("hi", model="test-model")


async def test_generate_raises_type_error_when_the_response_choice_is_not_a_choices_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ModelResponse.choices is typed as a Union[Choices, StreamingChoices] —
    # construct the (unexpected in practice) case where the SDK returns a
    # streaming-shaped choice inside a non-streaming response.
    response = ModelResponse(choices=[StreamingChoices(delta=Delta(content="x"))])
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(return_value=response))

    with pytest.raises(TypeError, match="non-streaming Choices"):
        await LiteLLMAdapter().generate("hi", model="test-model")


async def test_generate_stream_yields_only_non_empty_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [
        ModelResponseStream(choices=[StreamingChoices(delta=Delta(content="hel"))]),
        ModelResponseStream(choices=[StreamingChoices(delta=Delta(content=None))]),
        ModelResponseStream(choices=[StreamingChoices(delta=Delta(content="lo"))]),
    ]
    fake_stream: Any = MagicMock(spec=CustomStreamWrapper)
    fake_stream.__aiter__.return_value = iter(chunks)
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(return_value=fake_stream))

    tokens = [token async for token in LiteLLMAdapter().generate_stream("hi", model="test-model")]

    assert tokens == ["hel", "lo"]
    assert litellm.acompletion.await_args.kwargs["stream"] is True


async def test_generate_stream_raises_type_error_when_litellm_returns_a_non_streaming_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = ModelResponse(choices=[Choices(message=Message(content="not a stream"))])
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(return_value=response))

    with pytest.raises(TypeError, match="streaming CustomStreamWrapper"):
        async for _ in LiteLLMAdapter().generate_stream("hi", model="test-model"):
            pass


async def test_generate_stream_retries_establishing_the_stream_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_stream: Any = MagicMock(spec=CustomStreamWrapper)
    fake_stream.__aiter__.return_value = iter(
        [ModelResponseStream(choices=[StreamingChoices(delta=Delta(content="ok"))])]
    )
    mock_acompletion = AsyncMock(side_effect=[_connection_error(), fake_stream])
    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)

    tokens = [token async for token in LiteLLMAdapter().generate_stream("hi", model="test-model")]

    assert tokens == ["ok"]
    assert mock_acompletion.await_count == 2


async def test_embed_returns_one_vector_per_input_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    response = EmbeddingResponse(
        data=[
            {"embedding": [0.1, 0.2], "index": 0, "object": "embedding"},
            {"embedding": [0.3, 0.4], "index": 1, "object": "embedding"},
        ]
    )
    monkeypatch.setattr(litellm, "aembedding", AsyncMock(return_value=response))

    result = await LiteLLMAdapter().embed(["a", "b"], model="test-embed-model")

    assert result == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_retries_at_most_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_aembedding = AsyncMock(side_effect=_connection_error())
    monkeypatch.setattr(litellm, "aembedding", mock_aembedding)

    with pytest.raises(APIConnectionError):
        await LiteLLMAdapter().embed(["a"], model="test-embed-model")

    assert mock_aembedding.await_count == 2


async def test_embed_raises_type_error_on_an_unexpected_response_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = ModelResponse(choices=[Choices(message=Message(content="not an embedding"))])
    monkeypatch.setattr(litellm, "aembedding", AsyncMock(return_value=response))

    with pytest.raises(TypeError, match="EmbeddingResponse"):
        await LiteLLMAdapter().embed(["a"], model="test-embed-model")


async def test_estimate_cost_counts_tokens_and_prices_a_known_model() -> None:
    usage = await LiteLLMAdapter().estimate_cost(
        "claude-haiku-4-5-20251001", "a short prompt", "a short completion"
    )

    assert usage.input_tokens > 0
    assert usage.output_tokens > 0
    assert usage.estimated_cost_usd > 0.0


async def test_estimate_cost_falls_back_to_zero_for_an_unrecognized_model() -> None:
    usage = await LiteLLMAdapter().estimate_cost(
        "totally-unknown-model-xyz", "prompt", "completion"
    )

    assert usage.estimated_cost_usd == 0.0
    assert usage.input_tokens > 0
    assert usage.output_tokens > 0
