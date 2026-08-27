"""Global exception handling for the FastAPI app (files/plan.md Step
14.2, files/coding-standards.md section 6): maps `PolicyPalError`
subclasses to the right HTTP status code, and guarantees nothing else
ever leaks a raw stack trace or internal detail to a client.

Existing `raise HTTPException(...)` call sites across `api/routes/`
(mostly "not found" checks predating this step) are untouched --
FastAPI installs its own default `HTTPException` handler independently
of this module, and it already produces a safe, consistent response.
`PolicyPalError` exists for the layering section 6 actually asks for
("API layer converts domain exceptions to appropriate HTTP status
codes"): a route or service can raise a plain domain exception without
importing `fastapi`/`HTTPException`/`status` at all, and this module
owns turning it into a response -- the 15 pre-existing "not found"
`HTTPException` raises were migrated to `NotFoundError` as this step's
first real caller of the new hierarchy (see IMPLEMENTATION_STATUS.md).
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from core.domain.errors import (
    AuthenticationError,
    AuthorizationError,
    DocumentProcessingError,
    DomainError,
    ModelUnavailableError,
    NotFoundError,
    PolicyPalError,
    RateLimitError,
)

# Every `PolicyPalError` subclass not listed here falls back to whichever
# ancestor *is* listed (Starlette resolves a raised exception's handler by
# walking its MRO -- e.g. `TenantAccessError` -> `AuthorizationError`'s
# entry, `UnsupportedFormatError` -> `DocumentProcessingError`'s entry --
# so those two don't need their own line). `PolicyPalError` itself is the
# catch-all for any future subclass that doesn't fit an existing bucket:
# still a *recognized* app error, so 400 is the right default, not 500.
_STATUS_BY_ERROR: dict[type[PolicyPalError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    AuthorizationError: status.HTTP_403_FORBIDDEN,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    RateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
    ModelUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    DocumentProcessingError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    DomainError: status.HTTP_400_BAD_REQUEST,
    PolicyPalError: status.HTTP_400_BAD_REQUEST,
}


def register_exception_handlers(app: FastAPI) -> None:
    """Call once from `main.py`'s `create_app()`."""
    for error_type, status_code in _STATUS_BY_ERROR.items():
        app.add_exception_handler(error_type, _make_policy_pal_error_handler(status_code))
    # Registering on the bare `Exception` class is special-cased by
    # Starlette (`Starlette.build_middleware_stack` pulls it out as
    # `ServerErrorMiddleware`'s dedicated `handler`, not a normal
    # per-class lookup) -- this is the true last-resort catch for
    # anything not already a `PolicyPalError`/`HTTPException`/
    # `RequestValidationError` (all handled elsewhere, untouched by this
    # module). Deliberately never `FastAPI(debug=True)` here regardless
    # of `AppConfig.debug` (Step 14.1's own dev/prod switch): Starlette's
    # debug traceback page bypasses this handler entirely and would leak
    # exactly what section 6 forbids -- a stack trace in the HTTP
    # response. Dev-mode tracebacks belong in the structlog console
    # output (Step 14.1's `ConsoleRenderer`), not the response body.
    app.add_exception_handler(Exception, _handle_unexpected_error)


def _make_policy_pal_error_handler(
    status_code: int,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def _handler(request: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, PolicyPalError):
            raise TypeError(f"expected a PolicyPalError, got {type(exc).__name__}")
        return JSONResponse(status_code=status_code, content={"detail": exc.message})

    return _handler


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Never logs: `RequestLoggerMiddleware` (Step 14.1) already logs
    `request_failed` -- with the correlation ID and the full exception --
    before this exception finishes propagating up to
    `ServerErrorMiddleware`. Logging again here would just duplicate that
    entry; this handler's only job is shaping a safe response.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )
