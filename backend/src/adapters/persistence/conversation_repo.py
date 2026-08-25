"""PostgreSQL implementations of `ConversationRepository` and
`MessageRepository`."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from adapters.persistence.base_repository import PostgresRepository
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.policy import PolicyType
from core.ports.repository_ports import ConversationRepository, MessageRepository


def _orm_policy_type(policy_type: PolicyType | None) -> models.PolicyType | None:
    return models.PolicyType[policy_type.name] if policy_type is not None else None


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

    async def list_active_since(
        self, since: datetime, *, employer_id: UUID | None = None
    ) -> list[Conversation]:
        query = (
            select(models.Conversation)
            .join(models.Message, models.Message.conversation_id == models.Conversation.id)
            .where(models.Message.created_at >= since)
            .distinct()
        )
        if employer_id is not None:
            query = query.where(models.Conversation.employer_id == employer_id)
        result = await self._session.execute(query)
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
            policy_type=_orm_policy_type(entity.policy_type),
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
        existing.policy_type = _orm_policy_type(entity.policy_type)

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

    async def list_for_analytics(
        self,
        *,
        employer_id: UUID | None = None,
        role: MessageRole | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Message]:
        query = select(models.Message)
        if employer_id is not None:
            query = query.where(models.Message.employer_id == employer_id)
        if role is not None:
            query = query.where(models.Message.role == models.MessageRole[role.name])
        if start is not None:
            query = query.where(models.Message.created_at >= start)
        if end is not None:
            query = query.where(models.Message.created_at < end)
        result = await self._session.execute(query)
        return [self._to_domain(row) for row in result.scalars().all()]
