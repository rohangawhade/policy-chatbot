from datetime import datetime
from uuid import UUID, uuid4

from adapters.event_bus.in_memory_event_bus import InMemoryEventBus
from api.event_subscribers import register_default_subscribers
from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.events import DocumentUploadedEvent, GuardrailRejectionEvent
from core.ports.repository_ports import AnalyticsRepository


class FakeAnalyticsRepository(AnalyticsRepository):
    def __init__(self) -> None:
        self.guardrail_rejections: list[GuardrailRejection] = []

    async def record_llm_cost(self, log: LLMCostLog) -> None:
        raise NotImplementedError

    async def record_latency(self, log: RequestLatencyLog) -> None:
        raise NotImplementedError

    async def record_flagged_response(self, flagged: FlaggedResponse) -> None:
        raise NotImplementedError

    async def record_guardrail_rejection(self, rejection: GuardrailRejection) -> None:
        self.guardrail_rejections.append(rejection)

    async def list_llm_costs(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[LLMCostLog]:
        raise NotImplementedError

    async def list_latencies(
        self,
        *,
        employer_id: UUID | None = None,
        model_tier: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[RequestLatencyLog]:
        raise NotImplementedError

    async def list_flagged_responses(
        self, *, employer_id: UUID | None = None, status: FlaggedResponseStatus | None = None
    ) -> list[FlaggedResponse]:
        raise NotImplementedError

    async def get_flagged_response(self, flagged_response_id: UUID) -> FlaggedResponse | None:
        raise NotImplementedError

    async def update_flagged_response_status(
        self, flagged_response_id: UUID, status: FlaggedResponseStatus
    ) -> FlaggedResponse:
        raise NotImplementedError

    async def list_guardrail_rejections(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[GuardrailRejection]:
        return [r for r in self.guardrail_rejections if r.employer_id == employer_id]


async def test_registered_subscriber_persists_a_guardrail_rejection_on_publish() -> None:
    event_bus = InMemoryEventBus()
    analytics_repository = FakeAnalyticsRepository()
    register_default_subscribers(event_bus, analytics_repository=analytics_repository)
    employer_id = uuid4()

    await event_bus.publish(
        GuardrailRejectionEvent(
            employer_id=employer_id,
            query_text="what's the weather today?",
            rejection_reason="off_topic",
        )
    )

    assert len(analytics_repository.guardrail_rejections) == 1
    rejection = analytics_repository.guardrail_rejections[0]
    assert rejection.employer_id == employer_id
    assert rejection.query_text == "what's the weather today?"
    assert rejection.rejection_reason == "off_topic"


async def test_registered_subscriber_ignores_unrelated_event_types() -> None:
    event_bus = InMemoryEventBus()
    analytics_repository = FakeAnalyticsRepository()
    register_default_subscribers(event_bus, analytics_repository=analytics_repository)

    await event_bus.publish(
        DocumentUploadedEvent(document_id=uuid4(), employer_id=uuid4(), title="Handbook")
    )

    assert analytics_repository.guardrail_rejections == []
