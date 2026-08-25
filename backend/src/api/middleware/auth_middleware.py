"""Authenticates incoming requests: decodes the bearer token, attaches
the current user, and gates routes by role (files/plan.md Step 5.2).
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from api.dependencies import get_auth_service
from core.domain.employee import UserRole
from core.domain.errors import InvalidTokenError
from core.services.auth_service import AuthService, TokenPayload

# tokenUrl is only Swagger UI's "Authorize" button hint — points at the
# real login route added by Step 9.1 (files/plan.md).
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(_oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPayload:
    """Decode and validate the request's bearer token into a `TokenPayload`
    (plan.md's "CurrentUser").

    Raises:
        HTTPException: 401 if the token is missing, malformed, expired,
            or a refresh token presented where an access token is
            required.
    """
    try:
        payload = auth_service.decode_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A refresh token cannot be used to authenticate a request.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


# Any x2: a FastAPI dependency's Coroutine send/throw types are never used
# by a caller — this is the standard shape for "an async callable", not a
# genuine unknown.
def require_role(
    *allowed_roles: UserRole,
) -> Callable[..., Coroutine[Any, Any, TokenPayload]]:
    """Build a dependency that only lets `allowed_roles` through.

    Usage: `@router.get(..., dependencies=[Depends(require_role(UserRole.ADMIN))])`.

    Raises:
        HTTPException: 403 if the authenticated user's role isn't in
            `allowed_roles`.
    """

    async def _check(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to perform this action.",
            )
        return current_user

    return _check
