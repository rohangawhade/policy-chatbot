"""Canned implementation of `LLMPort` for local dev and testing without
LLM provider credentials.

Deterministic on purpose: `embed()` derives each vector from a hash of
its input text, so the same text always embeds to the same vector across
calls and processes — retrieval/similarity tests built on top of this
adapter get stable, reproducible results without a real embedding model.
"""

import hashlib
from collections.abc import AsyncIterator

from core.ports.llm_port import LLMPort, UsageCost

_CANNED_RESPONSE = (
    "This is a canned response from PolicyPal's MockLLMAdapter — no real LLM call was made."
)
_EMBEDDING_DIMENSIONS = 16


class MockLLMAdapter(LLMPort):
    async def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        return _CANNED_RESPONSE

    async def generate_stream(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        for word in _CANNED_RESPONSE.split(" "):
            yield f"{word} "

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        return [self._deterministic_vector(text) for text in texts]

    async def estimate_cost(self, model: str, prompt: str, completion: str) -> UsageCost:
        # No real provider pricing in dev/testing — a deterministic,
        # word-count-based estimate with zero cost, so callers exercise
        # the same code path without a real LiteLLM/network dependency.
        return UsageCost(
            input_tokens=len(prompt.split()),
            output_tokens=len(completion.split()),
            estimated_cost_usd=0.0,
        )

    @staticmethod
    def _deterministic_vector(text: str, dimensions: int = _EMBEDDING_DIMENSIONS) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255 for byte in digest[:dimensions]]
