from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.employee_repo import PostgresEmployeeRepository
from adapters.persistence.employer_repo import PostgresEmployerRepository
from adapters.persistence.policy_repo import PostgresEnrollmentRepository, PostgresPolicyRepository
from core.domain.employee import Employee, UserRole
from core.domain.employer import Employer
from core.domain.policy import Enrollment, Policy, PolicyType
from core.ports.repository_ports import EnrollmentRepository, PolicyRepository


async def _make_employer(db_session: AsyncSession) -> Employer:
    return await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))


async def _make_employee(db_session: AsyncSession, employer_id: UUID) -> Employee:
    return await PostgresEmployeeRepository(db_session).create(
        Employee(
            employer_id=employer_id,
            email="employee@acme.example",
            hashed_password="hashed",
            full_name="Employee",
            role=UserRole.EMPLOYEE,
        )
    )


def test_is_a_policy_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresPolicyRepository(db_session), PolicyRepository)


def test_is_an_enrollment_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresEnrollmentRepository(db_session), EnrollmentRepository)


async def test_create_then_get_round_trips_the_policy_including_type(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresPolicyRepository(db_session)
    policy = Policy(
        employer_id=employer.id,
        policy_type=PolicyType.DENTAL,
        name="Dental PPO",
        description="Standard dental plan",
    )

    await repo.create(policy)
    fetched = await repo.get(policy.id)

    assert fetched is not None
    assert fetched.policy_type == PolicyType.DENTAL
    assert fetched.name == "Dental PPO"


async def test_list_by_employer_only_returns_that_employers_policies(
    db_session: AsyncSession,
) -> None:
    employer_a = await _make_employer(db_session)
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="Beta Corp"))
    repo = PostgresPolicyRepository(db_session)
    await repo.create(
        Policy(employer_id=employer_a.id, policy_type=PolicyType.HEALTH, name="Health A")
    )
    await repo.create(
        Policy(employer_id=employer_b.id, policy_type=PolicyType.HEALTH, name="Health B")
    )

    result = await repo.list_by_employer(employer_a.id)

    assert [p.name for p in result] == ["Health A"]


async def test_update_changes_policy_type_and_name(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresPolicyRepository(db_session)
    policy = await repo.create(
        Policy(employer_id=employer.id, policy_type=PolicyType.VISION, name="Vision Basic")
    )

    policy.policy_type = PolicyType.LIFE
    policy.name = "Life Standard"
    updated = await repo.update(policy)

    assert updated.policy_type == PolicyType.LIFE
    assert updated.name == "Life Standard"


async def test_policy_update_on_a_nonexistent_policy_raises(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresPolicyRepository(db_session)
    ghost = Policy(employer_id=employer.id, policy_type=PolicyType.HEALTH, name="ghost")

    with pytest.raises(ValueError, match="does not exist"):
        await repo.update(ghost)


async def test_delete_removes_the_policy(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresPolicyRepository(db_session)
    policy = await repo.create(
        Policy(employer_id=employer.id, policy_type=PolicyType.DISABILITY, name="Temp")
    )

    await repo.delete(policy.id)

    assert await repo.get(policy.id) is None


async def test_enrollment_create_then_get_round_trips(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    policy = await PostgresPolicyRepository(db_session).create(
        Policy(employer_id=employer.id, policy_type=PolicyType.HEALTH, name="Health")
    )
    repo = PostgresEnrollmentRepository(db_session)
    enrollment = Enrollment(employee_id=employee.id, policy_id=policy.id)

    await repo.create(enrollment)
    fetched = await repo.get(enrollment.id)

    assert fetched is not None
    assert fetched.employee_id == employee.id
    assert fetched.policy_id == policy.id
    assert fetched.is_active is True


async def test_enrollment_list_by_employee(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    policy = await PostgresPolicyRepository(db_session).create(
        Policy(employer_id=employer.id, policy_type=PolicyType.HEALTH, name="Health")
    )
    repo = PostgresEnrollmentRepository(db_session)
    await repo.create(Enrollment(employee_id=employee.id, policy_id=policy.id))

    result = await repo.list_by_employee(employee.id)

    assert len(result) == 1
    assert result[0].policy_id == policy.id


async def test_enrollment_list_by_policy(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    policy = await PostgresPolicyRepository(db_session).create(
        Policy(employer_id=employer.id, policy_type=PolicyType.HEALTH, name="Health")
    )
    repo = PostgresEnrollmentRepository(db_session)
    await repo.create(Enrollment(employee_id=employee.id, policy_id=policy.id))

    result = await repo.list_by_policy(policy.id)

    assert len(result) == 1
    assert result[0].employee_id == employee.id


async def test_enrollment_update_toggles_active_status(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    policy = await PostgresPolicyRepository(db_session).create(
        Policy(employer_id=employer.id, policy_type=PolicyType.HEALTH, name="Health")
    )
    repo = PostgresEnrollmentRepository(db_session)
    enrollment = await repo.create(Enrollment(employee_id=employee.id, policy_id=policy.id))

    enrollment.is_active = False
    updated = await repo.update(enrollment)

    assert updated.is_active is False


async def test_enrollment_delete_removes_it(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    policy = await PostgresPolicyRepository(db_session).create(
        Policy(employer_id=employer.id, policy_type=PolicyType.HEALTH, name="Health")
    )
    repo = PostgresEnrollmentRepository(db_session)
    enrollment = await repo.create(Enrollment(employee_id=employee.id, policy_id=policy.id))

    await repo.delete(enrollment.id)

    assert await repo.get(enrollment.id) is None
