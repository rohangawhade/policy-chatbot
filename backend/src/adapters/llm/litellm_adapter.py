"""LiteLLM-backed implementation of `LLMPort`.

LiteLLM already unifies dozens of provider SDKs behind one call shape;
this adapter wraps LiteLLM itself rather than any single provider client,
so a future non-LiteLLM implementation is a drop-in swap for anything
depending on `LLMPort` — same guarantee `InMemoryEventBus` gives for
`EventBusPort` (files/plan.md's Strategy Pattern for LLMs).

Model selection is entirely caller-driven (`model=` on every call, backed
by `LLMConfig.cheap_model`/`powerful_model`/`embedding_model`) — this
adapter has no opinion about which model tier to use.
"""

from collections.abc import AsyncIterator
from typing import Any

import litellm
import structlog
from litellm.cost_calculator import cost_per_token
from litellm.exceptions import (
    APIConnectionError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.types.utils import Choices, EmbeddingResponse, ModelResponse
from litellm.utils import token_counter
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.ports.llm_port import LLMPort, UsageCost

logger = structlog.get_logger(__name__)

# files/coding-standards.md section 11: retryable transport/availability
# failures only — never retry on e.g. an authentication or bad-request
# error, which will fail identically on every attempt.
_RETRYABLE_LLM_ERRORS = (APIConnectionError, Timeout, RateLimitError, ServiceUnavailableError)


def _log_retry(retry_state: RetryCallState) -> None:
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "llm_call_retry",
        attempt=retry_state.attempt_number,
        error=str(exception) if exception else None,
    )


# Max 3 attempts for generation calls, max 2 for embedding calls
# (files/coding-standards.md section 11).
_generation_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_RETRYABLE_LLM_ERRORS),
    before_sleep=_log_retry,
    reraise=True,
)
_embedding_retry = retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_RETRYABLE_LLM_ERRORS),
    before_sleep=_log_retry,
    reraise=True,
)


class LiteLLMAdapter(LLMPort):
    @_generation_retry
    async def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        if not isinstance(response, ModelResponse):
            got = type(response).__name__
            raise TypeError(f"expected a non-streaming ModelResponse, got {got}")
        choice = response.choices[0]
        if not isinstance(choice, Choices):
            raise TypeError(f"expected a non-streaming Choices, got {type(choice).__name__}")
        return choice.message.content or ""

    async def generate_stream(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        # Retries only cover establishing the stream — once tokens have
        # started reaching the caller, silently restarting would replay
        # or duplicate output, so a mid-stream failure propagates as-is.
        stream = await self._start_stream(
            prompt, model=model, temperature=temperature, max_tokens=max_tokens
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    @_generation_retry
    async def _start_stream(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> CustomStreamWrapper:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        if not isinstance(response, CustomStreamWrapper):
            got = type(response).__name__
            raise TypeError(f"expected a streaming CustomStreamWrapper, got {got}")
        return response

    @_embedding_retry
    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        response = await litellm.aembedding(model=model, input=texts)
        if not isinstance(response, EmbeddingResponse):
            raise TypeError(f"expected an EmbeddingResponse, got {type(response).__name__}")
        # `EmbeddingResponse.data` is declared as an untyped `List` by
        # litellm itself — each item is provider JSON coerced into an
        # `Embedding` object, so `Any` here reflects a genuinely
        # loosely-typed external boundary, not a local typing shortcut.
        items: list[Any] = response.data
        return [[float(value) for value in item["embedding"]] for item in items]

    async def estimate_cost(self, model: str, prompt: str, completion: str) -> UsageCost:
        input_tokens = token_counter(model=model, text=prompt)
        output_tokens = token_counter(model=model, text=completion)
        try:
            input_cost, output_cost = cost_per_token(
                model=model, prompt_tokens=input_tokens, completion_tokens=output_tokens
            )
            estimated_cost_usd = input_cost + output_cost
        except BadRequestError:
            # No pricing data for this model (e.g. a provider litellm
            # doesn't recognize) — best-effort estimate degrades to 0
            # rather than failing the whole generation over a cost figure.
            logger.warning("cost_estimation_unavailable", model=model)
            estimated_cost_usd = 0.0
        return UsageCost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )
