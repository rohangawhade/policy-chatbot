"""Registers the app's standard event-bus subscribers onto a freshly
constructed `EventBusPort` instance.

Closes the standing gap tracked in IMPLEMENTATION_STATUS.md since Step
6.1: events were published (`GuardrailsService.check()`, Step 6.1) but
nothing ever subscribed to persist them, because nowhere in the app
called `EventBusPort.subscribe()`. `api/dependencies.py`'s
`get_event_bus()` calls `register_default_subscribers()` on every fresh
`InMemoryEventBus()` it builds — a subscription only lives as long as
the bus instance holding it (files/plan.md's fresh-bus-per-request
pattern, established Step 9.2), so registration has to happen at the
same place construction does.

Lives under `api/` rather than `adapters/event_bus/` because a
subscriber here needs a concrete `AnalyticsRepository` — `adapters/` may
only import `core/ports/`, `core/domain/`, and external libraries
(files/coding-standards.md section 3), never wire one port's adapter
into another's. `api/` is the one layer allowed to import
`core/services/`/`adapters/` for DI wiring, and registering a subscriber
is exactly that: wiring, not domain logic.
"""

from core.domain.analytics import GuardrailRejection
from core.domain.events import DomainEvent, GuardrailRejectionEvent
from core.ports.event_bus_port import EventBusPort
from core.ports.repository_ports import AnalyticsRepository


def register_default_subscribers(
    event_bus: EventBusPort, *, analytics_repository: AnalyticsRepository
) -> None:
    """Wire every subscriber the app currently needs.

    Only `GuardrailRejectionEvent` has a subscriber today —
    `GET /api/admin/guardrail-rejections` (Step 9.6) is the first
    consumer of the persisted rows. Other events (`ChatMessageReceivedEvent`,
    `DocumentVersionReplacedEvent`, etc.) are published into a void still;
    add a handler here when something actually needs to react to one,
    rather than pre-wiring every event speculatively.
    """

    async def _persist_guardrail_rejection(event: DomainEvent) -> None:
        assert isinstance(event, GuardrailRejectionEvent)
        await analytics_repository.record_guardrail_rejection(
            GuardrailRejection(
                employer_id=event.employer_id,
                query_text=event.query_text,
                rejection_reason=event.rejection_reason,
            )
        )

    event_bus.subscribe(GuardrailRejectionEvent.event_type, _persist_guardrail_rejection)
