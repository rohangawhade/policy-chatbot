"""In-process implementation of `EventBusPort`.

Dev/test default, and the production bus until cross-process delivery is
actually needed. Swap this for `KafkaEventBus` (or any other
`EventBusPort` implementation) by writing one new adapter class — nothing
in `core/` changes, since callers only ever depend on the port.
"""

import inspect
from collections import defaultdict

import structlog

from core.domain.events import DomainEvent
from core.ports.event_bus_port import EventBusPort, EventHandler

logger = structlog.get_logger(__name__)


class InMemoryEventBus(EventBusPort):
    """Dispatches events to subscribed handlers via an in-memory dict.

    Keyed by `event_type` string (not the event class) so handlers can
    subscribe without importing every concrete event class.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception(
                    "event_handler_failed",
                    event_type=event.event_type,
                    handler=getattr(handler, "__qualname__", repr(handler)),
                )

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type)
        if handlers is None or handler not in handlers:
            logger.warning("unsubscribe_handler_not_found", event_type=event_type)
            return
        handlers.remove(handler)
