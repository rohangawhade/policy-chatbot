from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import (
    get_employee_repository,
    get_enrollment_repository,
    get_policy_repository,
)
from api.error_handlers import register_exception_handlers
from api.middleware.auth_middleware import get_current_user
from api.middleware.tenant_context import get_current_employer_id
from api.routes import employee_routes
from core.domain.employee import Employee, UserRole
from core.domain.policy import Enrollment, Policy, PolicyType
from core.ports.repository_ports import EmployeeRepository, EnrollmentRepository, PolicyRepository
from core.services.auth_service import AuthService, TokenPayload


class _FakeEmployeeRepository(EmployeeRepository):
    def __init__(self, employees: list[Employee] | None = None) -> None:
        self._by_id = {e.id: e for e in (employees or [])}

    async def get(self, entity_id: UUID) -> Employee | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Employee) -> Employee:
        self._by_id[entity.id] = entity
        return entity

    async def update(self, entity: Employee) -> Employee:
        self._by_id[entity.id] = entity
        return entity

    async def delete(self, entity_id: UUID) -> None:
        self._by_id.pop(entity_id, None)

    async def get_by_email(self, email: str) -> Employee | None:
        return next((e for e in self._by_id.values() if e.email == email), None)

    async def list_by_employer(self, employer_id: UUID) -> list[Employee]:
        return [e for e in self._by_id.values() if e.employer_id == employer_id]


class _FakeEnrollmentRepository(EnrollmentRepository):
    def __init__(self, enrollments: list[Enrollment] | None = None) -> None:
        self._by_id = {e.id: e for e in (enrollments or [])}

    async def get(self, entity_id: UUID) -> Enrollment | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Enrollment) -> Enrollment:
        raise NotImplementedError

    async def update(self, entity: Enrollment) -> Enrollment:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employee(self, employee_id: UUID) -> list[Enrollment]:
        return [e for e in self._by_id.values() if e.employee_id == employee_id]

    async def list_by_policy(self, policy_id: UUID) -> list[Enrollment]:
        raise NotImplementedError


class _FakePolicyRepository(PolicyRepository):
    def __init__(self, policies: list[Policy] | None = None) -> None:
        self._by_id = {p.id: p for p in (policies or [])}

    async def get(self, entity_id: UUID) -> Policy | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Policy) -> Policy:
        raise NotImplementedError

    async def update(self, entity: Policy) -> Policy:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employer(self, employer_id: UUID) -> list[Policy]:
        raise NotImplementedError


def _employee(**overrides: Any) -> Employee:
    defaults: dict[str, Any] = {
        "employer_id": uuid4(),
        "email": "alex@acme.example",
        "hashed_password": AuthService.hash_password("hunter22"),
        "full_name": "Alex Employee",
        "role": UserRole.EMPLOYEE,
    }
    defaults.update(overrides)
    return Employee(**defaults)


def _test_app(
    *,
    employer_id: UUID,
    employee_repository: EmployeeRepository | None = None,
    enrollment_repository: EnrollmentRepository | None = None,
    policy_repository: PolicyRepository | None = None,
    current_user: TokenPayload | None = None,
) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(employee_routes.router)
    app.dependency_overrides[get_employee_repository] = lambda: (
        employee_repository or _FakeEmployeeRepository()
    )
    app.dependency_overrides[get_enrollment_repository] = lambda: (
        enrollment_repository or _FakeEnrollmentRepository()
    )
    app.dependency_overrides[get_policy_repository] = lambda: (
        policy_repository or _FakePolicyRepository()
    )
    app.dependency_overrides[get_current_employer_id] = lambda: employer_id
    app.dependency_overrides[get_current_user] = lambda: current_user or TokenPayload(
        user_id=uuid4(), employer_id=employer_id, role=UserRole.EMPLOYER, token_type="access"
    )
    return app


# --- create -----------------------------------------------------------


