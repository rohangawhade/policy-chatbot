import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.employee_repo import PostgresEmployeeRepository
from adapters.persistence.employer_repo import PostgresEmployerRepository
from core.domain.employee import Employee, UserRole
from core.domain.employer import Employer
from core.ports.repository_ports import EmployeeRepository


async def _make_employer(db_session: AsyncSession) -> Employer:
    return await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))


def test_is_an_employee_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresEmployeeRepository(db_session), EmployeeRepository)


async def test_create_then_get_round_trips_the_employee_including_role(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresEmployeeRepository(db_session)
    employee = Employee(
        employer_id=employer.id,
        email="jane@acme.example",
        hashed_password="hashed",
        full_name="Jane Doe",
        role=UserRole.EMPLOYEE,
    )

    await repo.create(employee)
    fetched = await repo.get(employee.id)

    assert fetched is not None
    assert fetched.email == "jane@acme.example"
    assert fetched.role == UserRole.EMPLOYEE
    assert fetched.employer_id == employer.id


async def test_create_an_admin_with_no_employer(db_session: AsyncSession) -> None:
    repo = PostgresEmployeeRepository(db_session)
    admin = Employee(
        employer_id=None,
        email="admin@policypal.example",
        hashed_password="hashed",
        full_name="Admin User",
        role=UserRole.ADMIN,
    )

    await repo.create(admin)
    fetched = await repo.get(admin.id)

    assert fetched is not None
    assert fetched.employer_id is None
    assert fetched.role == UserRole.ADMIN


async def test_get_by_email_finds_the_matching_employee(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresEmployeeRepository(db_session)
    await repo.create(
        Employee(
            employer_id=employer.id,
            email="findme@acme.example",
            hashed_password="hashed",
            full_name="Find Me",
            role=UserRole.EMPLOYEE,
        )
    )

    found = await repo.get_by_email("findme@acme.example")

    assert found is not None
    assert found.full_name == "Find Me"


async def test_get_by_email_returns_none_when_no_match(db_session: AsyncSession) -> None:
    result = await PostgresEmployeeRepository(db_session).get_by_email("nobody@acme.example")

    assert result is None


async def test_list_by_employer_only_returns_that_employers_employees(
    db_session: AsyncSession,
) -> None:
    employer_a = await _make_employer(db_session)
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="Beta Corp"))
    repo = PostgresEmployeeRepository(db_session)
    await repo.create(
        Employee(
            employer_id=employer_a.id,
            email="a@acme.example",
            hashed_password="hashed",
            full_name="A",
            role=UserRole.EMPLOYEE,
        )
    )
    await repo.create(
        Employee(
            employer_id=employer_b.id,
            email="b@beta.example",
            hashed_password="hashed",
            full_name="B",
            role=UserRole.EMPLOYEE,
        )
    )

    result = await repo.list_by_employer(employer_a.id)

    assert [e.email for e in result] == ["a@acme.example"]


async def test_update_changes_role_and_active_status(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresEmployeeRepository(db_session)
    employee = await repo.create(
        Employee(
            employer_id=employer.id,
            email="promote@acme.example",
            hashed_password="hashed",
            full_name="Promote Me",
            role=UserRole.EMPLOYEE,
        )
    )

    employee.role = UserRole.EMPLOYER
    employee.is_active = False
    updated = await repo.update(employee)

    assert updated.role == UserRole.EMPLOYER
    assert updated.is_active is False


async def test_update_on_a_nonexistent_employee_raises(db_session: AsyncSession) -> None:
    repo = PostgresEmployeeRepository(db_session)
    ghost = Employee(
        email="ghost@acme.example",
        hashed_password="hashed",
        full_name="Ghost",
        role=UserRole.EMPLOYEE,
    )

    with pytest.raises(ValueError, match="does not exist"):
        await repo.update(ghost)


async def test_delete_removes_the_employee(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresEmployeeRepository(db_session)
    employee = await repo.create(
        Employee(
            employer_id=employer.id,
            email="temp@acme.example",
            hashed_password="hashed",
            full_name="Temp",
            role=UserRole.EMPLOYEE,
        )
    )

    await repo.delete(employee.id)

    assert await repo.get(employee.id) is None
