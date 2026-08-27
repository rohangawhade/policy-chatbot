"""Per-user Redis-backed sliding-window rate limiting (files/plan.md
Step 14.3, files/coding-standards.md section 8: "Rate limiting on all
LLM-calling endpoints"). Only `chat_routes.py`'s `send_message` actually
calls an LLM in this codebase today -- guardrails/routing/retrieval all
run before generation, but generation is the expensive, abuse-prone call
this step exists to protect, so only it is rate-limited.

Sliding-window-log algorithm (not the cheaper fixed/rolling-counter
approximation): each request's timestamp becomes a member of a per-key
Redis sorted set; a request is allowed only if fewer than `max_requests`
timestamps remain after evicting everything older than `window_seconds`.
Implemented as a single Lua script (`EVAL`) so the evict-count-add
sequence runs atomically on the Redis side -- a plain read-then-write
from Python would leave a check-then-act race between two concurrent
requests from the same key, letting both through even at the limit.
"""

import time
from uuid import uuid4

from redis.asyncio import Redis

from core.domain.errors import RateLimitError

_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window)
return 1
"""


class RateLimiter:
    """Sliding-window rate limiter over an arbitrary string key (a user
    id, an IP, etc.) -- this class has no opinion on what the key means,
    the same "caller decides" pattern as every other adapter's cache-key
    handling in this codebase (e.g. `RedisCacheAdapter`).

    Attributes:
        max_requests: Requests allowed per `window_seconds`.
        window_seconds: The sliding window's width.
    """

    def __init__(self, redis_url: str, *, max_requests: int, window_seconds: int) -> None:
        self._redis: Redis = Redis.from_url(redis_url, decode_responses=True)
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def check(self, key: str) -> None:
        """Raises `RateLimitError` if `key` has already made
        `max_requests` requests within the trailing `window_seconds`."""
        now = time.time()
        # `redis.asyncio.Redis.eval`'s stub types its return as
        # `Awaitable[str] | str` (shared with the sync client, which
        # returns `str` directly) -- for the real async client this is
        # always a coroutine, never a bare `str`, so mypy's `await`
        # check here is a stub inaccuracy, not a genuine ambiguity.
        result = await self._redis.eval(  # type: ignore[misc]
            _SLIDING_WINDOW_SCRIPT,
            1,
            f"rate_limit:{key}",
            str(now),
            str(self._window_seconds),
            str(self._max_requests),
            f"{now}:{uuid4()}",
        )
        if not int(result):
            raise RateLimitError(
                f"Rate limit exceeded: max {self._max_requests} requests per "
                f"{self._window_seconds}s. Please slow down and try again shortly.",
                code="rate_limit_exceeded",
            )