def test_create_employee_as_employer_uses_the_callers_own_employer_id() -> None:
    employer_id = uuid4()
    client = TestClient(_test_app(employer_id=employer_id))

    response = client.post(
        "/api/employees",
        json={
            "email": "new@acme.example",
            "password": "hunter22",
            "full_name": "New Employee",
            "role": "employee",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["employer_id"] == str(employer_id)
    assert body["role"] == "employee"


def test_create_employee_rejects_the_admin_role() -> None:
    client = TestClient(_test_app(employer_id=uuid4()))

    response = client.post(
        "/api/employees",
        json={
            "email": "root@acme.example",
            "password": "hunter22",
            "full_name": "Root",
            "role": "admin",
        },
    )

    assert response.status_code == 422


def test_create_employee_409s_for_an_already_registered_email() -> None:
    employer_id = uuid4()
    existing = _employee(employer_id=employer_id, email="taken@acme.example")
    client = TestClient(
        _test_app(employer_id=employer_id, employee_repository=_FakeEmployeeRepository([existing]))
    )

    response = client.post(
        "/api/employees",
        json={
            "email": "taken@acme.example",
            "password": "hunter22",
            "full_name": "Someone",
            "role": "employee",
        },
    )

    assert response.status_code == 409


def test_create_employee_403s_for_an_employee_caller() -> None:
    employer_id = uuid4()
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            current_user=TokenPayload(
                user_id=uuid4(),
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.post(
        "/api/employees",
        json={
            "email": "new@acme.example",
            "password": "hunter22",
            "full_name": "New",
            "role": "employee",
        },
    )

    assert response.status_code == 403


def test_create_employee_as_admin_requires_an_explicit_employer_id() -> None:
    client = TestClient(
        _test_app(
            employer_id=uuid4(),
            current_user=TokenPayload(
                user_id=uuid4(), employer_id=None, role=UserRole.ADMIN, token_type="access"
            ),
        )
    )

    without = client.post(
        "/api/employees",
        json={
            "email": "new@acme.example",
            "password": "hunter22",
            "full_name": "New",
            "role": "employee",
        },
    )
    assert without.status_code == 422

    target_employer_id = uuid4()
    with_id = client.post(
        "/api/employees",
        json={
            "email": "new@acme.example",
            "password": "hunter22",
            "full_name": "New",
            "role": "employee",
            "employer_id": str(target_employer_id),
        },
    )
    assert with_id.status_code == 201
    assert with_id.json()["employer_id"] == str(target_employer_id)


# --- list ---------------------------------------------------------------


def test_list_employees_returns_only_the_current_employers_employees() -> None:
    employer_id = uuid4()
    mine = _employee(employer_id=employer_id, email="mine@acme.example")
    theirs = _employee(employer_id=uuid4(), email="theirs@acme.example")
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            employee_repository=_FakeEmployeeRepository([mine, theirs]),
        )
    )

    response = client.get("/api/employees")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(mine.id)


def test_list_employees_403s_for_an_employee_caller() -> None:
    employer_id = uuid4()
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            current_user=TokenPayload(
                user_id=uuid4(),
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.get("/api/employees")

    assert response.status_code == 403


# --- me/policies ------------------------------------------------------


def test_get_my_policies_returns_the_current_users_enrolled_policies() -> None:
    employer_id = uuid4()
    employee_id = uuid4()
    policy = Policy(employer_id=employer_id, policy_type=PolicyType.HEALTH, name="Health PPO")
    enrollment = Enrollment(employee_id=employee_id, policy_id=policy.id)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            enrollment_repository=_FakeEnrollmentRepository([enrollment]),
            policy_repository=_FakePolicyRepository([policy]),
            current_user=TokenPayload(
                user_id=employee_id,
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.get("/api/employees/me/policies")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Health PPO"
    assert body[0]["policy_type"] == "health"


def test_get_my_policies_returns_empty_for_no_enrollments() -> None:
    employer_id = uuid4()
    client = TestClient(_test_app(employer_id=employer_id))

    response = client.get("/api/employees/me/policies")

    assert response.status_code == 200
    assert response.json() == []


def test_get_my_policies_skips_an_enrollment_whose_policy_no_longer_exists() -> None:
    employer_id = uuid4()
    employee_id = uuid4()
    enrollment = Enrollment(employee_id=employee_id, policy_id=uuid4())
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            enrollment_repository=_FakeEnrollmentRepository([enrollment]),
            current_user=TokenPayload(
                user_id=employee_id,
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.get("/api/employees/me/policies")

    assert response.status_code == 200
    assert response.json() == []


# --- get / update / delete ------------------------------------------------


def test_get_employee_returns_the_employee() -> None:
    employer_id = uuid4()
    employee = _employee(employer_id=employer_id)
    client = TestClient(
        _test_app(employer_id=employer_id, employee_repository=_FakeEmployeeRepository([employee]))
    )

    response = client.get(f"/api/employees/{employee.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(employee.id)


def test_get_employee_404s_for_an_unknown_employee() -> None:
    client = TestClient(_test_app(employer_id=uuid4()))

    response = client.get(f"/api/employees/{uuid4()}")

    assert response.status_code == 404


def test_get_employee_404s_for_another_employers_employee() -> None:
    employee = _employee(employer_id=uuid4())
    client = TestClient(
        _test_app(employer_id=uuid4(), employee_repository=_FakeEmployeeRepository([employee]))
    )

    response = client.get(f"/api/employees/{employee.id}")

    assert response.status_code == 404


def test_get_employee_allows_an_admin_across_employers() -> None:
    employee = _employee(employer_id=uuid4())
    client = TestClient(
        _test_app(
            employer_id=uuid4(),
            employee_repository=_FakeEmployeeRepository([employee]),
            current_user=TokenPayload(
                user_id=uuid4(), employer_id=None, role=UserRole.ADMIN, token_type="access"
            ),
        )
    )

    response = client.get(f"/api/employees/{employee.id}")

    assert response.status_code == 200


def test_update_employee_applies_only_the_provided_fields() -> None:
    employer_id = uuid4()
    employee = _employee(employer_id=employer_id, full_name="Old Name", is_active=True)
    client = TestClient(
        _test_app(employer_id=employer_id, employee_repository=_FakeEmployeeRepository([employee]))
    )

    response = client.patch(f"/api/employees/{employee.id}", json={"is_active": False})

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Old Name"
    assert body["is_active"] is False


def test_delete_employee_removes_it() -> None:
    employer_id = uuid4()
    employee = _employee(employer_id=employer_id)
    repository = _FakeEmployeeRepository([employee])
    client = TestClient(_test_app(employer_id=employer_id, employee_repository=repository))

    response = client.delete(f"/api/employees/{employee.id}")

    assert response.status_code == 204
    assert employee.id not in repository._by_id


def test_delete_employee_403s_for_an_employee_caller() -> None:
    employer_id = uuid4()
    employee = _employee(employer_id=employer_id)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            employee_repository=_FakeEmployeeRepository([employee]),
            current_user=TokenPayload(
                user_id=uuid4(),
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.delete(f"/api/employees/{employee.id}")

    assert response.status_code == 403
