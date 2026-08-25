from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from adapters.persistence.analytics_repo import PostgresAnalyticsRepository
from adapters.persistence.conversation_repo import (
    PostgresConversationRepository,
    PostgresMessageRepository,
)
from adapters.persistence.employee_repo import PostgresEmployeeRepository
from adapters.persistence.employer_repo import PostgresEmployerRepository
from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.employee import Employee, UserRole
from core.domain.employer import Employer
from core.domain.policy import PolicyType
from core.ports.repository_ports import AnalyticsRepository


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
            content="answer",
        )
    )
    return employer.id, message


def test_is_an_analytics_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresAnalyticsRepository(db_session), AnalyticsRepository)


async def test_record_llm_cost_persists_the_log(db_session: AsyncSession) -> None:
    employer = await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))
    repo = PostgresAnalyticsRepository(db_session)
    log = LLMCostLog(
        employer_id=employer.id,
        model="claude-haiku-4-5-20251001",
        model_tier="cheap",
        input_tokens=1200,
        output_tokens=450,
        estimated_cost_usd=0.0023,
        query_complexity_score=0.3,
    )

    await repo.record_llm_cost(log)

    # `AnalyticsRepository`'s port has no list method for cost logs (only
    # for flagged responses / guardrail rejections), so verifying
    # persistence means querying the ORM table directly.
    row = await db_session.get(models.LLMCostLog, log.id)
    assert row is not None
    assert row.model == "claude-haiku-4-5-20251001"
    assert row.estimated_cost_usd == 0.0023


async def test_record_latency_persists_the_log(db_session: AsyncSession) -> None:
    employer = await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))
    repo = PostgresAnalyticsRepository(db_session)
    log = RequestLatencyLog(
        employer_id=employer.id,
        total_ms=1820,
        retrieval_ms=340,
        llm_ms=1400,
        overhead_ms=80,
        model_tier="cheap",
    )

    await repo.record_latency(log)

    row = await db_session.get(models.RequestLatencyLog, log.id)
    assert row is not None
    assert row.total_ms == 1820


async def test_record_flagged_response_and_list_flagged_responses(
    db_session: AsyncSession,
) -> None:
    employer_id, message = await _make_message(db_session)
    repo = PostgresAnalyticsRepository(db_session)
    flagged = FlaggedResponse(
        employer_id=employer_id,
        conversation_id=message.conversation_id,
        message_id=message.id,
        query_text="what's my HSA limit?",
        top_similarity_score=0.42,
        flag_reason="low_retrieval_confidence",
        policy_type=PolicyType.HEALTH,
    )

    await repo.record_flagged_response(flagged)
    result = await repo.list_flagged_responses(employer_id=employer_id)

    assert len(result) == 1
    assert result[0].flag_reason == "low_retrieval_confidence"
    assert result[0].status == FlaggedResponseStatus.PENDING_REVIEW
    assert result[0].policy_type == PolicyType.HEALTH


async def test_list_flagged_responses_filters_by_status(db_session: AsyncSession) -> None:
    employer_id, message = await _make_message(db_session)
    repo = PostgresAnalyticsRepository(db_session)
    await repo.record_flagged_response(
        FlaggedResponse(
            employer_id=employer_id,
            conversation_id=message.conversation_id,
            message_id=message.id,
            query_text="q1",
            flag_reason="low_confidence",
            status=FlaggedResponseStatus.PENDING_REVIEW,
        )
    )
    await repo.record_flagged_response(
        FlaggedResponse(
            employer_id=employer_id,
            conversation_id=message.conversation_id,
            message_id=message.id,
            query_text="q2",
            flag_reason="low_confidence",
            status=FlaggedResponseStatus.DISMISSED,
        )
    )

    pending = await repo.list_flagged_responses(
        employer_id=employer_id, status=FlaggedResponseStatus.PENDING_REVIEW
    )

    assert [f.query_text for f in pending] == ["q1"]


async def test_list_flagged_responses_only_returns_that_employers_records(
    db_session: AsyncSession,
) -> None:
    employer_id, message = await _make_message(db_session)
    other_employer_id, other_message = await _make_message(db_session)
    repo = PostgresAnalyticsRepository(db_session)
    await repo.record_flagged_response(
        FlaggedResponse(
            employer_id=employer_id,
            conversation_id=message.conversation_id,
            message_id=message.id,
            query_text="mine",
            flag_reason="low_confidence",
        )
    )
    await repo.record_flagged_response(
        FlaggedResponse(
            employer_id=other_employer_id,
            conversation_id=other_message.conversation_id,
            message_id=other_message.id,
            query_text="not mine",
            flag_reason="low_confidence",
        )
    )

    result = await repo.list_flagged_responses(employer_id=employer_id)

    assert [f.query_text for f in result] == ["mine"]


async def test_record_guardrail_rejection_and_list_guardrail_rejections(
    db_session: AsyncSession,
) -> None:
    employer = await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))
    repo = PostgresAnalyticsRepository(db_session)
    rejection = GuardrailRejection(
        employer_id=employer.id,
        query_text="what's the weather today?",
        rejection_reason="off_topic",
    )

    await repo.record_guardrail_rejection(rejection)
    result = await repo.list_guardrail_rejections(employer_id=employer.id)

    assert len(result) == 1
    assert result[0].rejection_reason == "off_topic"


