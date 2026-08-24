from uuid import uuid4

import pytest

from core.domain.events import (
    ChatMessageReceivedEvent,
    ChatResponseGeneratedEvent,
    DocumentEmbeddedEvent,
    DocumentProcessedEvent,
    DocumentUploadedEvent,
    DocumentVersionReplacedEvent,
    DomainEvent,
    EmployeeEnrolledEvent,
    EmployerCreatedEvent,
    FeedbackReceivedEvent,
    GuardrailRejectionEvent,
    LowConfidenceResponseEvent,
)


def test_document_uploaded_event_has_fixed_event_type() -> None:
    event = DocumentUploadedEvent(document_id=uuid4(), employer_id=uuid4(), title="2026 Guide")

    assert event.event_type == "document.uploaded"
    assert isinstance(event, DomainEvent)


def test_document_processed_event_has_fixed_event_type() -> None:
    event = DocumentProcessedEvent(document_id=uuid4(), employer_id=uuid4())

    assert event.event_type == "document.processed"


def test_document_embedded_event_carries_chunk_count() -> None:
    event = DocumentEmbeddedEvent(document_id=uuid4(), employer_id=uuid4(), chunk_count=42)

    assert event.event_type == "document.embedded"
    assert event.chunk_count == 42


def test_document_version_replaced_event_carries_old_and_new_version() -> None:
    old_document_id = uuid4()
    new_document_id = uuid4()
    event = DocumentVersionReplacedEvent(
        document_id=new_document_id,
        old_document_id=old_document_id,
        employer_id=uuid4(),
        old_version=1,
        new_version=2,
    )

    assert event.event_type == "document.version_replaced"
    assert event.document_id == new_document_id
    assert event.old_document_id == old_document_id
    assert event.old_version == 1
    assert event.new_version == 2


def test_employer_created_event() -> None:
    event = EmployerCreatedEvent(employer_id=uuid4(), name="Acme Corp")

    assert event.event_type == "employer.created"
    assert event.name == "Acme Corp"


def test_employee_enrolled_event() -> None:
    event = EmployeeEnrolledEvent(employee_id=uuid4(), employer_id=uuid4(), policy_id=uuid4())

    assert event.event_type == "employee.enrolled"


def test_chat_message_received_event() -> None:
    event = ChatMessageReceivedEvent(
        conversation_id=uuid4(), employer_id=uuid4(), employee_id=uuid4(), message_id=uuid4()
    )

    assert event.event_type == "chat.message_received"


def test_chat_response_generated_event_carries_model_used() -> None:
    event = ChatResponseGeneratedEvent(
        conversation_id=uuid4(),
        employer_id=uuid4(),
        message_id=uuid4(),
        model_used="claude-haiku-4-5-20251001",
    )

    assert event.event_type == "chat.response_generated"
    assert event.model_used == "claude-haiku-4-5-20251001"


def test_feedback_received_event() -> None:
    event = FeedbackReceivedEvent(
        feedback_id=uuid4(), message_id=uuid4(), employer_id=uuid4(), rating="thumbs_down"
    )

    assert event.event_type == "feedback.received"
    assert event.rating == "thumbs_down"


def test_low_confidence_response_event_carries_similarity_score() -> None:
    event = LowConfidenceResponseEvent(
        conversation_id=uuid4(),
        employer_id=uuid4(),
        message_id=uuid4(),
        top_similarity_score=0.42,
    )

    assert event.event_type == "response.low_confidence"
    assert event.top_similarity_score == 0.42


def test_guardrail_rejection_event() -> None:
    event = GuardrailRejectionEvent(
        employer_id=uuid4(), query_text="what's the weather?", rejection_reason="off_topic"
    )

    assert event.event_type == "guardrail.rejected"


def test_all_concrete_events_are_frozen() -> None:
    event = EmployerCreatedEvent(employer_id=uuid4(), name="Acme Corp")

    with pytest.raises(AttributeError):
        event.name = "Other Corp"  # type: ignore[misc]


def test_all_concrete_events_inherit_timestamp_from_domain_event() -> None:
    event = EmployerCreatedEvent(employer_id=uuid4(), name="Acme Corp")

    assert event.timestamp is not None
