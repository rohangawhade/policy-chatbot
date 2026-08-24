import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.employer_repo import PostgresEmployerRepository
from core.domain.employer import Employer
from core.ports.repository_ports import EmployerRepository


def test_is_an_employer_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresEmployerRepository(db_session), EmployerRepository)


async def test_create_then_get_round_trips_the_employer(db_session: AsyncSession) -> None:
    repo = PostgresEmployerRepository(db_session)
    employer = Employer(name="Acme Corp")

    created = await repo.create(employer)
    fetched = await repo.get(employer.id)

    assert created.id == employer.id
    assert fetched is not None
    assert fetched.name == "Acme Corp"
    assert fetched.is_active is True


async def test_get_returns_none_for_a_missing_employer(db_session: AsyncSession) -> None:
    repo = PostgresEmployerRepository(db_session)

    result = await repo.get(Employer(name="unused").id)

    assert result is None


async def test_update_persists_changed_fields(db_session: AsyncSession) -> None:
    repo = PostgresEmployerRepository(db_session)
    employer = await repo.create(Employer(name="Original Name"))

    employer.name = "Renamed Corp"
    employer.is_active = False
    updated = await repo.update(employer)

    assert updated.name == "Renamed Corp"
    assert updated.is_active is False
    refetched = await repo.get(employer.id)
    assert refetched is not None
    assert refetched.name == "Renamed Corp"


async def test_update_on_a_nonexistent_employer_raises(db_session: AsyncSession) -> None:
    repo = PostgresEmployerRepository(db_session)

    with pytest.raises(ValueError, match="does not exist"):
        await repo.update(Employer(name="ghost"))


async def test_delete_removes_the_employer(db_session: AsyncSession) -> None:
    repo = PostgresEmployerRepository(db_session)
    employer = await repo.create(Employer(name="Temp Corp"))

    await repo.delete(employer.id)

    assert await repo.get(employer.id) is None


async def test_delete_on_a_missing_employer_does_not_raise(db_session: AsyncSession) -> None:
    repo = PostgresEmployerRepository(db_session)

    await repo.delete(Employer(name="unused").id)


async def test_list_all_returns_every_created_employer(db_session: AsyncSession) -> None:
    repo = PostgresEmployerRepository(db_session)
    await repo.create(Employer(name="First Corp"))
    await repo.create(Employer(name="Second Corp"))

    result = await repo.list_all()

    names = {employer.name for employer in result}
    assert {"First Corp", "Second Corp"}.issubset(names)
