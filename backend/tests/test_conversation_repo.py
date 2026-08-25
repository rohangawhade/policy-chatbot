from datetime import UTC, datetime, timedelta
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
from core.domain.policy import PolicyType
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


async def test_list_active_since_finds_conversations_with_a_recent_message(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    active_conversation = await _make_conversation(db_session, employee)
    idle_conversation = await _make_conversation(db_session, employee)
    message_repo = PostgresMessageRepository(db_session)
    await message_repo.create(
        Message(
            conversation_id=active_conversation.id,
            employer_id=employer.id,
            role=MessageRole.USER,
            content="hi",
        )
    )

    since = datetime.now(UTC) - timedelta(minutes=1)
    result = await PostgresConversationRepository(db_session).list_active_since(since)

    ids = {c.id for c in result}
    assert active_conversation.id in ids
    assert idle_conversation.id not in ids


async def test_list_active_since_filters_by_employer(db_session: AsyncSession) -> None:
    employer_a = await _make_employer(db_session)
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="Other Co"))
    employee_a = await _make_employee(db_session, employer_a.id)
    employee_b = await PostgresEmployeeRepository(db_session).create(
        Employee(
            employer_id=employer_b.id,
            email="other@other.example",
            hashed_password="hashed",
            full_name="Other Employee",
            role=UserRole.EMPLOYEE,
        )
    )
    conversation_a = await _make_conversation(db_session, employee_a)
    conversation_b = await _make_conversation(db_session, employee_b)
    message_repo = PostgresMessageRepository(db_session)
    for conversation, employer in ((conversation_a, employer_a), (conversation_b, employer_b)):
        await message_repo.create(
            Message(
                conversation_id=conversation.id,
                employer_id=employer.id,
                role=MessageRole.USER,
                content="hi",
            )
        )

    since = datetime.now(UTC) - timedelta(minutes=1)
    result = await PostgresConversationRepository(db_session).list_active_since(
        since, employer_id=employer_a.id
    )

    assert [c.id for c in result] == [conversation_a.id]


async def test_list_active_since_excludes_a_conversation_with_no_recent_message(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    await _make_conversation(db_session, employee)

    since = datetime.now(UTC) + timedelta(days=1)
    result = await PostgresConversationRepository(db_session).list_active_since(since)

    assert result == []


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


async def test_message_round_trips_policy_type(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    conversation = await _make_conversation(db_session, employee)
    repo = PostgresMessageRepository(db_session)
    message = await repo.create(
        Message(
            conversation_id=conversation.id,
            employer_id=employer.id,
            role=MessageRole.USER,
            content="what's my dental deductible?",
            policy_type=PolicyType.DENTAL,
        )
    )

    fetched = await repo.get(message.id)

    assert fetched is not None
    assert fetched.policy_type == PolicyType.DENTAL


async def test_list_for_analytics_with_no_filters_spans_every_employer_and_role(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    employee = await _make_employee(db_session, employer.id)
    conversation = await _make_conversation(db_session, employee)
    repo = PostgresMessageRepository(db_session)
    await repo.create(
        Message(
            conversation_id=conversation.id,
            employer_id=employer.id,
            role=MessageRole.USER,
            content="q",
        )
    )
    await repo.create(
        Message(
            conversation_id=conversation.id,
            employer_id=employer.id,
            role=MessageRole.ASSISTANT,
            content="a",
        )
    )

    assert len(await repo.list_for_analytics()) == 2


async def test_list_for_analytics_filters_by_employer_role_and_date_range(
    db_session: AsyncSession,
) -> None:
    employer_a = await _make_employer(db_session)
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="Other Co"))
    employee_a = await _make_employee(db_session, employer_a.id)
    employee_b = await PostgresEmployeeRepository(db_session).create(
        Employee(
            employer_id=employer_b.id,
            email="other2@other.example",
            hashed_password="hashed",
            full_name="Other Employee",
            role=UserRole.EMPLOYEE,
        )
    )
    conversation_a = await _make_conversation(db_session, employee_a)
    conversation_b = await _make_conversation(db_session, employee_b)
    repo = PostgresMessageRepository(db_session)
    await repo.create(
        Message(
            conversation_id=conversation_a.id,
            employer_id=employer_a.id,
            role=MessageRole.USER,
            content="user question",
            policy_type=PolicyType.DENTAL,
        )
    )
    await repo.create(
        Message(
            conversation_id=conversation_a.id,
            employer_id=employer_a.id,
            role=MessageRole.ASSISTANT,
            content="assistant answer",
        )
    )
    await repo.create(
        Message(
            conversation_id=conversation_b.id,
            employer_id=employer_b.id,
            role=MessageRole.USER,
            content="other employer question",
        )
    )

    scoped = await repo.list_for_analytics(employer_id=employer_a.id, role=MessageRole.USER)
    assert [m.content for m in scoped] == ["user question"]
    assert scoped[0].policy_type == PolicyType.DENTAL

    future_start = datetime.now(UTC) + timedelta(days=1)
    assert await repo.list_for_analytics(start=future_start) == []

    past_end = datetime.now(UTC) - timedelta(days=1)
    assert await repo.list_for_analytics(end=past_end) == []
