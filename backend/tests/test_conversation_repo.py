from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.conversation_repo import (
    PostgresConversationRepository,
    PostgresMessageRepository,
)
from adapters.persistence.employee_repo import PostgresEmployeeRepository
from adapters.persistence.employer_repo import PostgresEmployerRepository
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.employee import Employee, UserRole
from core.domain.employer import Employer
from core.ports.repository_ports import ConversationRepository, MessageRepository


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


async def _make_conversation(db_session: AsyncSession, employee: Employee) -> Conversation:
    return await PostgresConversationRepository(db_session).create(
        Conversation(employee_id=employee.id, employer_id=employee.employer_id, title="Q&A")  # type: ignore[arg-type]
    )


def test_is_a_conversation_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresConversationRepository(db_session), ConversationRepository)


def test_is_a_message_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresMessageRepository(db_session), MessageRepository)


async def test_conversation_create_then_get_round_trips(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)

    conversation = await _make_conversation(db_session, employee)
    fetched = await PostgresConversationRepository(db_session).get(conversation.id)

    assert fetched is not None
    assert fetched.title == "Q&A"
    assert fetched.employee_id == employee.id


async def test_conversation_list_by_employee(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    await _make_conversation(db_session, employee)

    result = await PostgresConversationRepository(db_session).list_by_employee(employee.id)

    assert len(result) == 1


async def test_conversation_update_changes_title(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    repo = PostgresConversationRepository(db_session)
    conversation = await _make_conversation(db_session, employee)

    conversation.title = "Renamed"
    updated = await repo.update(conversation)

    assert updated.title == "Renamed"


async def test_conversation_update_on_a_nonexistent_conversation_raises(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    repo = PostgresConversationRepository(db_session)
    ghost = Conversation(employee_id=employee.id, employer_id=employer.id)

    with pytest.raises(ValueError, match="does not exist"):
        await repo.update(ghost)


async def test_conversation_delete_removes_it(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    repo = PostgresConversationRepository(db_session)
    conversation = await _make_conversation(db_session, employee)

    await repo.delete(conversation.id)

    assert await repo.get(conversation.id) is None


async def test_message_create_then_get_round_trips_including_role(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    conversation = await _make_conversation(db_session, employee)
    repo = PostgresMessageRepository(db_session)
    message = Message(
        conversation_id=conversation.id,
        employer_id=employer.id,
        role=MessageRole.USER,
        content="What's my deductible?",
    )

    await repo.create(message)
    fetched = await repo.get(message.id)

    assert fetched is not None
    assert fetched.role == MessageRole.USER
    assert fetched.content == "What's my deductible?"


async def test_list_by_conversation_returns_messages_oldest_first_within_the_limit(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    conversation = await _make_conversation(db_session, employee)
    repo = PostgresMessageRepository(db_session)
    for i in range(5):
        await repo.create(
            Message(
                conversation_id=conversation.id,
                employer_id=employer.id,
                role=MessageRole.USER,
                content=f"message {i}",
            )
        )

    result = await repo.list_by_conversation(conversation.id, limit=3)

    assert [m.content for m in result] == ["message 2", "message 3", "message 4"]


async def test_list_by_conversation_only_returns_that_conversations_messages(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    conversation_a = await _make_conversation(db_session, employee)
    conversation_b = await _make_conversation(db_session, employee)
    repo = PostgresMessageRepository(db_session)
    await repo.create(
        Message(
            conversation_id=conversation_a.id,
            employer_id=employer.id,
            role=MessageRole.USER,
            content="in A",
        )
    )
    await repo.create(
        Message(
            conversation_id=conversation_b.id,
            employer_id=employer.id,
            role=MessageRole.USER,
            content="in B",
        )
    )

    result = await repo.list_by_conversation(conversation_a.id)

    assert [m.content for m in result] == ["in A"]


async def test_message_update_changes_content(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    conversation = await _make_conversation(db_session, employee)
    repo = PostgresMessageRepository(db_session)
    message = await repo.create(
        Message(
            conversation_id=conversation.id,
            employer_id=employer.id,
            role=MessageRole.ASSISTANT,
            content="original",
        )
    )

    message.content = "edited"
    updated = await repo.update(message)

    assert updated.content == "edited"


async def test_message_delete_removes_it(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    conversation = await _make_conversation(db_session, employee)
    repo = PostgresMessageRepository(db_session)
    message = await repo.create(
        Message(
            conversation_id=conversation.id,
            employer_id=employer.id,
            role=MessageRole.USER,
            content="temp",
        )
    )

    await repo.delete(message.id)

    assert await repo.get(message.id) is None
