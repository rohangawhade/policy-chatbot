import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from tenacity.wait import wait_exponential_jitter

from adapters.cache.redis_cache_adapter import RedisCacheAdapter
from config import retry_config
from core.ports.cache_port import CachePort


class _FakeRedisClient:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.set_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.exists_calls: list[str] = []
        self.scan_iter_calls: list[str] = []
        self.get_return: str | None = None
        self.exists_return: int = 0
        self.scan_iter_return: list[str] = []
        self.get_side_effect: BaseException | None = None
        self.set_side_effect: BaseException | None = None
        self.scan_iter_side_effect: BaseException | None = None

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        if self.get_side_effect is not None:
            raise self.get_side_effect
        return self.get_return

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.set_calls.append({"key": key, "value": value, "ex": ex})
        if self.set_side_effect is not None:
            raise self.set_side_effect

    async def delete(self, *keys: str) -> None:
        self.delete_calls.extend(keys)

    async def exists(self, key: str) -> int:
        self.exists_calls.append(key)
        return self.exists_return

    async def scan_iter(self, match: str | None = None) -> AsyncIterator[str]:
        self.scan_iter_calls.append(match or "")
        if self.scan_iter_side_effect is not None:
            raise self.scan_iter_side_effect
        for key in self.scan_iter_return:
            yield key


@pytest.fixture(autouse=True)
def _no_real_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


def _make_adapter(monkeypatch: pytest.MonkeyPatch) -> tuple[RedisCacheAdapter, _FakeRedisClient]:
    fake_client = _FakeRedisClient()

    import adapters.cache.redis_cache_adapter as module

    monkeypatch.setattr(module.Redis, "from_url", lambda *args, **kwargs: fake_client)
    adapter = RedisCacheAdapter(url="redis://localhost:6379/0")
    return adapter, fake_client


def _connection_error() -> RedisConnectionError:
    return RedisConnectionError("connection refused")


def test_is_a_cache_port(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _make_adapter(monkeypatch)
    assert isinstance(adapter, CachePort)


def test_get_retry_is_sourced_from_retry_config_not_hardcoded() -> None:
    retrying = RedisCacheAdapter.get.retry

    assert retrying.stop.max_attempt_number == retry_config.redis_max_attempts
    assert isinstance(retrying.wait, wait_exponential_jitter)
    assert retrying.wait.initial == retry_config.base_delay_seconds
    assert retrying.wait.max == retry_config.max_delay_seconds


async def test_get_returns_the_cached_value(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.get_return = "cached response"

    result = await adapter.get("some-key")

    assert result == "cached response"
    assert client.get_calls == ["some-key"]


async def test_get_returns_none_on_a_cache_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.get_return = None

    result = await adapter.get("missing-key")

    assert result is None


async def test_get_retries_on_a_retryable_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    call_count = 0

    async def _flaky_get(key: str) -> str | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _connection_error()
        return "recovered"

    client.get = _flaky_get  # type: ignore[method-assign]

    result = await adapter.get("some-key")

    assert result == "recovered"
    assert call_count == 2


async def test_get_gives_up_after_three_attempts_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.get_side_effect = _connection_error()

    with pytest.raises(RedisConnectionError):
        await adapter.get("some-key")

    assert len(client.get_calls) == 3


async def test_get_does_not_retry_a_non_retryable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.get_side_effect = ValueError("bad request")

    with pytest.raises(ValueError, match="bad request"):
        await adapter.get("some-key")

    assert len(client.get_calls) == 1


async def test_set_passes_through_value_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)

    await adapter.set("some-key", "some-value", ttl_seconds=3600)

    assert client.set_calls == [{"key": "some-key", "value": "some-value", "ex": 3600}]


async def test_set_with_no_ttl_passes_none_for_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)

    await adapter.set("some-key", "some-value")

    assert client.set_calls == [{"key": "some-key", "value": "some-value", "ex": None}]


async def test_set_gives_up_after_three_attempts_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.set_side_effect = _connection_error()

    with pytest.raises(RedisConnectionError):
        await adapter.set("some-key", "some-value")

    assert len(client.set_calls) == 3


async def test_delete_calls_through_to_the_client(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)

    await adapter.delete("some-key")

    assert client.delete_calls == ["some-key"]


async def test_exists_returns_true_when_the_key_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.exists_return = 1

    assert await adapter.exists("some-key") is True


async def test_exists_returns_false_when_the_key_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.exists_return = 0

    assert await adapter.exists("some-key") is False


async def test_delete_by_prefix_scans_with_a_wildcard_and_deletes_every_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.scan_iter_return = ["rag_response:emp-1:dental:abc", "rag_response:emp-1:dental:def"]

    await adapter.delete_by_prefix("rag_response:emp-1:dental:")

    assert client.scan_iter_calls == ["rag_response:emp-1:dental:*"]
    assert client.delete_calls == [
        "rag_response:emp-1:dental:abc",
        "rag_response:emp-1:dental:def",
    ]


async def test_delete_by_prefix_with_no_matches_does_not_call_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.scan_iter_return = []

    await adapter.delete_by_prefix("no-match:")

    assert client.delete_calls == []


async def test_delete_by_prefix_retries_on_a_retryable_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    call_count = 0

    async def _flaky_scan_iter(match: str | None = None) -> AsyncIterator[str]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _connection_error()
        yield "recovered-key"

    client.scan_iter = _flaky_scan_iter  # type: ignore[method-assign]

    await adapter.delete_by_prefix("some-prefix:")

    assert call_count == 2
    assert client.delete_calls == ["recovered-key"]


async def test_delete_by_prefix_gives_up_after_three_attempts_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.scan_iter_side_effect = _connection_error()

    with pytest.raises(RedisConnectionError):
        await adapter.delete_by_prefix("some-prefix:")

    assert len(client.scan_iter_calls) == 3


async def test_delete_by_prefix_does_not_retry_a_non_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.scan_iter_side_effect = ValueError("bad request")

    with pytest.raises(ValueError, match="bad request"):
        await adapter.delete_by_prefix("some-prefix:")

    assert len(client.scan_iter_calls) == 1
