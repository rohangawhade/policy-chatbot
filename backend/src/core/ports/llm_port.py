"""Abstraction over LLM generation and embedding. LiteLLM already unifies
providers, but our own LLMPort wraps even LiteLLM — so the entire LLM
layer is replaceable (files/plan.md's Strategy Pattern for LLMs)."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMPort(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a complete response for `prompt` using `model`."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream response tokens as they're generated.

        Implementations are async generator functions (`async def ...:
        yield token`) — calling one returns an async iterator directly, not
        a coroutine, so callers do `async for token in
        port.generate_stream(...)`, never `await` the call itself.
        """
        yield ""  # pragma: no cover — the yield makes this an async generator

    @abstractmethod
    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        """Embed a batch of texts, one vector per input, same order."""
        ...
