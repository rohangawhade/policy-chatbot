import time

import pytest

from adapters.cache.in_memory_cache_adapter import InMemoryCacheAdapter
from core.ports.cache_port import CachePort


def test_is_a_cache_port() -> None:
    assert isinstance(InMemoryCacheAdapter(), CachePort)


async def test_get_returns_none_for_a_missing_key() -> None:
    result = await InMemoryCacheAdapter().get("missing-key")

    assert result is None


async def test_set_then_get_returns_the_stored_value() -> None:
    cache = InMemoryCacheAdapter()

    await cache.set("some-key", "some-value")

    assert await cache.get("some-key") == "some-value"


async def test_set_overwrites_a_previously_stored_value() -> None:
    cache = InMemoryCacheAdapter()

    await cache.set("some-key", "first-value")
    await cache.set("some-key", "second-value")

    assert await cache.get("some-key") == "second-value"


async def test_delete_removes_a_stored_value() -> None:
    cache = InMemoryCacheAdapter()
    await cache.set("some-key", "some-value")

    await cache.delete("some-key")

    assert await cache.get("some-key") is None


async def test_delete_on_a_missing_key_does_not_raise() -> None:
    await InMemoryCacheAdapter().delete("never-set-key")


async def test_exists_is_true_for_a_stored_key() -> None:
    cache = InMemoryCacheAdapter()
    await cache.set("some-key", "some-value")

    assert await cache.exists("some-key") is True


async def test_exists_is_false_for_a_missing_key() -> None:
    assert await InMemoryCacheAdapter().exists("missing-key") is False


async def test_a_value_with_no_ttl_never_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = InMemoryCacheAdapter()
    clock = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: clock)

    await cache.set("some-key", "some-value")
    clock += 10_000

    assert await cache.get("some-key") == "some-value"


async def test_a_value_expires_after_its_ttl_elapses(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = InMemoryCacheAdapter()
    clock = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: clock)

    await cache.set("some-key", "some-value", ttl_seconds=60)
    clock += 61

    assert await cache.get("some-key") is None


async def test_a_value_is_still_present_just_before_its_ttl_elapses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = InMemoryCacheAdapter()
    clock = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: clock)

    await cache.set("some-key", "some-value", ttl_seconds=60)
    clock += 59

    assert await cache.get("some-key") == "some-value"


async def test_exists_reflects_ttl_expiration_too(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = InMemoryCacheAdapter()
    clock = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: clock)

    await cache.set("some-key", "some-value", ttl_seconds=60)
    clock += 61

    assert await cache.exists("some-key") is False
