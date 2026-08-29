import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from pinecone.exceptions import ServiceException
from tenacity.wait import wait_exponential_jitter

from adapters.llm.litellm_adapter import LiteLLMAdapter
from adapters.llm.pinecone_embedding_adapter import PineconeEmbeddingAdapter
from config import retry_config
from core.ports.llm_port import LLMPort


@dataclass
class _FakeEmbedResponse:
    data: list[dict[str, Any]] = field(default_factory=list)


class _FakeInference:
    def __init__(self) -> None:
        self.embed_calls: list[dict[str, Any]] = []
        self.side_effect: BaseException | None = None
        self.embed_return: _FakeEmbedResponse = _FakeEmbedResponse()

    def embed(
        self, model: str, inputs: list[str], parameters: dict[str, Any]
    ) -> _FakeEmbedResponse:
        self.embed_calls.append({"model": model, "inputs": inputs, "parameters": parameters})
        if self.side_effect is not None:
            raise self.side_effect
        if self.embed_return.data:
            return self.embed_return
        # No preset response -- auto-generate one deterministic vector
        # per input (its length), enough for batching tests to verify
        # order/count without presetting a response for every batch.
        return _FakeEmbedResponse(data=[{"values": [float(len(text))]} for text in inputs])


class _FakePineconeClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.inference = _FakeInference()


@pytest.fixture(autouse=True)
def _no_real_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


def _make_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PineconeEmbeddingAdapter, _FakePineconeClient]:
    fake_client_holder: dict[str, _FakePineconeClient] = {}

    def _fake_pinecone_ctor(api_key: str) -> _FakePineconeClient:
        client = _FakePineconeClient(api_key)
        fake_client_holder["client"] = client
        return client

    import adapters.llm.pinecone_embedding_adapter as module

    monkeypatch.setattr(module, "Pinecone", _fake_pinecone_ctor)
    adapter = PineconeEmbeddingAdapter(pinecone_api_key="test-key")
    return adapter, fake_client_holder["client"]


def test_is_an_llm_port() -> None:
    assert isinstance(PineconeEmbeddingAdapter(pinecone_api_key="k"), LLMPort)


def test_is_a_litellm_adapter_and_inherits_generate_unchanged() -> None:
    # generate/generate_stream/estimate_cost stay exactly LiteLLMAdapter's
    # -- only embed() is overridden -- so Groq keeps working through the
    # same, unmodified generation path.
    assert issubclass(PineconeEmbeddingAdapter, LiteLLMAdapter)
    assert PineconeEmbeddingAdapter.generate is LiteLLMAdapter.generate
    assert PineconeEmbeddingAdapter.generate_stream is LiteLLMAdapter.generate_stream
    assert PineconeEmbeddingAdapter.estimate_cost is LiteLLMAdapter.estimate_cost


def test_embedding_retry_is_sourced_from_retry_config_not_hardcoded() -> None:
    retrying = PineconeEmbeddingAdapter._embed_batch.retry

    assert retrying.stop.max_attempt_number == retry_config.llm_embedding_max_attempts
    assert isinstance(retrying.wait, wait_exponential_jitter)
    assert retrying.wait.initial == retry_config.base_delay_seconds
    assert retrying.wait.max == retry_config.max_delay_seconds


async def test_embed_returns_one_vector_per_input_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.inference.embed_return = _FakeEmbedResponse(
        data=[{"values": [0.1, 0.2]}, {"values": [0.3, 0.4]}]
    )

    result = await adapter.embed(["a", "b"], model="llama-text-embed-v2")

    assert result == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_passes_model_inputs_and_input_type_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.inference.embed_return = _FakeEmbedResponse(data=[{"values": [0.0]}])

    await adapter.embed(["hello"], model="llama-text-embed-v2", input_type="query")

    assert client.inference.embed_calls == [
        {
            "model": "llama-text-embed-v2",
            "inputs": ["hello"],
            "parameters": {"input_type": "query", "truncate": "END"},
        }
    ]


async def test_embed_defaults_input_type_to_passage(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.inference.embed_return = _FakeEmbedResponse(data=[{"values": [0.0]}])

    await adapter.embed(["hello"], model="llama-text-embed-v2")

    assert client.inference.embed_calls[0]["parameters"]["input_type"] == "passage"


async def test_embed_retries_on_a_retryable_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    expected = _FakeEmbedResponse(data=[{"values": [1.0]}])
    call_count = 0

    def _flaky_embed(model: str, inputs: list[str], parameters: dict[str, Any]) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ServiceException(status_code=503, reason="Service Unavailable")
        return expected

    client.inference.embed = _flaky_embed  # type: ignore[method-assign]

    result = await adapter.embed(["hello"], model="llama-text-embed-v2")

    assert result == [[1.0]]
    assert call_count == 2


async def test_embed_gives_up_after_max_attempts_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.inference.side_effect = ServiceException(status_code=503, reason="Service Unavailable")

    with pytest.raises(ServiceException):
        await adapter.embed(["hello"], model="llama-text-embed-v2")

    assert len(client.inference.embed_calls) == retry_config.llm_embedding_max_attempts


async def test_embed_splits_a_large_batch_into_calls_of_at_most_96(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Real, confirmed limit (not assumed): a real ingestion run sent
    # SemanticChunker's boundary-detection embed() call 439 sentences
    # in one batch and got back a real Pinecone
    # "[400 INVALID_ARGUMENT] Input length '439' exceeded inputs limit
    # of 96 for model 'llama-text-embed-v2'" error.
    adapter, client = _make_adapter(monkeypatch)
    texts = [f"sentence-{i}" for i in range(200)]

    result = await adapter.embed(texts, model="llama-text-embed-v2")

    assert len(result) == 200
    batch_sizes = [len(call["inputs"]) for call in client.inference.embed_calls]
    assert batch_sizes == [96, 96, 8]


async def test_embed_preserves_order_across_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)
    texts = [f"{'x' * i}" for i in range(150)]  # length i, so result[i] == [float(i)]

    result = await adapter.embed(texts, model="llama-text-embed-v2")

    assert result == [[float(i)] for i in range(150)]


async def test_embed_of_a_single_batch_makes_exactly_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)

    await adapter.embed(["a", "b", "c"], model="llama-text-embed-v2")

    assert len(client.inference.embed_calls) == 1


async def test_embed_does_not_retry_a_non_retryable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.inference.side_effect = ValueError("bad request")

    with pytest.raises(ValueError, match="bad request"):
        await adapter.embed(["hello"], model="llama-text-embed-v2")

    assert len(client.inference.embed_calls) == 1
