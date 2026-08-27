"""Pinecone-backed implementation of `VectorStorePort`.

`pinecone-client` 5.x's `Index` client is synchronous/blocking (no
asyncio variant in this pinned version) — every call here runs it via
`asyncio.to_thread()` so the port stays honestly async without blocking
the event loop (files/coding-standards.md section 9).

One Pinecone namespace per employer for hard tenant isolation
(files/plan.md Step 3.3) — `namespace` is always caller-supplied (from
`current_user.employer_id` once auth/tenancy land in Phase 5), never
invented here.
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

from config import retry_config
from core.ports.vector_store_port import VectorMatch, VectorRecord, VectorStorePort

logger = structlog.get_logger(__name__)

# files/coding-standards.md section 11: retryable transport/availability
# failures only — never retry e.g. an auth or not-found error, which
# fails identically on every attempt.
_RETRYABLE_PINECONE_ERRORS = (ServiceException, ConnectionError, TimeoutError)


def _log_retry(retry_state: RetryCallState) -> None:
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "pinecone_call_retry",
        attempt=retry_state.attempt_number,
        error=str(exception) if exception else None,
    )


# Max attempts + backoff bounds are configurable (files/plan.md Step
# 14.4); default of 3 matches files/coding-standards.md section 11's
# literal ceiling. Exponential backoff with jitter, not the plain
# `wait_exponential` this decorator used before Step 14.4.
_pinecone_retry = retry(
    stop=stop_after_attempt(retry_config.pinecone_max_attempts),
    wait=wait_exponential_jitter(
        initial=retry_config.base_delay_seconds, max=retry_config.max_delay_seconds
    ),
    retry=retry_if_exception_type(_RETRYABLE_PINECONE_ERRORS),
    before_sleep=_log_retry,
    reraise=True,
)


class PineconeAdapter(VectorStorePort):
    def __init__(self, *, api_key: str, index_name: str) -> None:
        self._client = Pinecone(api_key=api_key)
        self._index_name = index_name
        # Resolving an index by name (rather than host) costs a blocking
        # describe_index round trip — done lazily, once, on first use.
        self._index: Any = None

    async def _get_index(self) -> Any:
        if self._index is None:
            self._index = await asyncio.to_thread(self._client.Index, self._index_name)
        return self._index

    @_pinecone_retry
    async def upsert(self, namespace: str, records: list[VectorRecord]) -> None:
        index = await self._get_index()
        vectors = [
            {"id": record.id, "values": record.values, "metadata": record.metadata}
            for record in records
        ]
        await asyncio.to_thread(index.upsert, vectors=vectors, namespace=namespace)

    @_pinecone_retry
    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        index = await self._get_index()
        response = await asyncio.to_thread(
            index.query,
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            filter=metadata_filter,
            include_metadata=True,
        )
        return [
            VectorMatch(id=match.id, score=match.score, metadata=dict(match.metadata or {}))
            for match in response.matches
        ]

    @_pinecone_retry
    async def delete_by_metadata(self, namespace: str, metadata_filter: dict[str, Any]) -> None:
        index = await self._get_index()
        await asyncio.to_thread(index.delete, namespace=namespace, filter=metadata_filter)
