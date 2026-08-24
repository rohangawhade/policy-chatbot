"""PostgreSQL implementation of `EmployerRepository`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from adapters.persistence.base_repository import PostgresRepository
from core.domain.employer import Employer
from core.ports.repository_ports import EmployerRepository


class PostgresEmployerRepository(PostgresRepository[Employer, models.Employer], EmployerRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.Employer)

    def _to_orm(self, entity: Employer) -> models.Employer:
        return models.Employer(
            id=entity.id,
            name=entity.name,
            is_active=entity.is_active,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_domain(self, orm_obj: models.Employer) -> Employer:
        return Employer.model_validate(orm_obj)

    def _apply_update(self, existing: models.Employer, entity: Employer) -> None:
        existing.name = entity.name
        existing.is_active = entity.is_active

    async def list_all(self) -> list[Employer]:
        result = await self._session.execute(select(models.Employer))
        return [self._to_domain(row) for row in result.scalars().all()]
