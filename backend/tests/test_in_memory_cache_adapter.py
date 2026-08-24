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


async def test_delete_by_prefix_removes_only_matching_keys() -> None:
    cache = InMemoryCacheAdapter()
    await cache.set("rag_response:emp-1:dental:abc", "answer-1")
    await cache.set("rag_response:emp-1:dental:def", "answer-2")
    await cache.set("rag_response:emp-1:vision:ghi", "answer-3")
    await cache.set("rag_response:emp-2:dental:jkl", "answer-4")

    await cache.delete_by_prefix("rag_response:emp-1:dental:")

    assert await cache.get("rag_response:emp-1:dental:abc") is None
    assert await cache.get("rag_response:emp-1:dental:def") is None
    assert await cache.get("rag_response:emp-1:vision:ghi") == "answer-3"
    assert await cache.get("rag_response:emp-2:dental:jkl") == "answer-4"


async def test_delete_by_prefix_on_no_matching_keys_does_not_raise() -> None:
    cache = InMemoryCacheAdapter()
    await cache.set("unrelated-key", "value")

    await cache.delete_by_prefix("no-match:")

    assert await cache.get("unrelated-key") == "value"
