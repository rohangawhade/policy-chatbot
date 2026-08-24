"""Abstraction over the response/query cache. Redis is Phase 3's adapter,
with an in-memory fallback for dev/testing without Redis."""

from abc import ABC, abstractmethod


class CachePort(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None: ...

    @abstractmethod
    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def delete_by_prefix(self, prefix: str) -> None:
        """Delete every key starting with `prefix` — bulk invalidation
        for cases where individual keys aren't known ahead of time (e.g.
        "every cached response for this employer + policy type",
        files/plan.md Step 7.3). Callers own the key-naming convention
        that makes a given prefix meaningful; this port only knows about
        opaque string prefixes, same as every other method here."""
        ...
