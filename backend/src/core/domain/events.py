"""Domain events.

Every event is a frozen, keyword-only dataclass with a `timestamp`,
`event_type`, and payload (files/coding-standards.md section 17). Each
concrete event fixes its own `event_type` default so callers never pass it
by hand — `DocumentUploadedEvent(document_id=..., employer_id=..., ...)`
is enough.

`kw_only=True` on the base avoids the classic dataclass-inheritance trap
where a subclass field without a default can't follow a base field that
has one.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_type: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, kw_only=True)
class DocumentUploadedEvent(DomainEvent):
    event_type: str = "document.uploaded"
    document_id: UUID
    employer_id: UUID
    title: str


@dataclass(frozen=True, kw_only=True)
class DocumentProcessedEvent(DomainEvent):
    event_type: str = "document.processed"
    document_id: UUID
    employer_id: UUID


@dataclass(frozen=True, kw_only=True)
class DocumentEmbeddedEvent(DomainEvent):
    event_type: str = "document.embedded"
    document_id: UUID
    employer_id: UUID
    chunk_count: int


@dataclass(frozen=True, kw_only=True)
class DocumentVersionReplacedEvent(DomainEvent):
    """Old vectors purged, new ones indexed — Step 7.2.

    Each version is its own `Document` row (Step 7.1) with its own id —
    there's no shared logical-document identity to report a single
    `document_id` for, so both are carried explicitly. `document_id` is
    the new, now-current version; `old_document_id` is the one whose
    vectors/chunks were just purged/deactivated.
    """

    event_type: str = "document.version_replaced"
    document_id: UUID
    old_document_id: UUID
    employer_id: UUID
    old_version: int
    new_version: int


@dataclass(frozen=True, kw_only=True)
class EmployerCreatedEvent(DomainEvent):
    event_type: str = "employer.created"
    employer_id: UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class EmployeeEnrolledEvent(DomainEvent):
    event_type: str = "employee.enrolled"
    employee_id: UUID
    employer_id: UUID
    policy_id: UUID


@dataclass(frozen=True, kw_only=True)
class ChatMessageReceivedEvent(DomainEvent):
    event_type: str = "chat.message_received"
    conversation_id: UUID
    employer_id: UUID
    employee_id: UUID
    message_id: UUID


@dataclass(frozen=True, kw_only=True)
class ChatResponseGeneratedEvent(DomainEvent):
    event_type: str = "chat.response_generated"
    conversation_id: UUID
    employer_id: UUID
    message_id: UUID
    model_used: str


@dataclass(frozen=True, kw_only=True)
class FeedbackReceivedEvent(DomainEvent):
    event_type: str = "feedback.received"
    feedback_id: UUID
    message_id: UUID
    employer_id: UUID
    rating: str


@dataclass(frozen=True, kw_only=True)
class LowConfidenceResponseEvent(DomainEvent):
    """Auto-flagged for admin review — Step 6.5."""

    event_type: str = "response.low_confidence"
    conversation_id: UUID
    employer_id: UUID
    message_id: UUID
    top_similarity_score: float


@dataclass(frozen=True, kw_only=True)
class GuardrailRejectionEvent(DomainEvent):
    """Query blocked, logged for admin tuning — Step 6.1."""

    event_type: str = "guardrail.rejected"
    employer_id: UUID
    query_text: str
    rejection_reason: str
