from datetime import datetime
from uuid import UUID, uuid4

import pytest

from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.employer import Employer
from core.ports.repository_ports import (
    AnalyticsRepository,
    EmployeeRepository,
    EmployerRepository,
    RepositoryPort,
)


def test_repository_port_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        RepositoryPort()  # type: ignore[abstract]


def test_employer_repository_cannot_be_instantiated_without_implementing_list_all() -> None:
    class _IncompleteEmployerRepository(EmployerRepository):
        async def get(self, entity_id: UUID) -> Employer | None:
            return None

        async def create(self, entity: Employer) -> Employer:
            return entity

        async def update(self, entity: Employer) -> Employer:
            return entity

        async def delete(self, entity_id: UUID) -> None:
            return None

    with pytest.raises(TypeError):
        _IncompleteEmployerRepository()  # type: ignore[abstract]


async def test_employer_repository_concrete_implementation_satisfies_the_contract() -> None:
    class _FakeEmployerRepository(EmployerRepository):
        def __init__(self) -> None:
            self.store: dict[UUID, Employer] = {}

        async def get(self, entity_id: UUID) -> Employer | None:
            return self.store.get(entity_id)

        async def create(self, entity: Employer) -> Employer:
            self.store[entity.id] = entity
            return entity

        async def update(self, entity: Employer) -> Employer:
            self.store[entity.id] = entity
            return entity

        async def delete(self, entity_id: UUID) -> None:
            self.store.pop(entity_id, None)

        async def list_all(self) -> list[Employer]:
            return list(self.store.values())

    repo = _FakeEmployerRepository()
    employer = Employer(name="Acme Corp")

    await repo.create(employer)
    assert await repo.get(employer.id) == employer
    assert await repo.list_all() == [employer]

    await repo.delete(employer.id)
    assert await repo.get(employer.id) is None


def test_employee_repository_requires_get_by_email_and_list_by_employer() -> None:
    required = {"get_by_email", "list_by_employer"}
    declared = {name for name in vars(EmployeeRepository) if not name.startswith("_")}
    assert required <= declared


async def test_analytics_repository_concrete_implementation_satisfies_the_contract() -> None:
    class _FakeAnalyticsRepository(AnalyticsRepository):
        def __init__(self) -> None:
            self.cost_logs: list[LLMCostLog] = []
            self.latency_logs: list[RequestLatencyLog] = []
            self.flagged: list[FlaggedResponse] = []
            self.rejections: list[GuardrailRejection] = []

        async def record_llm_cost(self, log: LLMCostLog) -> None:
            self.cost_logs.append(log)

        async def record_latency(self, log: RequestLatencyLog) -> None:
            self.latency_logs.append(log)

        async def record_flagged_response(self, flagged: FlaggedResponse) -> None:
            self.flagged.append(flagged)

        async def record_guardrail_rejection(self, rejection: GuardrailRejection) -> None:
            self.rejections.append(rejection)

        async def list_llm_costs(
            self,
            *,
            employer_id: UUID | None = None,
            start: datetime | None = None,
            end: datetime | None = None,
        ) -> list[LLMCostLog]:
            return self.cost_logs

        async def list_latencies(
            self,
            *,
            employer_id: UUID | None = None,
            model_tier: str | None = None,
            start: datetime | None = None,
            end: datetime | None = None,
        ) -> list[RequestLatencyLog]:
            return self.latency_logs

        async def list_flagged_responses(
            self, *, employer_id: UUID | None = None, status: FlaggedResponseStatus | None = None
        ) -> list[FlaggedResponse]:
            if status is None:
                return self.flagged
            return [f for f in self.flagged if f.status == status]

        async def get_flagged_response(self, flagged_response_id: UUID) -> FlaggedResponse | None:
            for flagged in self.flagged:
                if flagged.id == flagged_response_id:
                    return flagged
            return None

        async def update_flagged_response_status(
            self, flagged_response_id: UUID, status: FlaggedResponseStatus
        ) -> FlaggedResponse:
            for index, flagged in enumerate(self.flagged):
                if flagged.id == flagged_response_id:
                    updated = flagged.model_copy(update={"status": status})
                    self.flagged[index] = updated
                    return updated
            raise ValueError(f"FlaggedResponse {flagged_response_id} does not exist.")

        async def list_guardrail_rejections(
            self,
            *,
            employer_id: UUID | None = None,
            start: datetime | None = None,
            end: datetime | None = None,
        ) -> list[GuardrailRejection]:
            return self.rejections

    repo = _FakeAnalyticsRepository()
    employer_id = uuid4()

    cost_log = LLMCostLog(
        employer_id=employer_id,
        model="claude-haiku-4-5-20251001",
        model_tier="cheap",
        input_tokens=100,
        output_tokens=40,
        estimated_cost_usd=0.001,
    )
    await repo.record_llm_cost(cost_log)
    assert repo.cost_logs == [cost_log]

    rejection = GuardrailRejection(
        employer_id=employer_id, query_text="weather?", rejection_reason="off_topic"
    )
    await repo.record_guardrail_rejection(rejection)
    assert await repo.list_guardrail_rejections(employer_id=employer_id) == [rejection]

    flagged = FlaggedResponse(
        employer_id=employer_id,
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    await repo.record_flagged_response(flagged)
    results = await repo.list_flagged_responses(
        employer_id=employer_id, status=FlaggedResponseStatus.PENDING_REVIEW
    )
    assert results == [flagged]
