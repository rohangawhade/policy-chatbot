"""PostgreSQL implementation of `FeedbackRepository`."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from adapters.persistence.base_repository import PostgresRepository
from core.domain.feedback import Feedback
from core.ports.repository_ports import FeedbackRepository


class PostgresFeedbackRepository(PostgresRepository[Feedback, models.Feedback], FeedbackRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.Feedback)

    def _to_orm(self, entity: Feedback) -> models.Feedback:
        return models.Feedback(
            id=entity.id,
            message_id=entity.message_id,
            conversation_id=entity.conversation_id,
            employer_id=entity.employer_id,
            rating=models.FeedbackRating[entity.rating.name],
            comment=entity.comment,
            created_at=entity.created_at,
        )

    def _to_domain(self, orm_obj: models.Feedback) -> Feedback:
        return Feedback.model_validate(orm_obj)

    def _apply_update(self, existing: models.Feedback, entity: Feedback) -> None:
        existing.message_id = entity.message_id
        existing.conversation_id = entity.conversation_id
        existing.employer_id = entity.employer_id
        existing.rating = models.FeedbackRating[entity.rating.name]
        existing.comment = entity.comment

    async def list_by_employer(self, employer_id: UUID) -> list[Feedback]:
        result = await self._session.execute(
            select(models.Feedback).where(models.Feedback.employer_id == employer_id)
        )
        return [self._to_domain(row) for row in result.scalars().all()]

    async def list_all(self, *, employer_id: UUID | None = None) -> list[Feedback]:
        query = select(models.Feedback)
        if employer_id is not None:
            query = query.where(models.Feedback.employer_id == employer_id)
        result = await self._session.execute(query)
        return [self._to_domain(row) for row in result.scalars().all()]
