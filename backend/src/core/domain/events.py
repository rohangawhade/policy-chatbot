"""Domain event base type.

Concrete event classes (DocumentUploadedEvent, ChatMessageReceivedEvent,
etc.) are added in Step 2.3. This base exists now because EventBusPort
(Step 2.2) needs a type to publish/subscribe against.

Frozen + keyword-only per files/coding-standards.md section 17: "Each
event is a frozen dataclass with a timestamp, event_type, and payload."
kw_only avoids the classic dataclass-inheritance trap where a subclass
field without a default can't follow a base field that has one.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_type: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
