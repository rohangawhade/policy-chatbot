"""`LiteLLMAdapter` with `embed()` swapped for Pinecone's own inference
API.

Groq (this project's configured LLM provider, via LiteLLM) has no
embedding endpoint of its own -- `generate`/`generate_stream`/
`estimate_cost` are inherited unchanged from `LiteLLMAdapter` (still
fully provider-agnostic; it just happens to be Groq today), so only
`embed()` needs a different backend. `RAGService`/`EmbeddingService`
depend on `LLMPort`, not a concrete class, so swapping this in at the
`dependencies.py`/Celery task wiring is the only change needed
(files/plan.md's Strategy Pattern for LLMs).
"""

import asyncio
from typing import Any

import structlog
from pinecone import Pinecone
from pinecone.exceptions import ServiceException
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from adapters.llm.litellm_adapter import LiteLLMAdapter
from config import retry_config

logger = structlog.get_logger(__name__)

# Pinecone's inference API's own documented/observed ceiling for a
# single `embed()` call's `inputs` list -- confirmed via a real error
# (see `embed()`'s docstring-equivalent comment below), not assumed.
_MAX_BATCH_SIZE = 96

# files/coding-standards.md section 11: retryable transport/availability
# failures only -- same tuple `PineconeAdapter` uses for its own calls,
# since this hits the same SDK/service.
_RETRYABLE_PINECONE_ERRORS = (ServiceException, ConnectionError, TimeoutError)


def _log_retry(retry_state: RetryCallState) -> None:
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "pinecone_embedding_retry",
        attempt=retry_state.attempt_number,
        error=str(exception) if exception else None,
    )


# Reuses the same `RETRY_LLM_EMBEDDING_MAX_ATTEMPTS` ceiling as
# `LiteLLMAdapter.embed()` -- this is still "the embedding attempt
# limit," regardless of which provider backs it.
_embedding_retry = retry(
    stop=stop_after_attempt(retry_config.llm_embedding_max_attempts),
    wait=wait_exponential_jitter(
        initial=retry_config.base_delay_seconds, max=retry_config.max_delay_seconds
    ),
    retry=retry_if_exception_type(_RETRYABLE_PINECONE_ERRORS),
    before_sleep=_log_retry,
    reraise=True,
)


class PineconeEmbeddingAdapter(LiteLLMAdapter):
    def __init__(self, *, pinecone_api_key: str) -> None:
        self._pinecone_client = Pinecone(api_key=pinecone_api_key)

    async def embed(
        self, texts: list[str], *, model: str, input_type: str = "passage"
    ) -> list[list[float]]:
        # Pinecone's inference API caps `inputs` at 96 items per call
        # (confirmed via a real error, not documentation: a real
        # ingestion run of a several-page document sent hundreds of
        # sentences to SemanticChunker's boundary-detection embed()
        # call in one batch and got a real
        # `[400 INVALID_ARGUMENT] Input length '439' exceeded inputs
        # limit of 96 for model 'llama-text-embed-v2'` back) -- unlike
        # LiteLLM's own embedding path (OpenAI et al.), which accepts
        # much larger batches. Chunk into batches of `_MAX_BATCH_SIZE`
        # and concatenate results, order preserved.
        results: list[list[float]] = []
        for start in range(0, len(texts), _MAX_BATCH_SIZE):
            batch = texts[start : start + _MAX_BATCH_SIZE]
            results.extend(await self._embed_batch(batch, model=model, input_type=input_type))
        return results

    @_embedding_retry
    async def _embed_batch(
        self, texts: list[str], *, model: str, input_type: str
    ) -> list[list[float]]:
        # Pinecone's inference client is synchronous/blocking (no asyncio
        # variant) -- run via `asyncio.to_thread()`, same reasoning as
        # `PineconeAdapter`'s own calls (files/coding-standards.md
        # section 9).
        response = await asyncio.to_thread(
            self._pinecone_client.inference.embed,
            model=model,
            inputs=texts,
            parameters={"input_type": input_type, "truncate": "END"},
        )
        items: list[Any] = response.data
        return [[float(value) for value in item["values"]] for item in items]
