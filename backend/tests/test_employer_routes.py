from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_employer_repository
from api.error_handlers import register_exception_handlers
from api.middleware.auth_middleware import get_current_user
from api.routes import employer_routes
from core.domain.employee import UserRole
from core.domain.employer import Employer
from core.ports.repository_ports import EmployerRepository
from core.services.auth_service import TokenPayload


class _FakeEmployerRepository(EmployerRepository):
    def __init__(self, employers: list[Employer] | None = None) -> None:
        self._by_id = {employer.id: employer for employer in (employers or [])}

    async def get(self, entity_id: UUID) -> Employer | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Employer) -> Employer:
        self._by_id[entity.id] = entity
        return entity

    async def update(self, entity: Employer) -> Employer:
        if entity.id not in self._by_id:
            raise ValueError("not found")
        self._by_id[entity.id] = entity
        return entity

    async def delete(self, entity_id: UUID) -> None:
        self._by_id.pop(entity_id, None)

    async def list_all(self) -> list[Employer]:
        return list(self._by_id.values())


def _test_app(
    *, repository: EmployerRepository | None = None, role: UserRole = UserRole.ADMIN
) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(employer_routes.router)
    app.dependency_overrides[get_employer_repository] = lambda: (
        repository or _FakeEmployerRepository()
    )
    app.dependency_overrides[get_current_user] = lambda: TokenPayload(
        user_id=uuid4(), employer_id=None, role=role, token_type="access"
    )
    return app


def test_create_employer_as_admin() -> None:
    client = TestClient(_test_app())

    response = client.post("/api/employers", json={"name": "Acme Corp"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Corp"
    assert body["is_active"] is True


def test_create_employer_403s_for_a_non_admin() -> None:
    client = TestClient(_test_app(role=UserRole.EMPLOYER))

    response = client.post("/api/employers", json={"name": "Acme Corp"})

    assert response.status_code == 403


def test_list_employers_returns_all_employers() -> None:
    employers = [Employer(name="A"), Employer(name="B")]
    client = TestClient(_test_app(repository=_FakeEmployerRepository(employers)))

    response = client.get("/api/employers")

    assert response.status_code == 200
    assert {e["name"] for e in response.json()} == {"A", "B"}


def test_get_employer_returns_the_employer() -> None:
    employer = Employer(name="Acme Corp")
    client = TestClient(_test_app(repository=_FakeEmployerRepository([employer])))

    response = client.get(f"/api/employers/{employer.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(employer.id)


def test_get_employer_404s_for_an_unknown_employer() -> None:
    client = TestClient(_test_app())

    response = client.get(f"/api/employers/{uuid4()}")

    assert response.status_code == 404


def test_update_employer_applies_only_the_provided_fields() -> None:
    employer = Employer(name="Acme Corp", is_active=True)
    client = TestClient(_test_app(repository=_FakeEmployerRepository([employer])))

    response = client.patch(f"/api/employers/{employer.id}", json={"is_active": False})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Acme Corp"
    assert body["is_active"] is False


def test_update_employer_404s_for_an_unknown_employer() -> None:
    client = TestClient(_test_app())

    response = client.patch(f"/api/employers/{uuid4()}", json={"name": "New Name"})

    assert response.status_code == 404


def test_delete_employer_removes_it() -> None:
    employer = Employer(name="Acme Corp")
    repository = _FakeEmployerRepository([employer])
    client = TestClient(_test_app(repository=repository))

    response = client.delete(f"/api/employers/{employer.id}")

    assert response.status_code == 204
    assert employer.id not in repository._by_id


def test_delete_employer_404s_for_an_unknown_employer() -> None:
    client = TestClient(_test_app())

    response = client.delete(f"/api/employers/{uuid4()}")

    assert response.status_code == 404


def test_all_routes_403_without_admin_role() -> None:
    client = TestClient(_test_app(role=UserRole.EMPLOYEE))

    assert client.get("/api/employers").status_code == 403
    assert client.get(f"/api/employers/{uuid4()}").status_code == 403
    assert client.patch(f"/api/employers/{uuid4()}", json={}).status_code == 403
    assert client.delete(f"/api/employers/{uuid4()}").status_code == 403
