"""Abstraction over inter-module event dispatch. An in-memory adapter
handles this today (Step 3.1); swapping to Kafka later means writing one
new adapter — zero core logic changes (files/plan.md's Event-Driven Ready
principle)."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from core.domain.events import DomainEvent

EventHandler = Callable[[DomainEvent], Awaitable[None] | None]
"""A subscriber may be a sync or async callable — the adapter is
responsible for awaiting async handlers."""


class EventBusPort(ABC):
    @abstractmethod
    async def publish(self, event: DomainEvent) -> None: ...

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None: ...

    @abstractmethod
    def unsubscribe(self, event_type: str, handler: EventHandler) -> None: ...
