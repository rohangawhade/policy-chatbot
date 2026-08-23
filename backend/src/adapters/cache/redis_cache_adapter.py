"""Redis-backed implementation of `CachePort`.

Key construction (e.g. a hash of employer_id + query_text + model_tier,
per files/plan.md's caching strategy) is entirely the caller's
responsibility — this adapter only knows about opaque string keys, the
same way `LiteLLMAdapter` has no opinion on model tier. `ttl_seconds`
is likewise caller-supplied per call (`None` means no expiration);
`CacheConfig.ttl_seconds` (Step 1.4) is the default a caller reaches for,
not something this adapter reads itself.
"""

import structlog
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.ports.cache_port import CachePort

logger = structlog.get_logger(__name__)

# files/coding-standards.md section 11 names explicit retry ceilings for
# LLM/Pinecone/embedding calls but not cache calls; 3 attempts matches
# the LLM/Pinecone ceiling as a sane default for the same class of
# transport/availability failure.
_RETRYABLE_REDIS_ERRORS = (RedisConnectionError, RedisTimeoutError)


def _log_retry(retry_state: RetryCallState) -> None:
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "redis_call_retry",
        attempt=retry_state.attempt_number,
        error=str(exception) if exception else None,
    )


_redis_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_RETRYABLE_REDIS_ERRORS),
    before_sleep=_log_retry,
    reraise=True,
)


class RedisCacheAdapter(CachePort):
    def __init__(self, *, url: str) -> None:
        self._client: Redis = Redis.from_url(url, decode_responses=True)

    @_redis_retry
    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)
        return str(value) if value is not None else None

    @_redis_retry
    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        await self._client.set(key, value, ex=ttl_seconds)

    @_redis_retry
    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    @_redis_retry
    async def exists(self, key: str) -> bool:
        count = await self._client.exists(key)
        return bool(count)
