"""Abstraction over LLM generation and embedding. LiteLLM already unifies
providers, but our own LLMPort wraps even LiteLLM — so the entire LLM
layer is replaceable (files/plan.md's Strategy Pattern for LLMs)."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class UsageCost:
    """Token counts and estimated USD cost for one generation call
    (files/coding-standards.md section 12's `LLMCostLog` fields)."""

    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


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
    async def embed(
        self, texts: list[str], *, model: str, input_type: str = "passage"
    ) -> list[list[float]]:
        """Embed a batch of texts, one vector per input, same order.

        `input_type` distinguishes asymmetric embedding of a document
        being indexed ("passage", the default) from a search query
        ("query") — some embedding models (Pinecone's `llama-text-embed-v2`
        included) embed each differently for better retrieval quality.
        Implementations without that concept (e.g. a generic LiteLLM
        embedding call) accept and ignore it.
        """
        ...

    @abstractmethod
    async def estimate_cost(self, model: str, prompt: str, completion: str) -> UsageCost:
        """Token-count `prompt`/`completion` and estimate USD cost for
        `model` (files/plan.md Step 6.5's `LLMCostLog` requirement).

        Provider-specific pricing lookups belong behind this port, same
        as token counting — a `core/services/` caller (e.g. `RAGService`)
        must not import a provider SDK directly to compute either.
        """
        ...
