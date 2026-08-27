import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import error_handlers
from api.error_handlers import register_exception_handlers
from core.domain.errors import (
    AuthenticationError,
    AuthorizationError,
    DocumentProcessingError,
    DomainError,
    ModelUnavailableError,
    NotFoundError,
    PolicyPalError,
    RateLimitError,
    TenantAccessError,
    UnsupportedFormatError,
)


class _UnmappedError(PolicyPalError):
    """A `PolicyPalError` subclass with no entry of its own in
    `_STATUS_BY_ERROR` -- exercises the base-class catch-all."""


def _client_raising(exc: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (AuthenticationError("bad auth", code="bad_auth"), 401),
        (AuthorizationError("nope", code="authorization_error"), 403),
        (TenantAccessError("cross tenant", code="tenant_access_error"), 403),
        (NotFoundError("Thing not found.", code="not_found"), 404),
        (RateLimitError("slow down", code="rate_limit_exceeded"), 429),
        (ModelUnavailableError("no model", code="model_unavailable"), 503),
        (DocumentProcessingError("bad doc", code="doc_processing_error"), 422),
        (UnsupportedFormatError("csv"), 422),
        (DomainError("business rule broken", code="domain_error"), 400),
        (_UnmappedError("unmapped", code="unmapped"), 400),
    ],
)
def test_policy_pal_error_subclasses_map_to_the_right_status(
    exc: Exception, expected_status: int
) -> None:
    client = _client_raising(exc)

    response = client.get("/boom")

    assert response.status_code == expected_status
    assert response.json() == {"detail": exc.args[0]}


def test_unhandled_non_policypal_exception_returns_a_safe_generic_500() -> None:
    client = _client_raising(ValueError("some internal detail"))

    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "An unexpected error occurred. Please try again later."}
    assert "some internal detail" not in response.text


async def test_policy_pal_error_handler_rejects_a_non_policypal_exception() -> None:
    handler = error_handlers._make_policy_pal_error_handler(400)

    with pytest.raises(TypeError, match="expected a PolicyPalError"):
        await handler(None, ValueError("not a domain error"))  # type: ignore[arg-type]
