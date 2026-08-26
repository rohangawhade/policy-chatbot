"""Sets the authenticated request's `employer_id` in a context variable
(files/plan.md Step 5.3), so it's readable without being threaded
through every function signature between a route handler and whatever
eventually needs it.

Repository queries and vector searches still take `employer_id` as an
explicit parameter — that contract was established across every Phase 3
adapter/repository and isn't changed here. What this adds is a single,
trusted source for *which* `employer_id` a request is allowed to pass
into those calls: read from the authenticated JWT (Step 5.2), never
from a client-supplied value in a request body or query param.

**Real, empirically-verified finding, not a hypothetical**: a plain
`Depends()` function that calls `ContextVar.set(...)` does NOT reliably
propagate that value to the route handler or to other dependencies —
FastAPI/Starlette can resolve dependencies in a way that isolates
`contextvars` state between them (confirmed with a minimal repro before
writing this file: a value set inside one `Depends` was invisible via
`ContextVar.get()` inside the endpoint it fed into). A genuine ASGI/HTTP
middleware doesn't have this problem — it wraps the entire request in
one task, so a value it sets is visible everywhere downstream. That's
why `TenantContextMiddleware` below is real middleware
(`app.add_middleware(...)` in `main.py`), not a `Depends` function like
`auth_middleware.py`'s `get_current_user`, even though both files
otherwise look similar.
"""

from contextvars import ContextVar
from uuid import UUID

from fastapi import Depends, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from api.middleware.auth_middleware import get_current_user
from config import auth_config
from core.domain.employee import Employee
from core.domain.errors import InvalidTokenError
from core.ports.repository_ports import EmployeeRepository
from core.services.auth_service import AuthService, TokenPayload

_employer_id_context: ContextVar[UUID | None] = ContextVar("employer_id_context", default=None)
# Set alongside `_employer_id_context` from the same decoded token -- unlike
# `employer_id` (None for admin accounts), `user_id` is always present on any
# validly decoded token. Exists so `RequestLoggerMiddleware` (Step 14.1) can
# attach `user_id` to every log entry (files/coding-standards.md section 13)
# without re-decoding the token itself.
_user_id_context: ContextVar[UUID | None] = ContextVar("user_id_context", default=None)


class _DecodeOnlyEmployeeRepository(EmployeeRepository):
    """`AuthService.decode_token()` never touches the repository — only
    `authenticate()` does, which this middleware never calls (it has no
    request-scoped DB session to give one anyway; it runs outside
    FastAPI's per-route dependency injection). Every method here would
    be a programming error to actually invoke."""

    async def get(self, entity_id: UUID) -> Employee | None:
        raise NotImplementedError  # pragma: no cover

    async def create(self, entity: Employee) -> Employee:
        raise NotImplementedError  # pragma: no cover

    async def update(self, entity: Employee) -> Employee:
        raise NotImplementedError  # pragma: no cover

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError  # pragma: no cover

    async def get_by_email(self, email: str) -> Employee | None:
        raise NotImplementedError  # pragma: no cover

    async def list_by_employer(self, employer_id: UUID) -> list[Employee]:
        raise NotImplementedError  # pragma: no cover


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Extracts `employer_id` from a valid bearer token, if present, and
    makes it available via `get_employer_id_from_context()` for the rest
    of the request.

    Never blocks a request — a missing or invalid token just leaves the
    context at its default (`None`). Enforcing that a route actually
    requires authentication or a single-employer account is
    `auth_middleware.py`'s job (`get_current_user`) and
    `get_current_employer_id` below, not this middleware's.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._auth_service = AuthService(
            _DecodeOnlyEmployeeRepository(),
            secret_key=auth_config.jwt_secret_key,
            algorithm=auth_config.jwt_algorithm,
            access_token_expire_minutes=auth_config.access_token_expire_minutes,
            refresh_token_expire_days=auth_config.refresh_token_expire_days,
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        token = _extract_bearer_token(request)
        if token is not None:
            try:
                payload = self._auth_service.decode_token(token)
            except InvalidTokenError:
                payload = None
            if payload is not None:
                _user_id_context.set(payload.user_id)
                if payload.employer_id is not None:
                    _employer_id_context.set(payload.employer_id)
        return await call_next(request)


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if header is None or not header.startswith("Bearer "):
        return None
    return header.removeprefix("Bearer ")


def get_current_employer_id(current_user: TokenPayload = Depends(get_current_user)) -> UUID:
    """The authenticated request's tenant-scoping `employer_id`, for a
    route handler that needs it as a typed value.

    Also sets the context variable directly (in addition to
    `TenantContextMiddleware` already having done so for any real
    request) — self-contained behavior for callers that use this
    dependency without the middleware registered, e.g. in tests.

    Raises:
        HTTPException: 403 if the current user has no `employer_id`.
            Only `ADMIN` accounts have none (`core/domain/employee.py`);
            admin-only routes should guard with
            `require_role(UserRole.ADMIN)` instead of this dependency.
    """
    if current_user.employer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an account scoped to a single employer.",
        )
    _employer_id_context.set(current_user.employer_id)
    return current_user.employer_id


def get_employer_id_from_context() -> UUID | None:
    """Read the current request's `employer_id` without depending on
    `get_current_employer_id` or `get_current_user` directly.

    Returns `None` if `TenantContextMiddleware` isn't registered, the
    request had no valid bearer token, or the account has no
    `employer_id` — code that requires a value should depend on
    `get_current_employer_id` instead of calling this and handling
    `None` itself.
    """
    return _employer_id_context.get()


def get_user_id_from_context() -> UUID | None:
    """Read the current request's authenticated `user_id` without
    depending on `get_current_user` directly -- for cross-cutting
    concerns (e.g. `RequestLoggerMiddleware`) that run outside FastAPI's
    per-route dependency injection.

    Returns `None` if `TenantContextMiddleware` isn't registered or the
    request had no valid bearer token.
    """
    return _user_id_context.get()
