import pytest
from fastapi.testclient import TestClient

from api.routes import health_routes
from main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_check_pinecone_is_not_configured_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes.pinecone_config, "api_key", None)

    assert await health_routes._check_pinecone() == "not_configured"


async def test_check_pinecone_reports_ok_when_configured_and_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeIndexList:
        pass

    class _FakePinecone:
        def __init__(self, api_key: str | None = None) -> None:
            self.api_key = api_key

        def list_indexes(self) -> _FakeIndexList:
            return _FakeIndexList()

    monkeypatch.setattr(health_routes.pinecone_config, "api_key", "fake-key")
    monkeypatch.setattr("pinecone.Pinecone", _FakePinecone)

    assert await health_routes._check_pinecone() == "ok"


async def test_check_pinecone_reports_error_when_configured_but_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingPinecone:
        def __init__(self, api_key: str | None = None) -> None:
            pass

        def list_indexes(self) -> None:
            raise ConnectionError("boom")

    monkeypatch.setattr(health_routes.pinecone_config, "api_key", "fake-key")
    monkeypatch.setattr("pinecone.Pinecone", _FailingPinecone)

    assert await health_routes._check_pinecone() == "error"


async def test_check_database_reports_ok_on_successful_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeConnection:
        async def __aenter__(self) -> "_FakeConnection":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def execute(self, *_args: object, **_kwargs: object) -> None:
            return None

    class _FakeEngine:
        def connect(self) -> _FakeConnection:
            return _FakeConnection()

    monkeypatch.setattr(health_routes, "engine", _FakeEngine())

    assert await health_routes._check_database() == "ok"


async def test_check_database_reports_error_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeEngine:
        def connect(self) -> None:
            raise ConnectionError("boom")

    monkeypatch.setattr(health_routes, "engine", _FakeEngine())

    assert await health_routes._check_database() == "error"


async def test_check_redis_reports_ok_on_successful_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeRedis:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        health_routes.Redis, "from_url", staticmethod(lambda *a, **kw: _FakeRedis())
    )  # type: ignore[misc]

    assert await health_routes._check_redis() == "ok"


async def test_check_redis_reports_error_on_failed_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeRedis:
        async def ping(self) -> bool:
            raise ConnectionError("boom")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        health_routes.Redis, "from_url", staticmethod(lambda *a, **kw: _FakeRedis())
    )  # type: ignore[misc]

    assert await health_routes._check_redis() == "error"


def test_ready_endpoint_returns_200_when_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ok() -> str:
        return "ok"

    async def _not_configured() -> str:
        return "not_configured"

    monkeypatch.setattr(health_routes, "_check_database", _ok)
    monkeypatch.setattr(health_routes, "_check_redis", _ok)
    monkeypatch.setattr(health_routes, "_check_pinecone", _not_configured)

    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"
    assert body["pinecone"] == "not_configured"


def test_ready_endpoint_returns_503_when_database_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _error() -> str:
        return "error"

    async def _ok() -> str:
        return "ok"

    async def _not_configured() -> str:
        return "not_configured"

    monkeypatch.setattr(health_routes, "_check_database", _error)
    monkeypatch.setattr(health_routes, "_check_redis", _ok)
    monkeypatch.setattr(health_routes, "_check_pinecone", _not_configured)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_ready_endpoint_returns_503_when_pinecone_configured_but_erroring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ok() -> str:
        return "ok"

    async def _error() -> str:
        return "error"

    monkeypatch.setattr(health_routes, "_check_database", _ok)
    monkeypatch.setattr(health_routes, "_check_redis", _ok)
    monkeypatch.setattr(health_routes, "_check_pinecone", _error)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["pinecone"] == "error"
