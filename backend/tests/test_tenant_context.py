from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from api.dependencies import get_auth_service
from api.middleware.tenant_context import (
    TenantContextMiddleware,
    get_current_employer_id,
    get_employer_id_from_context,
    get_user_id_from_context,
)
from config import auth_config
from core.domain.employee import UserRole
from core.services.auth_service import AuthService

_SECRET_KEY = "test-secret-key"
_ALGORITHM = "HS256"


def _token(
    *,
    employer_id: UUID | None,
    user_id: UUID | None = None,
    role: UserRole = UserRole.EMPLOYEE,
    token_type: str = "access",
    expires_delta: timedelta = timedelta(minutes=15),
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id if user_id is not None else uuid4()),
        "employer_id": str(employer_id) if employer_id is not None else None,
        "role": role.value,
        "token_type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    encoded: str = jwt.encode(claims, _SECRET_KEY, algorithm=_ALGORITHM)
    return encoded


def test_get_employer_id_from_context_defaults_to_none_outside_a_request() -> None:
    assert get_employer_id_from_context() is None


def test_get_user_id_from_context_defaults_to_none_outside_a_request() -> None:
    assert get_user_id_from_context() is None


@pytest.fixture
def middleware_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A real app with `TenantContextMiddleware` registered, signing/
    verifying with a known test secret, and one route that reads the
    context var directly — proving the middleware alone (no `Depends`)
    makes `employer_id` available to the endpoint."""
    monkeypatch.setattr(auth_config, "jwt_secret_key", _SECRET_KEY)
    monkeypatch.setattr(auth_config, "jwt_algorithm", _ALGORITHM)

    app = FastAPI()
    app.add_middleware(TenantContextMiddleware)

    @app.get("/context-only")
    async def context_only() -> dict[str, str | None]:
        employer_id = get_employer_id_from_context()
        user_id = get_user_id_from_context()
        return {
            "employer_id": str(employer_id) if employer_id else None,
            "user_id": str(user_id) if user_id else None,
        }

    return TestClient(app)


def test_middleware_makes_employer_id_visible_to_the_endpoint(
    middleware_client: TestClient,
) -> None:
    employer_id = uuid4()
    token = _token(employer_id=employer_id)

    response = middleware_client.get("/context-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["employer_id"] == str(employer_id)


def test_middleware_makes_user_id_visible_to_the_endpoint(
    middleware_client: TestClient,
) -> None:
    user_id = uuid4()
    token = _token(employer_id=uuid4(), user_id=user_id)

    response = middleware_client.get("/context-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["user_id"] == str(user_id)


def test_middleware_sets_user_id_even_for_an_admin_with_no_employer_id(
    middleware_client: TestClient,
) -> None:
    user_id = uuid4()
    token = _token(employer_id=None, user_id=user_id, role=UserRole.ADMIN)

    response = middleware_client.get("/context-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"employer_id": None, "user_id": str(user_id)}


def test_middleware_leaves_context_unset_without_a_token(middleware_client: TestClient) -> None:
    response = middleware_client.get("/context-only")

    assert response.status_code == 200
    assert response.json() == {"employer_id": None, "user_id": None}


def test_middleware_leaves_context_unset_for_a_garbage_token(
    middleware_client: TestClient,
) -> None:
    response = middleware_client.get(
        "/context-only", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 200
    assert response.json() == {"employer_id": None, "user_id": None}


def test_middleware_leaves_context_unset_for_an_expired_token(
    middleware_client: TestClient,
) -> None:
    token = _token(employer_id=uuid4(), expires_delta=timedelta(minutes=-1))

    response = middleware_client.get("/context-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"employer_id": None, "user_id": None}


def test_middleware_does_not_leak_the_previous_requests_employer_id(
    middleware_client: TestClient,
) -> None:
    first_employer_id = uuid4()
    second_employer_id = uuid4()

    first_response = middleware_client.get(
        "/context-only",
        headers={"Authorization": f"Bearer {_token(employer_id=first_employer_id)}"},
    )
    second_response = middleware_client.get(
        "/context-only",
        headers={"Authorization": f"Bearer {_token(employer_id=second_employer_id)}"},
    )

    assert first_response.json()["employer_id"] == str(first_employer_id)
    assert second_response.json()["employer_id"] == str(second_employer_id)


class _UnusedEmployeeRepository:
    """`decode_token` never touches the repository."""


def _dependency_test_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_auth_service] = lambda: AuthService(
        _UnusedEmployeeRepository(),  # type: ignore[arg-type]
        secret_key=_SECRET_KEY,
        algorithm=_ALGORITHM,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
    )

    @app.get("/employer-scoped")
    async def employer_scoped(
        employer_id: UUID = Depends(get_current_employer_id),
    ) -> dict[str, str]:
        return {"employer_id": str(employer_id)}

    return app


dependency_client = TestClient(_dependency_test_app())


def test_get_current_employer_id_returns_the_authenticated_employer_id() -> None:
    employer_id = uuid4()
    token = _token(employer_id=employer_id)

    response = dependency_client.get(
        "/employer-scoped", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json() == {"employer_id": str(employer_id)}


def test_get_current_employer_id_rejects_an_admin_with_no_employer_id() -> None:
    token = _token(employer_id=None, role=UserRole.ADMIN)

    response = dependency_client.get(
        "/employer-scoped", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_get_current_employer_id_without_a_token_is_unauthorized() -> None:
    response = dependency_client.get("/employer-scoped")

    assert response.status_code == 401
