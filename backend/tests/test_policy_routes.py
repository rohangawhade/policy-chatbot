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
from api.routes import policy_routes
from core.domain.employee import Employee, UserRole
from core.domain.policy import Enrollment, Policy, PolicyType
from core.ports.repository_ports import EmployeeRepository, EnrollmentRepository, PolicyRepository
from core.services.auth_service import AuthService, TokenPayload


class _FakePolicyRepository(PolicyRepository):
    def __init__(self, policies: list[Policy] | None = None) -> None:
        self._by_id = {p.id: p for p in (policies or [])}

    async def get(self, entity_id: UUID) -> Policy | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Policy) -> Policy:
        self._by_id[entity.id] = entity
        return entity

    async def update(self, entity: Policy) -> Policy:
        self._by_id[entity.id] = entity
        return entity

    async def delete(self, entity_id: UUID) -> None:
        self._by_id.pop(entity_id, None)

    async def list_by_employer(self, employer_id: UUID) -> list[Policy]:
        return [p for p in self._by_id.values() if p.employer_id == employer_id]


class _FakeEmployeeRepository(EmployeeRepository):
    def __init__(self, employees: list[Employee] | None = None) -> None:
        self._by_id = {e.id: e for e in (employees or [])}

    async def get(self, entity_id: UUID) -> Employee | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Employee) -> Employee:
        raise NotImplementedError

    async def update(self, entity: Employee) -> Employee:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def get_by_email(self, email: str) -> Employee | None:
        raise NotImplementedError

    async def list_by_employer(self, employer_id: UUID) -> list[Employee]:
        raise NotImplementedError


class _FakeEnrollmentRepository(EnrollmentRepository):
    def __init__(self, enrollments: list[Enrollment] | None = None) -> None:
        self._by_id = {e.id: e for e in (enrollments or [])}

    async def get(self, entity_id: UUID) -> Enrollment | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Enrollment) -> Enrollment:
        self._by_id[entity.id] = entity
        return entity

    async def update(self, entity: Enrollment) -> Enrollment:
        self._by_id[entity.id] = entity
        return entity

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employee(self, employee_id: UUID) -> list[Enrollment]:
        return [e for e in self._by_id.values() if e.employee_id == employee_id]

    async def list_by_policy(self, policy_id: UUID) -> list[Enrollment]:
        return [e for e in self._by_id.values() if e.policy_id == policy_id]


def _policy(**overrides: Any) -> Policy:
    defaults: dict[str, Any] = {
        "employer_id": uuid4(),
        "policy_type": PolicyType.HEALTH,
        "name": "Health PPO",
    }
    defaults.update(overrides)
    return Policy(**defaults)


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
    policy_repository: PolicyRepository | None = None,
    employee_repository: EmployeeRepository | None = None,
    enrollment_repository: EnrollmentRepository | None = None,
    current_user: TokenPayload | None = None,
) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(policy_routes.router)
    app.dependency_overrides[get_policy_repository] = lambda: (
        policy_repository or _FakePolicyRepository()
    )
    app.dependency_overrides[get_employee_repository] = lambda: (
        employee_repository or _FakeEmployeeRepository()
    )
    app.dependency_overrides[get_enrollment_repository] = lambda: (
        enrollment_repository or _FakeEnrollmentRepository()
    )
    app.dependency_overrides[get_current_employer_id] = lambda: employer_id
    app.dependency_overrides[get_current_user] = lambda: current_user or TokenPayload(
        user_id=uuid4(), employer_id=employer_id, role=UserRole.EMPLOYER, token_type="access"
    )
    return app


# --- create / list / get / update / delete ---------------------------------


def test_create_policy_as_employer() -> None:
    employer_id = uuid4()
    client = TestClient(_test_app(employer_id=employer_id))

    response = client.post("/api/policies", json={"policy_type": "dental", "name": "Dental PPO"})

    assert response.status_code == 201
    body = response.json()
    assert body["employer_id"] == str(employer_id)
    assert body["policy_type"] == "dental"


def test_create_policy_403s_for_an_employee_caller() -> None:
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

    response = client.post("/api/policies", json={"policy_type": "dental", "name": "Dental PPO"})

    assert response.status_code == 403


