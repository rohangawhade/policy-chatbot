"""Logs every request for latency tracking, and binds a correlation ID
(plus `employer_id`/`user_id`, when authenticated) to every log entry
emitted while handling it (files/plan.md Step 14.1,
files/coding-standards.md section 13's `correlation_id`/`employer_id`/
`user_id` on every entry).

Must be registered so that `TenantContextMiddleware` (`tenant_context.py`)
runs *before* this middleware's `dispatch` starts -- in `main.py`, that
means `app.add_middleware(RequestLoggerMiddleware)` before
`app.add_middleware(TenantContextMiddleware)` (Starlette wraps
later-added middleware around earlier-added ones, so the later addition
runs first). That ordering is what lets this middleware read
`get_employer_id_from_context()`/`get_user_id_from_context()` -- already
populated by the time its own `dispatch` begins -- without decoding the
bearer token a second time itself.
"""

import time
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from api.middleware.tenant_context import get_employer_id_from_context, get_user_id_from_context

logger = structlog.get_logger(__name__)

_CORRELATION_ID_HEADER = "X-Correlation-ID"


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get(_CORRELATION_ID_HEADER) or str(uuid4())

        structlog.contextvars.clear_contextvars()
        bound: dict[str, str] = {"correlation_id": correlation_id}
        employer_id = get_employer_id_from_context()
        if employer_id is not None:
            bound["employer_id"] = str(employer_id)
        user_id = get_user_id_from_context()
        if user_id is not None:
            bound["user_id"] = str(user_id)
        structlog.contextvars.bind_contextvars(**bound)

        start = time.monotonic()
        logger.info("request_received", method=request.method, path=request.url.path)
        try:
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.exception(
                    "request_failed",
                    method=request.method,
                    path=request.url.path,
                    duration_ms=duration_ms,
                )
                raise

            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            response.headers[_CORRELATION_ID_HEADER] = correlation_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
