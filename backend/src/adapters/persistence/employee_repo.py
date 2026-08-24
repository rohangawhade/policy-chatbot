"""PostgreSQL implementation of `EmployeeRepository`."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from adapters.persistence.base_repository import PostgresRepository
from core.domain.employee import Employee
from core.ports.repository_ports import EmployeeRepository


class PostgresEmployeeRepository(PostgresRepository[Employee, models.Employee], EmployeeRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.Employee)

    def _to_orm(self, entity: Employee) -> models.Employee:
        return models.Employee(
            id=entity.id,
            employer_id=entity.employer_id,
            email=entity.email,
            hashed_password=entity.hashed_password,
            full_name=entity.full_name,
            role=models.UserRole[entity.role.name],
            is_active=entity.is_active,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_domain(self, orm_obj: models.Employee) -> Employee:
        return Employee.model_validate(orm_obj)

    def _apply_update(self, existing: models.Employee, entity: Employee) -> None:
        existing.employer_id = entity.employer_id
        existing.email = entity.email
        existing.hashed_password = entity.hashed_password
        existing.full_name = entity.full_name
        existing.role = models.UserRole[entity.role.name]
        existing.is_active = entity.is_active

    async def get_by_email(self, email: str) -> Employee | None:
        result = await self._session.execute(
            select(models.Employee).where(models.Employee.email == email)
        )
        orm_obj = result.scalar_one_or_none()
        return self._to_domain(orm_obj) if orm_obj is not None else None

    async def list_by_employer(self, employer_id: UUID) -> list[Employee]:
        result = await self._session.execute(
            select(models.Employee).where(models.Employee.employer_id == employer_id)
        )
        return [self._to_domain(row) for row in result.scalars().all()]