def test_list_policies_is_open_to_an_employee_caller() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            current_user=TokenPayload(
                user_id=uuid4(),
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.get("/api/policies")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_policy_returns_the_policy() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    client = TestClient(
        _test_app(employer_id=employer_id, policy_repository=_FakePolicyRepository([policy]))
    )

    response = client.get(f"/api/policies/{policy.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(policy.id)


def test_get_policy_404s_for_another_employers_policy() -> None:
    policy = _policy(employer_id=uuid4())
    client = TestClient(
        _test_app(employer_id=uuid4(), policy_repository=_FakePolicyRepository([policy]))
    )

    response = client.get(f"/api/policies/{policy.id}")

    assert response.status_code == 404


def test_update_policy_applies_only_the_provided_fields() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id, name="Old Name")
    client = TestClient(
        _test_app(employer_id=employer_id, policy_repository=_FakePolicyRepository([policy]))
    )

    response = client.patch(f"/api/policies/{policy.id}", json={"name": "New Name"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New Name"
    assert body["policy_type"] == "health"


def test_delete_policy_removes_it() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    repository = _FakePolicyRepository([policy])
    client = TestClient(_test_app(employer_id=employer_id, policy_repository=repository))

    response = client.delete(f"/api/policies/{policy.id}")

    assert response.status_code == 204
    assert policy.id not in repository._by_id


# --- enrollments (Step 10.8) -------------------------------------------


def test_list_policy_enrollments_returns_enrolled_employees() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    employee = _employee(employer_id=employer_id, full_name="Alex Employee")
    enrollment = Enrollment(employee_id=employee.id, policy_id=policy.id, is_active=True)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            employee_repository=_FakeEmployeeRepository([employee]),
            enrollment_repository=_FakeEnrollmentRepository([enrollment]),
        )
    )

    response = client.get(f"/api/policies/{policy.id}/enrollments")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["employee_id"] == str(employee.id)
    assert body[0]["full_name"] == "Alex Employee"
    assert body[0]["email"] == employee.email
    assert body[0]["is_active"] is True


def test_list_policy_enrollments_omits_unenrolled_and_deleted_employees() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    # Enrollment points at an employee id that no longer resolves (e.g.
    # the employee row was deleted) -- should be skipped, not 500.
    dangling = Enrollment(employee_id=uuid4(), policy_id=policy.id, is_active=True)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            enrollment_repository=_FakeEnrollmentRepository([dangling]),
        )
    )

    response = client.get(f"/api/policies/{policy.id}/enrollments")

    assert response.status_code == 200
    assert response.json() == []


def test_list_policy_enrollments_404s_for_another_employers_policy() -> None:
    policy = _policy(employer_id=uuid4())
    client = TestClient(
        _test_app(employer_id=uuid4(), policy_repository=_FakePolicyRepository([policy]))
    )

    response = client.get(f"/api/policies/{policy.id}/enrollments")

    assert response.status_code == 404


def test_list_policy_enrollments_403s_for_an_employee_caller() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            current_user=TokenPayload(
                user_id=uuid4(),
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.get(f"/api/policies/{policy.id}/enrollments")

    assert response.status_code == 403


# --- enroll / unenroll ------------------------------------------------


def test_enroll_employee_creates_a_new_enrollment() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    employee = _employee(employer_id=employer_id)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            employee_repository=_FakeEmployeeRepository([employee]),
        )
    )

    response = client.post(
        f"/api/policies/{policy.id}/enroll", json={"employee_id": str(employee.id)}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["employee_id"] == str(employee.id)
    assert body["policy_id"] == str(policy.id)
    assert body["is_active"] is True


def test_enroll_employee_reactivates_an_existing_inactive_enrollment() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    employee = _employee(employer_id=employer_id)
    existing = Enrollment(employee_id=employee.id, policy_id=policy.id, is_active=False)
    enrollment_repository = _FakeEnrollmentRepository([existing])
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            employee_repository=_FakeEmployeeRepository([employee]),
            enrollment_repository=enrollment_repository,
        )
    )

    response = client.post(
        f"/api/policies/{policy.id}/enroll", json={"employee_id": str(employee.id)}
    )

    assert response.status_code == 201
    assert response.json()["is_active"] is True
    # Reactivated the same row — no second enrollment created.
    assert len(enrollment_repository._by_id) == 1


def test_enroll_employee_404s_for_an_unknown_policy() -> None:
    employer_id = uuid4()
    employee = _employee(employer_id=employer_id)
    client = TestClient(
        _test_app(employer_id=employer_id, employee_repository=_FakeEmployeeRepository([employee]))
    )

    response = client.post(
        f"/api/policies/{uuid4()}/enroll", json={"employee_id": str(employee.id)}
    )

    assert response.status_code == 404


def test_enroll_employee_404s_for_an_employee_from_another_employer() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    employee = _employee(employer_id=uuid4())
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            employee_repository=_FakeEmployeeRepository([employee]),
        )
    )

    response = client.post(
        f"/api/policies/{policy.id}/enroll", json={"employee_id": str(employee.id)}
    )

    assert response.status_code == 404


def test_unenroll_employee_deactivates_the_enrollment() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    employee = _employee(employer_id=employer_id)
    existing = Enrollment(employee_id=employee.id, policy_id=policy.id, is_active=True)
    enrollment_repository = _FakeEnrollmentRepository([existing])
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            enrollment_repository=enrollment_repository,
        )
    )

    response = client.delete(f"/api/policies/{policy.id}/enroll/{employee.id}")

    assert response.status_code == 204
    assert enrollment_repository._by_id[existing.id].is_active is False


def test_unenroll_employee_404s_for_a_missing_enrollment() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    client = TestClient(
        _test_app(employer_id=employer_id, policy_repository=_FakePolicyRepository([policy]))
    )

    response = client.delete(f"/api/policies/{policy.id}/enroll/{uuid4()}")

    assert response.status_code == 404


def test_enroll_and_unenroll_403_for_an_employee_caller() -> None:
    employer_id = uuid4()
    policy = _policy(employer_id=employer_id)
    client = TestClient(
        _test_app(
            employer_id=employer_id,
            policy_repository=_FakePolicyRepository([policy]),
            current_user=TokenPayload(
                user_id=uuid4(),
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    assert (
        client.post(
            f"/api/policies/{policy.id}/enroll", json={"employee_id": str(uuid4())}
        ).status_code
        == 403
    )
    assert client.delete(f"/api/policies/{policy.id}/enroll/{uuid4()}").status_code == 403
