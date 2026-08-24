"""PostgreSQL implementations of `ConversationRepository` and
`MessageRepository`."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from adapters.persistence.base_repository import PostgresRepository
from core.domain.conversation import Conversation, Message
from core.ports.repository_ports import ConversationRepository, MessageRepository


class PostgresConversationRepository(
    PostgresRepository[Conversation, models.Conversation], ConversationRepository
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.Conversation)

    def _to_orm(self, entity: Conversation) -> models.Conversation:
        return models.Conversation(
            id=entity.id,
            employee_id=entity.employee_id,
            employer_id=entity.employer_id,
            title=entity.title,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_domain(self, orm_obj: models.Conversation) -> Conversation:
        return Conversation.model_validate(orm_obj)

    def _apply_update(self, existing: models.Conversation, entity: Conversation) -> None:
        existing.employee_id = entity.employee_id
        existing.employer_id = entity.employer_id
        existing.title = entity.title

    async def list_by_employee(self, employee_id: UUID) -> list[Conversation]:
        result = await self._session.execute(
            select(models.Conversation).where(models.Conversation.employee_id == employee_id)
        )
        return [self._to_domain(row) for row in result.scalars().all()]


class PostgresMessageRepository(PostgresRepository[Message, models.Message], MessageRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.Message)

    def _to_orm(self, entity: Message) -> models.Message:
        return models.Message(
            id=entity.id,
            conversation_id=entity.conversation_id,
            employer_id=entity.employer_id,
            role=models.MessageRole[entity.role.name],
            content=entity.content,
            model_used=entity.model_used,
            created_at=entity.created_at,
        )

    def _to_domain(self, orm_obj: models.Message) -> Message:
        return Message.model_validate(orm_obj)

    def _apply_update(self, existing: models.Message, entity: Message) -> None:
        existing.conversation_id = entity.conversation_id
        existing.employer_id = entity.employer_id
        existing.role = models.MessageRole[entity.role.name]
        existing.content = entity.content
        existing.model_used = entity.model_used

    async def list_by_conversation(
        self, conversation_id: UUID, *, limit: int = 20
    ) -> list[Message]:
        # Most recent `limit` messages, returned oldest-first — the order
        # a caller wants when replaying them as LLM prompt context
        # (Step 6.6's conversation memory).
        result = await self._session.execute(
            select(models.Message)
            .where(models.Message.conversation_id == conversation_id)
            .order_by(models.Message.created_at.desc())
            .limit(limit)
        )
        return [self._to_domain(row) for row in reversed(result.scalars().all())]
