from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.conversation_repo import (
    PostgresConversationRepository,
    PostgresMessageRepository,
)
from adapters.persistence.employee_repo import PostgresEmployeeRepository
from adapters.persistence.employer_repo import PostgresEmployerRepository
from adapters.persistence.feedback_repo import PostgresFeedbackRepository
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.employee import Employee, UserRole
from core.domain.employer import Employer
from core.domain.feedback import Feedback, FeedbackRating
from core.ports.repository_ports import FeedbackRepository


async def _make_message(db_session: AsyncSession) -> tuple[UUID, Message]:
    employer = await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))
    employee = await PostgresEmployeeRepository(db_session).create(
        Employee(
            employer_id=employer.id,
            email=f"employee-{uuid4()}@acme.example",
            hashed_password="hashed",
            full_name="Employee",
            role=UserRole.EMPLOYEE,
        )
    )
    conversation = await PostgresConversationRepository(db_session).create(
        Conversation(employee_id=employee.id, employer_id=employer.id)
    )
    message = await PostgresMessageRepository(db_session).create(
        Message(
            conversation_id=conversation.id,
            employer_id=employer.id,
            role=MessageRole.ASSISTANT,
            content="Your deductible is $500.",
        )
    )
    return employer.id, message


def test_is_a_feedback_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresFeedbackRepository(db_session), FeedbackRepository)


async def test_create_then_get_round_trips_the_feedback_including_rating(
    db_session: AsyncSession,
) -> None:
    employer_id, message = await _make_message(db_session)
    repo = PostgresFeedbackRepository(db_session)
    feedback = Feedback(
        message_id=message.id,
        conversation_id=message.conversation_id,
        employer_id=employer_id,
        rating=FeedbackRating.THUMBS_UP,
        comment="Very helpful",
    )

    await repo.create(feedback)
    fetched = await repo.get(feedback.id)

    assert fetched is not None
    assert fetched.rating == FeedbackRating.THUMBS_UP
    assert fetched.comment == "Very helpful"


async def test_list_by_employer_only_returns_that_employers_feedback(
    db_session: AsyncSession,
) -> None:
    employer_id, message = await _make_message(db_session)
    other_employer_id, other_message = await _make_message(db_session)
    repo = PostgresFeedbackRepository(db_session)
    await repo.create(
        Feedback(
            message_id=message.id,
            conversation_id=message.conversation_id,
            employer_id=employer_id,
            rating=FeedbackRating.THUMBS_UP,
        )
    )
    await repo.create(
        Feedback(
            message_id=other_message.id,
            conversation_id=other_message.conversation_id,
            employer_id=other_employer_id,
            rating=FeedbackRating.THUMBS_DOWN,
        )
    )

    result = await repo.list_by_employer(employer_id)

    assert len(result) == 1
    assert result[0].rating == FeedbackRating.THUMBS_UP


async def test_list_all_with_no_filter_spans_every_employer(db_session: AsyncSession) -> None:
    employer_id, message = await _make_message(db_session)
    other_employer_id, other_message = await _make_message(db_session)
    repo = PostgresFeedbackRepository(db_session)
    await repo.create(
        Feedback(
            message_id=message.id,
            conversation_id=message.conversation_id,
            employer_id=employer_id,
            rating=FeedbackRating.THUMBS_UP,
        )
    )
    await repo.create(
        Feedback(
            message_id=other_message.id,
            conversation_id=other_message.conversation_id,
            employer_id=other_employer_id,
            rating=FeedbackRating.THUMBS_DOWN,
        )
    )

    result = await repo.list_all()

    assert len(result) == 2


async def test_list_all_filters_by_employer(db_session: AsyncSession) -> None:
    employer_id, message = await _make_message(db_session)
    other_employer_id, other_message = await _make_message(db_session)
    repo = PostgresFeedbackRepository(db_session)
    await repo.create(
        Feedback(
            message_id=message.id,
            conversation_id=message.conversation_id,
            employer_id=employer_id,
            rating=FeedbackRating.THUMBS_UP,
        )
    )
    await repo.create(
        Feedback(
            message_id=other_message.id,
            conversation_id=other_message.conversation_id,
            employer_id=other_employer_id,
            rating=FeedbackRating.THUMBS_DOWN,
        )
    )

    result = await repo.list_all(employer_id=employer_id)

    assert [f.employer_id for f in result] == [employer_id]


async def test_update_changes_rating_and_comment(db_session: AsyncSession) -> None:
    employer_id, message = await _make_message(db_session)
    repo = PostgresFeedbackRepository(db_session)
    feedback = await repo.create(
        Feedback(
            message_id=message.id,
            conversation_id=message.conversation_id,
            employer_id=employer_id,
            rating=FeedbackRating.THUMBS_UP,
        )
    )

    feedback.rating = FeedbackRating.THUMBS_DOWN
    feedback.comment = "Changed my mind"
    updated = await repo.update(feedback)

    assert updated.rating == FeedbackRating.THUMBS_DOWN
    assert updated.comment == "Changed my mind"


async def test_update_on_a_nonexistent_feedback_raises(db_session: AsyncSession) -> None:
    employer_id, message = await _make_message(db_session)
    repo = PostgresFeedbackRepository(db_session)
    ghost = Feedback(
        message_id=message.id,
        conversation_id=message.conversation_id,
        employer_id=employer_id,
        rating=FeedbackRating.THUMBS_UP,
    )

    with pytest.raises(ValueError, match="does not exist"):
        await repo.update(ghost)


async def test_delete_removes_the_feedback(db_session: AsyncSession) -> None:
    employer_id, message = await _make_message(db_session)
    repo = PostgresFeedbackRepository(db_session)
    feedback = await repo.create(
        Feedback(
            message_id=message.id,
            conversation_id=message.conversation_id,
            employer_id=employer_id,
            rating=FeedbackRating.THUMBS_UP,
        )
    )

    await repo.delete(feedback.id)

    assert await repo.get(feedback.id) is None
