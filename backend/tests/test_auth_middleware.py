from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from api.dependencies import get_auth_service
from api.middleware.auth_middleware import get_current_user, require_role
from core.domain.employee import UserRole
from core.services.auth_service import AuthService, TokenPayload

_SECRET_KEY = "test-secret-key"
_ALGORITHM = "HS256"


class _UnusedEmployeeRepository:
    """`decode_token`/`refresh_access_token` never touch the repository —
    every test route here only exercises those, so a repository that
    would raise if ever called is a deliberate guard, not a real fake."""


def _test_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_auth_service] = lambda: AuthService(
        _UnusedEmployeeRepository(),  # type: ignore[arg-type]
        secret_key=_SECRET_KEY,
        algorithm=_ALGORITHM,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
    )

    @app.get("/whoami")
    async def whoami(
        current_user: TokenPayload = Depends(get_current_user),
    ) -> dict[str, str | None]:
        return {
            "user_id": str(current_user.user_id),
            "employer_id": str(current_user.employer_id) if current_user.employer_id else None,
            "role": current_user.role.value,
        }

    @app.get("/admin-only", dependencies=[Depends(require_role(UserRole.ADMIN))])
    async def admin_only() -> dict[str, bool]:
        return {"ok": True}

    return app


def _token(
    *,
    user_id: UUID | None = None,
    employer_id: UUID | None = None,
    role: UserRole = UserRole.EMPLOYEE,
    token_type: str = "access",
    expires_delta: timedelta = timedelta(minutes=15),
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id or uuid4()),
        "employer_id": str(employer_id) if employer_id is not None else None,
        "role": role.value,
        "token_type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    encoded: str = jwt.encode(claims, _SECRET_KEY, algorithm=_ALGORITHM)
    return encoded


client = TestClient(_test_app())


def test_whoami_without_a_token_is_unauthorized() -> None:
    response = client.get("/whoami")

    assert response.status_code == 401


def test_whoami_with_garbage_bearer_token_is_unauthorized() -> None:
    response = client.get("/whoami", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_whoami_with_a_valid_access_token_returns_the_current_user() -> None:
    user_id, employer_id = uuid4(), uuid4()
    token = _token(user_id=user_id, employer_id=employer_id, role=UserRole.EMPLOYER)

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user_id),
        "employer_id": str(employer_id),
        "role": "employer",
    }


def test_whoami_with_a_refresh_token_is_unauthorized() -> None:
    token = _token(token_type="refresh")

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_whoami_with_an_expired_token_is_unauthorized() -> None:
    token = _token(expires_delta=timedelta(minutes=-1))

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_admin_only_route_allows_an_admin() -> None:
    token = _token(role=UserRole.ADMIN)

    response = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


def test_admin_only_route_rejects_a_non_admin() -> None:
    token = _token(role=UserRole.EMPLOYEE)

    response = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_admin_only_route_without_a_token_is_unauthorized() -> None:
    response = client.get("/admin-only")

    assert response.status_code == 401