async def test_list_guardrail_rejections_only_returns_that_employers_records(
    db_session: AsyncSession,
) -> None:
    employer_a = await PostgresEmployerRepository(db_session).create(Employer(name="A Corp"))
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="B Corp"))
    repo = PostgresAnalyticsRepository(db_session)
    await repo.record_guardrail_rejection(
        GuardrailRejection(employer_id=employer_a.id, query_text="q", rejection_reason="off_topic")
    )
    await repo.record_guardrail_rejection(
        GuardrailRejection(employer_id=employer_b.id, query_text="q", rejection_reason="off_topic")
    )

    result = await repo.list_guardrail_rejections(employer_id=employer_a.id)

    assert len(result) == 1


async def test_list_guardrail_rejections_filters_by_date_range(db_session: AsyncSession) -> None:
    employer = await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))
    repo = PostgresAnalyticsRepository(db_session)
    await repo.record_guardrail_rejection(
        GuardrailRejection(employer_id=employer.id, query_text="q", rejection_reason="off_topic")
    )

    future_start = datetime.now(UTC) + timedelta(days=1)
    assert await repo.list_guardrail_rejections(start=future_start) == []

    past_end = datetime.now(UTC) - timedelta(days=1)
    assert await repo.list_guardrail_rejections(end=past_end) == []


async def test_list_llm_costs_with_no_filters_spans_every_employer(
    db_session: AsyncSession,
) -> None:
    employer_a = await PostgresEmployerRepository(db_session).create(Employer(name="A Corp"))
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="B Corp"))
    repo = PostgresAnalyticsRepository(db_session)
    for employer in (employer_a, employer_b):
        await repo.record_llm_cost(
            LLMCostLog(
                employer_id=employer.id,
                model="claude-haiku-4-5-20251001",
                model_tier="cheap",
                input_tokens=10,
                output_tokens=5,
                estimated_cost_usd=0.001,
            )
        )

    result = await repo.list_llm_costs()

    assert len(result) == 2


async def test_list_llm_costs_filters_by_employer_and_date_range(db_session: AsyncSession) -> None:
    employer = await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))
    other_employer = await PostgresEmployerRepository(db_session).create(Employer(name="Other Co"))
    repo = PostgresAnalyticsRepository(db_session)
    await repo.record_llm_cost(
        LLMCostLog(
            employer_id=employer.id,
            model="claude-haiku-4-5-20251001",
            model_tier="cheap",
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.001,
        )
    )
    await repo.record_llm_cost(
        LLMCostLog(
            employer_id=other_employer.id,
            model="claude-haiku-4-5-20251001",
            model_tier="cheap",
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.002,
        )
    )

    scoped = await repo.list_llm_costs(employer_id=employer.id)
    assert len(scoped) == 1
    assert scoped[0].employer_id == employer.id

    future_start = datetime.now(UTC) + timedelta(days=1)
    assert await repo.list_llm_costs(start=future_start) == []

    past_end = datetime.now(UTC) - timedelta(days=1)
    assert await repo.list_llm_costs(end=past_end) == []


async def test_list_latencies_filters_by_employer_model_tier_and_date_range(
    db_session: AsyncSession,
) -> None:
    employer = await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))
    repo = PostgresAnalyticsRepository(db_session)
    await repo.record_latency(
        RequestLatencyLog(employer_id=employer.id, total_ms=100, model_tier="cheap")
    )
    await repo.record_latency(
        RequestLatencyLog(employer_id=employer.id, total_ms=900, model_tier="powerful")
    )

    cheap_only = await repo.list_latencies(employer_id=employer.id, model_tier="cheap")
    assert [log.total_ms for log in cheap_only] == [100]

    future_start = datetime.now(UTC) + timedelta(days=1)
    assert await repo.list_latencies(start=future_start) == []

    past_end = datetime.now(UTC) - timedelta(days=1)
    assert await repo.list_latencies(end=past_end) == []


async def test_get_flagged_response_returns_none_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    repo = PostgresAnalyticsRepository(db_session)

    assert await repo.get_flagged_response(uuid4()) is None


async def test_get_flagged_response_returns_the_persisted_row(db_session: AsyncSession) -> None:
    employer_id, message = await _make_message(db_session)
    repo = PostgresAnalyticsRepository(db_session)
    flagged = FlaggedResponse(
        employer_id=employer_id,
        conversation_id=message.conversation_id,
        message_id=message.id,
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    await repo.record_flagged_response(flagged)

    result = await repo.get_flagged_response(flagged.id)

    assert result is not None
    assert result.id == flagged.id


async def test_update_flagged_response_status_persists_the_new_status(
    db_session: AsyncSession,
) -> None:
    employer_id, message = await _make_message(db_session)
    repo = PostgresAnalyticsRepository(db_session)
    flagged = FlaggedResponse(
        employer_id=employer_id,
        conversation_id=message.conversation_id,
        message_id=message.id,
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    await repo.record_flagged_response(flagged)

    updated = await repo.update_flagged_response_status(flagged.id, FlaggedResponseStatus.REVIEWED)

    assert updated.status == FlaggedResponseStatus.REVIEWED
    reloaded = await repo.get_flagged_response(flagged.id)
    assert reloaded is not None
    assert reloaded.status == FlaggedResponseStatus.REVIEWED


async def test_update_flagged_response_status_raises_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    repo = PostgresAnalyticsRepository(db_session)

    with pytest.raises(ValueError, match="does not exist"):
        await repo.update_flagged_response_status(uuid4(), FlaggedResponseStatus.REVIEWED)
