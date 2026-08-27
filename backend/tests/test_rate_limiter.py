import pytest

from api.middleware import rate_limiter as rate_limiter_module
from api.middleware.rate_limiter import RateLimiter
from core.domain.errors import RateLimitError


class _FakeRedisClient:
    """Re-implements the Lua sliding-window script's exact semantics in
    pure Python (evict-by-score, count, conditional add) -- not just a
    call recorder -- so these tests exercise `RateLimiter.check()`'s real
    allow/deny behavior, the same way `test_redis_cache_adapter.py`'s
    fake simulates real get/set/exists semantics rather than a live
    Redis. A real Redis's Lua VM isn't available in CI (`ci.yml` runs no
    redis service, only postgres, per Step 3.5's precedent) -- validated
    against a real instance separately, see IMPLEMENTATION_STATUS.md.
    """

    def __init__(self) -> None:
        self._store: dict[str, list[tuple[float, str]]] = {}
        self.eval_calls: list[tuple[str, int, tuple[str, ...]]] = []

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> str:
        self.eval_calls.append((script, numkeys, keys_and_args))
        key, now_arg, window_arg, limit_arg, member = keys_and_args
        now = float(now_arg)
        window = float(window_arg)
        limit = int(limit_arg)

        entries = self._store.setdefault(key, [])
        entries[:] = [(score, m) for score, m in entries if score > now - window]
        if len(entries) >= limit:
            return "0"
        entries.append((now, member))
        return "1"


def _make_limiter(
    monkeypatch: pytest.MonkeyPatch, *, max_requests: int = 3, window_seconds: int = 60
) -> tuple[RateLimiter, _FakeRedisClient]:
    fake_client = _FakeRedisClient()
    monkeypatch.setattr(rate_limiter_module.Redis, "from_url", lambda *a, **kw: fake_client)
    limiter = RateLimiter(
        "redis://localhost:6379/0", max_requests=max_requests, window_seconds=window_seconds
    )
    return limiter, fake_client


async def test_first_request_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter, _ = _make_limiter(monkeypatch)

    await limiter.check("user-1")  # does not raise


async def test_requests_up_to_the_limit_are_all_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter, _ = _make_limiter(monkeypatch, max_requests=3)

    for _ in range(3):
        await limiter.check("user-1")  # does not raise


async def test_a_request_beyond_the_limit_raises_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter, _ = _make_limiter(monkeypatch, max_requests=3)
    for _ in range(3):
        await limiter.check("user-1")

    with pytest.raises(RateLimitError) as exc_info:
        await limiter.check("user-1")

    assert exc_info.value.code == "rate_limit_exceeded"
    assert "3 requests per 60s" in exc_info.value.message


async def test_different_keys_have_independent_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter, _ = _make_limiter(monkeypatch, max_requests=1)

    await limiter.check("user-1")
    await limiter.check("user-2")  # a different key -- not affected by user-1's usage


async def test_a_request_outside_the_window_is_allowed_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter, _ = _make_limiter(monkeypatch, max_requests=1, window_seconds=60)
    now = [1_000_000.0]
    monkeypatch.setattr(rate_limiter_module.time, "time", lambda: now[0])

    await limiter.check("user-1")
    with pytest.raises(RateLimitError):
        await limiter.check("user-1")

    now[0] += 61  # past the 60s window -- the earlier request is evicted
    await limiter.check("user-1")  # does not raise


async def test_eval_is_called_with_the_redis_namespaced_key_and_string_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter, client = _make_limiter(monkeypatch, max_requests=5, window_seconds=30)

    await limiter.check("user-1")

    assert len(client.eval_calls) == 1
    _script, numkeys, args = client.eval_calls[0]
    assert numkeys == 1
    key, now_arg, window_arg, limit_arg, member = args
    assert key == "rate_limit:user-1"
    assert window_arg == "30"
    assert limit_arg == "5"
    assert isinstance(now_arg, str)
    assert isinstance(member, str)
