from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from structlog.testing import LogCapture

from api.middleware.request_logger import RequestLoggerMiddleware
from api.middleware.tenant_context import TenantContextMiddleware
from config import auth_config
from core.domain.employee import UserRole

_SECRET_KEY = "test-secret-key"
_ALGORITHM = "HS256"


def _token(*, employer_id: UUID | None, role: UserRole = UserRole.EMPLOYEE) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid4()),
        "employer_id": str(employer_id) if employer_id is not None else None,
        "role": role.value,
        "token_type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    encoded: str = jwt.encode(claims, _SECRET_KEY, algorithm=_ALGORITHM)
    return encoded


@contextmanager
def _capture_logs_with_contextvars() -> Generator[list[dict[str, Any]], None, None]:
    """`structlog.testing.capture_logs()` replaces the *entire* processor
    chain with just its capturing processor, which drops
    `merge_contextvars` too -- so fields `RequestLoggerMiddleware` binds
    via `structlog.contextvars` never reach `capture_logs()`'s captured
    entries. This keeps `merge_contextvars` in the chain, ahead of the
    same `LogCapture` processor `capture_logs()` uses, so bound
    contextvars actually show up for assertions."""
    cap = LogCapture()
    old_processors = structlog.get_config()["processors"]
    structlog.configure(processors=[structlog.contextvars.merge_contextvars, cap])
    try:
        yield cap.entries
    finally:
        structlog.configure(processors=old_processors)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(auth_config, "jwt_secret_key", _SECRET_KEY)
    monkeypatch.setattr(auth_config, "jwt_algorithm", _ALGORITHM)

    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware)
    app.add_middleware(TenantContextMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "true"}

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise ValueError("kaboom")

    return TestClient(app, raise_server_exceptions=False)


def test_logs_request_received_and_completed_with_status_and_duration(
    client: TestClient,
) -> None:
    with _capture_logs_with_contextvars() as entries:
        response = client.get("/ping")

    assert response.status_code == 200
    events = [entry["event"] for entry in entries]
    assert "request_received" in events
    assert "request_completed" in events
    completed = next(entry for entry in entries if entry["event"] == "request_completed")
    assert completed["method"] == "GET"
    assert completed["path"] == "/ping"
    assert completed["status_code"] == 200
    assert isinstance(completed["duration_ms"], int)


def test_response_carries_a_correlation_id_header(client: TestClient) -> None:
    with _capture_logs_with_contextvars():
        response = client.get("/ping")

    assert "X-Correlation-ID" in response.headers


def test_incoming_correlation_id_header_is_reused(client: TestClient) -> None:
    with _capture_logs_with_contextvars() as entries:
        response = client.get("/ping", headers={"X-Correlation-ID": "given-id"})

    assert response.headers["X-Correlation-ID"] == "given-id"
    completed = next(entry for entry in entries if entry["event"] == "request_completed")
    assert completed["correlation_id"] == "given-id"


def test_logs_include_employer_id_and_user_id_for_an_authenticated_request(
    client: TestClient,
) -> None:
    employer_id = uuid4()
    token = _token(employer_id=employer_id)

    with _capture_logs_with_contextvars() as entries:
        client.get("/ping", headers={"Authorization": f"Bearer {token}"})

    received = next(entry for entry in entries if entry["event"] == "request_received")
    assert received["employer_id"] == str(employer_id)
    assert "user_id" in received


def test_logs_omit_employer_id_and_user_id_without_a_token(client: TestClient) -> None:
    with _capture_logs_with_contextvars() as entries:
        client.get("/ping")

    received = next(entry for entry in entries if entry["event"] == "request_received")
    assert "employer_id" not in received
    assert "user_id" not in received


def test_an_unhandled_exception_logs_request_failed_and_still_propagates(
    client: TestClient,
) -> None:
    with _capture_logs_with_contextvars() as entries:
        response = client.get("/boom")

    assert response.status_code == 500
    events = [entry["event"] for entry in entries]
    assert "request_failed" in events
    assert "request_completed" not in events
    failed = next(entry for entry in entries if entry["event"] == "request_failed")
    assert failed["path"] == "/boom"


def test_contextvars_do_not_leak_between_requests(client: TestClient) -> None:
    first_employer_id = uuid4()
    token = _token(employer_id=first_employer_id)
    with _capture_logs_with_contextvars() as entries:
        client.get("/ping", headers={"Authorization": f"Bearer {token}"})
        client.get("/ping")

    received_entries = [entry for entry in entries if entry["event"] == "request_received"]
    assert received_entries[0]["employer_id"] == str(first_employer_id)
    assert "employer_id" not in received_entries[1]
