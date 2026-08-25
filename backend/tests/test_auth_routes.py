from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from api.dependencies import get_auth_service, get_employee_repository, get_employer_repository
from api.routes import auth_routes
from core.domain.employee import Employee, UserRole
from core.domain.employer import Employer
from core.ports.repository_ports import EmployeeRepository, EmployerRepository
from core.services.auth_service import AuthService

_SECRET_KEY = "test-secret-key"
_ALGORITHM = "HS256"


class _FakeEmployeeRepository(EmployeeRepository):
    def __init__(self, employees: list[Employee] | None = None) -> None:
        self._by_id = {employee.id: employee for employee in (employees or [])}

    async def get(self, entity_id: UUID) -> Employee | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Employee) -> Employee:
        self._by_id[entity.id] = entity
        return entity

    async def update(self, entity: Employee) -> Employee:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def get_by_email(self, email: str) -> Employee | None:
        return next((e for e in self._by_id.values() if e.email == email), None)

    async def list_by_employer(self, employer_id: UUID) -> list[Employee]:
        raise NotImplementedError


class _FakeEmployerRepository(EmployerRepository):
    def __init__(self, employers: list[Employer] | None = None) -> None:
        self._by_id = {employer.id: employer for employer in (employers or [])}

    async def get(self, entity_id: UUID) -> Employer | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Employer) -> Employer:
        raise NotImplementedError

    async def update(self, entity: Employer) -> Employer:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_all(self) -> list[Employer]:
        raise NotImplementedError


def _employee(**overrides: object) -> Employee:
    defaults: dict[str, object] = {
        "employer_id": uuid4(),
        "email": "alex@acme.example",
        "hashed_password": AuthService.hash_password("correct-horse"),
        "full_name": "Alex Employee",
        "role": UserRole.EMPLOYEE,
    }
    defaults.update(overrides)
    return Employee(**defaults)  # type: ignore[arg-type]


def _test_app(
    employee_repository: EmployeeRepository,
    employer_repository: EmployerRepository,
) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router)
    app.dependency_overrides[get_employee_repository] = lambda: employee_repository
    app.dependency_overrides[get_employer_repository] = lambda: employer_repository
    app.dependency_overrides[get_auth_service] = lambda: AuthService(
        employee_repository,
        secret_key=_SECRET_KEY,
        algorithm=_ALGORITHM,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
    )
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


# --- register ---------------------------------------------------------


def test_register_creates_an_employee_and_returns_a_token_pair() -> None:
    employer = Employer(name="Acme Corp")
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository([employer])))

    response = client.post(
        "/api/auth/register",
        json={
            "employer_id": str(employer.id),
            "email": "new@acme.example",
            "password": "hunter22",
            "full_name": "New Employee",
            "role": "employee",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


def test_register_allows_the_employer_role() -> None:
    employer = Employer(name="Acme Corp")
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository([employer])))

    response = client.post(
        "/api/auth/register",
        json={
            "employer_id": str(employer.id),
            "email": "hr@acme.example",
            "password": "hunter22",
            "full_name": "HR Contact",
            "role": "employer",
        },
    )

    assert response.status_code == 201


def test_register_rejects_the_admin_role() -> None:
    employer = Employer(name="Acme Corp")
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository([employer])))

    response = client.post(
        "/api/auth/register",
        json={
            "employer_id": str(employer.id),
            "email": "root@acme.example",
            "password": "hunter22",
            "full_name": "Root",
            "role": "admin",
        },
    )

    assert response.status_code == 422


def test_register_404s_for_an_unknown_employer() -> None:
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository([])))

    response = client.post(
        "/api/auth/register",
        json={
            "employer_id": str(uuid4()),
            "email": "new@acme.example",
            "password": "hunter22",
            "full_name": "New Employee",
            "role": "employee",
        },
    )

    assert response.status_code == 404


def test_register_409s_for_an_already_registered_email() -> None:
    employer = Employer(name="Acme Corp")
    existing = _employee(employer_id=employer.id, email="taken@acme.example")
    client = TestClient(
        _test_app(_FakeEmployeeRepository([existing]), _FakeEmployerRepository([employer]))
    )

    response = client.post(
        "/api/auth/register",
        json={
            "employer_id": str(employer.id),
            "email": "taken@acme.example",
            "password": "hunter22",
            "full_name": "Someone Else",
            "role": "employee",
        },
    )

    assert response.status_code == 409


# --- login --------------------------------------------------------------


def test_login_with_correct_credentials_returns_a_token_pair() -> None:
    employee = _employee(email="alex@acme.example")
    client = TestClient(_test_app(_FakeEmployeeRepository([employee]), _FakeEmployerRepository()))

    response = client.post(
        "/api/auth/login",
        data={"username": "alex@acme.example", "password": "correct-horse"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_with_wrong_password_is_unauthorized() -> None:
    employee = _employee(email="alex@acme.example")
    client = TestClient(_test_app(_FakeEmployeeRepository([employee]), _FakeEmployerRepository()))

    response = client.post(
        "/api/auth/login",
        data={"username": "alex@acme.example", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_with_unknown_email_is_unauthorized() -> None:
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository()))

    response = client.post(
        "/api/auth/login",
        data={"username": "nobody@acme.example", "password": "whatever"},
    )

    assert response.status_code == 401


def test_login_for_an_inactive_account_is_unauthorized() -> None:
    employee = _employee(email="alex@acme.example", is_active=False)
    client = TestClient(_test_app(_FakeEmployeeRepository([employee]), _FakeEmployerRepository()))

    response = client.post(
        "/api/auth/login",
        data={"username": "alex@acme.example", "password": "correct-horse"},
    )

    assert response.status_code == 401


# --- refresh --------------------------------------------------------------


def test_refresh_with_a_valid_refresh_token_returns_a_new_access_token() -> None:
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository()))
    refresh_token = _token(token_type="refresh")

    response = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_refresh_with_an_access_token_is_unauthorized() -> None:
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository()))
    access_token = _token(token_type="access")

    response = client.post("/api/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401


def test_refresh_with_garbage_is_unauthorized() -> None:
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository()))

    response = client.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"})

    assert response.status_code == 401


# --- me -------------------------------------------------------------------


def test_me_returns_the_current_users_profile_without_the_password_hash() -> None:
    employee = _employee(email="alex@acme.example", full_name="Alex Employee")
    client = TestClient(_test_app(_FakeEmployeeRepository([employee]), _FakeEmployerRepository()))
    token = _token(user_id=employee.id, employer_id=employee.employer_id)

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(employee.id),
        "employer_id": str(employee.employer_id),
        "email": "alex@acme.example",
        "full_name": "Alex Employee",
        "role": "employee",
        "is_active": True,
    }
    assert "hashed_password" not in response.json()


def test_me_without_a_token_is_unauthorized() -> None:
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository()))

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_404s_if_the_account_no_longer_exists() -> None:
    client = TestClient(_test_app(_FakeEmployeeRepository(), _FakeEmployerRepository()))
    token = _token()

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
