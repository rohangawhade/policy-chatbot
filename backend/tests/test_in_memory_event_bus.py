from uuid import uuid4

from adapters.event_bus.in_memory_event_bus import InMemoryEventBus
from core.domain.events import DocumentProcessedEvent, DocumentUploadedEvent
from core.ports.event_bus_port import EventBusPort


def _uploaded_event() -> DocumentUploadedEvent:
    return DocumentUploadedEvent(document_id=uuid4(), employer_id=uuid4(), title="SPD.pdf")


def test_is_an_event_bus_port() -> None:
    assert isinstance(InMemoryEventBus(), EventBusPort)


async def test_publish_dispatches_to_a_sync_handler_subscribed_to_the_event_type() -> None:
    bus = InMemoryEventBus()
    received: list[DocumentUploadedEvent] = []

    def handler(event: DocumentUploadedEvent) -> None:
        received.append(event)

    bus.subscribe("document.uploaded", handler)  # type: ignore[arg-type]
    event = _uploaded_event()

    await bus.publish(event)

    assert received == [event]


async def test_publish_dispatches_to_an_async_handler_and_awaits_it() -> None:
    bus = InMemoryEventBus()
    received: list[DocumentUploadedEvent] = []

    async def handler(event: DocumentUploadedEvent) -> None:
        received.append(event)

    bus.subscribe("document.uploaded", handler)  # type: ignore[arg-type]
    event = _uploaded_event()

    await bus.publish(event)

    assert received == [event]


async def test_publish_dispatches_to_multiple_handlers_in_subscription_order() -> None:
    bus = InMemoryEventBus()
    calls: list[str] = []

    def first(event: DocumentUploadedEvent) -> None:
        calls.append("first")

    async def second(event: DocumentUploadedEvent) -> None:
        calls.append("second")

    bus.subscribe("document.uploaded", first)  # type: ignore[arg-type]
    bus.subscribe("document.uploaded", second)  # type: ignore[arg-type]

    await bus.publish(_uploaded_event())

    assert calls == ["first", "second"]


async def test_publish_only_invokes_handlers_subscribed_to_the_matching_event_type() -> None:
    bus = InMemoryEventBus()
    uploaded_calls: list[DocumentUploadedEvent] = []
    processed_calls: list[DocumentProcessedEvent] = []

    bus.subscribe("document.uploaded", uploaded_calls.append)  # type: ignore[arg-type]
    bus.subscribe("document.processed", processed_calls.append)  # type: ignore[arg-type]

    await bus.publish(_uploaded_event())

    assert len(uploaded_calls) == 1
    assert processed_calls == []


async def test_publish_with_no_subscribers_does_not_raise() -> None:
    bus = InMemoryEventBus()

    await bus.publish(_uploaded_event())


async def test_a_failing_handler_does_not_prevent_other_handlers_from_running() -> None:
    bus = InMemoryEventBus()
    calls: list[str] = []

    def failing(event: DocumentUploadedEvent) -> None:
        raise RuntimeError("boom")

    def healthy(event: DocumentUploadedEvent) -> None:
        calls.append("healthy")

    bus.subscribe("document.uploaded", failing)  # type: ignore[arg-type]
    bus.subscribe("document.uploaded", healthy)  # type: ignore[arg-type]

    await bus.publish(_uploaded_event())

    assert calls == ["healthy"]


async def test_a_failing_async_handler_does_not_prevent_other_handlers_from_running() -> None:
    bus = InMemoryEventBus()
    calls: list[str] = []

    async def failing(event: DocumentUploadedEvent) -> None:
        raise RuntimeError("boom")

    def healthy(event: DocumentUploadedEvent) -> None:
        calls.append("healthy")

    bus.subscribe("document.uploaded", failing)  # type: ignore[arg-type]
    bus.subscribe("document.uploaded", healthy)  # type: ignore[arg-type]

    await bus.publish(_uploaded_event())

    assert calls == ["healthy"]


async def test_unsubscribed_handler_is_not_called_on_publish() -> None:
    bus = InMemoryEventBus()
    received: list[DocumentUploadedEvent] = []

    def handler(event: DocumentUploadedEvent) -> None:
        received.append(event)

    bus.subscribe("document.uploaded", handler)  # type: ignore[arg-type]
    bus.unsubscribe("document.uploaded", handler)  # type: ignore[arg-type]

    await bus.publish(_uploaded_event())

    assert received == []


def test_unsubscribe_an_unknown_event_type_does_not_raise() -> None:
    bus = InMemoryEventBus()

    bus.unsubscribe("never.subscribed", lambda event: None)  # type: ignore[arg-type]


def test_unsubscribe_a_handler_not_in_the_list_does_not_raise() -> None:
    bus = InMemoryEventBus()

    def one(event: DocumentUploadedEvent) -> None:
        pass

    def two(event: DocumentUploadedEvent) -> None:
        pass

    bus.subscribe("document.uploaded", one)  # type: ignore[arg-type]

    bus.unsubscribe("document.uploaded", two)  # type: ignore[arg-type]
