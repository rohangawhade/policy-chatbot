"""PostgreSQL implementations of `PolicyRepository` and
`EnrollmentRepository` (the latter mapping to the `EmployeePolicy` ORM
table — plan.md's Step 1.3 table name, "enrollment" in domain terms)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from adapters.persistence.base_repository import PostgresRepository
from core.domain.policy import Enrollment, Policy
from core.ports.repository_ports import EnrollmentRepository, PolicyRepository


class PostgresPolicyRepository(PostgresRepository[Policy, models.Policy], PolicyRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.Policy)

    def _to_orm(self, entity: Policy) -> models.Policy:
        return models.Policy(
            id=entity.id,
            employer_id=entity.employer_id,
            policy_type=models.PolicyType[entity.policy_type.name],
            name=entity.name,
            description=entity.description,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_domain(self, orm_obj: models.Policy) -> Policy:
        return Policy.model_validate(orm_obj)

    def _apply_update(self, existing: models.Policy, entity: Policy) -> None:
        existing.employer_id = entity.employer_id
        existing.policy_type = models.PolicyType[entity.policy_type.name]
        existing.name = entity.name
        existing.description = entity.description

    async def list_by_employer(self, employer_id: UUID) -> list[Policy]:
        result = await self._session.execute(
            select(models.Policy).where(models.Policy.employer_id == employer_id)
        )
        return [self._to_domain(row) for row in result.scalars().all()]


class PostgresEnrollmentRepository(
    PostgresRepository[Enrollment, models.EmployeePolicy], EnrollmentRepository
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.EmployeePolicy)

    def _to_orm(self, entity: Enrollment) -> models.EmployeePolicy:
        return models.EmployeePolicy(
            id=entity.id,
            employee_id=entity.employee_id,
            policy_id=entity.policy_id,
            enrolled_at=entity.enrolled_at,
            is_active=entity.is_active,
        )

    def _to_domain(self, orm_obj: models.EmployeePolicy) -> Enrollment:
        return Enrollment.model_validate(orm_obj)

    def _apply_update(self, existing: models.EmployeePolicy, entity: Enrollment) -> None:
        existing.employee_id = entity.employee_id
        existing.policy_id = entity.policy_id
        existing.is_active = entity.is_active

    async def list_by_employee(self, employee_id: UUID) -> list[Enrollment]:
        result = await self._session.execute(
            select(models.EmployeePolicy).where(models.EmployeePolicy.employee_id == employee_id)
        )
        return [self._to_domain(row) for row in result.scalars().all()]

    async def list_by_policy(self, policy_id: UUID) -> list[Enrollment]:
        result = await self._session.execute(
            select(models.EmployeePolicy).where(models.EmployeePolicy.policy_id == policy_id)
        )
        return [self._to_domain(row) for row in result.scalars().all()]
