"""In-process implementation of `CachePort` for local dev/testing without
a running Redis instance.

TTL is enforced lazily (checked on access, no background eviction
thread) — fine for dev/testing, not a substitute for `RedisCacheAdapter`
in production, which is the reason this isn't the module-level default.
"""

import time

from core.ports.cache_port import CachePort


class InMemoryCacheAdapter(CachePort):
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds is not None else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def delete_by_prefix(self, prefix: str) -> None:
        for key in [key for key in self._store if key.startswith(prefix)]:
            del self._store[key]
