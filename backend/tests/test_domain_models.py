from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.document import Document, DocumentChunk, DocumentStatus
from core.domain.employee import Employee, UserRole
from core.domain.employer import Employer
from core.domain.events import DomainEvent
from core.domain.feedback import Feedback, FeedbackRating
from core.domain.policy import Enrollment, Policy, PolicyType


def test_employer_has_sane_defaults() -> None:
    employer = Employer(name="Acme Corp")

    assert employer.is_active is True
    assert employer.id is not None
    assert employer.created_at is not None


def test_employee_admin_role_allows_no_employer() -> None:
    admin = Employee(
        employer_id=None,
        email="admin@policypal.dev",
        hashed_password="hashed",
        full_name="Site Admin",
        role=UserRole.ADMIN,
    )

    assert admin.employer_id is None
    assert admin.role == UserRole.ADMIN


def test_employee_requires_role() -> None:
    with pytest.raises(ValidationError):
        Employee(
            employer_id=uuid4(),
            email="e@example.com",
            hashed_password="hashed",
            full_name="Someone",
        )  # type: ignore[call-arg]


def test_policy_and_enrollment_construction() -> None:
    employer_id = uuid4()
    policy = Policy(employer_id=employer_id, policy_type=PolicyType.DENTAL, name="Dental Basic")
    enrollment = Enrollment(employee_id=uuid4(), policy_id=policy.id)

    assert policy.policy_type == PolicyType.DENTAL
    assert enrollment.is_active is True


def test_document_defaults_to_processing_status() -> None:
    document = Document(
        employer_id=uuid4(),
        title="2026 Benefits Guide",
        source_type="pdf",
        source_path="s3://bucket/doc.pdf",
    )

    assert document.status == DocumentStatus.PROCESSING
    assert document.version == 1


def test_document_chunk_links_to_document_and_employer() -> None:
    document_id = uuid4()
    employer_id = uuid4()
    chunk = DocumentChunk(
        document_id=document_id,
        employer_id=employer_id,
        chunk_index=0,
        text="Deductibles reset every January.",
    )

    assert chunk.document_id == document_id
    assert chunk.employer_id == employer_id
    assert chunk.is_active is True


def test_conversation_and_message_construction() -> None:
    employer_id = uuid4()
    conversation = Conversation(employee_id=uuid4(), employer_id=employer_id)
    message = Message(
        conversation_id=conversation.id,
        employer_id=employer_id,
        role=MessageRole.ASSISTANT,
        content="Your deductible is $500.",
    )

    assert message.role == MessageRole.ASSISTANT
    assert message.conversation_id == conversation.id


def test_feedback_rating_enum_values() -> None:
    feedback = Feedback(
        message_id=uuid4(),
        conversation_id=uuid4(),
        employer_id=uuid4(),
        rating=FeedbackRating.THUMBS_DOWN,
    )

    assert feedback.rating == FeedbackRating.THUMBS_DOWN
    assert feedback.comment is None


def test_llm_cost_log_construction() -> None:
    log = LLMCostLog(
        employer_id=uuid4(),
        model="claude-haiku-4-5-20251001",
        model_tier="cheap",
        input_tokens=120,
        output_tokens=45,
        estimated_cost_usd=0.0023,
    )

    assert log.model_tier == "cheap"
    assert log.query_complexity_score is None


def test_request_latency_log_construction() -> None:
    log = RequestLatencyLog(employer_id=uuid4(), total_ms=1820, retrieval_ms=340, llm_ms=1400)

    assert log.total_ms == 1820


def test_flagged_response_defaults_to_pending_review() -> None:
    flagged = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="what's my HSA limit?",
        flag_reason="low_retrieval_confidence",
    )

    assert flagged.status == FlaggedResponseStatus.PENDING_REVIEW


def test_guardrail_rejection_construction() -> None:
    rejection = GuardrailRejection(
        employer_id=uuid4(),
        query_text="what's the weather today?",
        rejection_reason="off_topic",
    )

    assert rejection.rejection_reason == "off_topic"


def test_domain_models_construct_from_orm_style_objects_via_from_attributes() -> None:
    """The from_attributes=True config lets Phase 3 repository adapters map
    ORM rows to domain models without hand-written field-by-field code."""

    class _FakeOrmEmployer:
        def __init__(self) -> None:
            from datetime import UTC, datetime

            self.id = uuid4()
            self.name = "Acme Corp"
            self.is_active = True
            self.created_at = datetime.now(UTC)
            self.updated_at = datetime.now(UTC)

    domain_employer = Employer.model_validate(_FakeOrmEmployer())

    assert domain_employer.name == "Acme Corp"


def test_domain_event_has_type_and_timestamp() -> None:
    event = DomainEvent(event_type="document.uploaded")

    assert event.event_type == "document.uploaded"
    assert event.timestamp is not None


def test_domain_event_is_frozen() -> None:
    event = DomainEvent(event_type="document.uploaded")

    with pytest.raises(AttributeError):
        event.event_type = "document.processed"  # type: ignore[misc]


def test_domain_event_subclass_can_add_required_fields_without_ordering_errors() -> None:
    """kw_only=True on the base avoids the classic dataclass-inheritance
    trap where a required subclass field can't follow a base field that
    has a default."""
    from dataclasses import dataclass
    from uuid import UUID

    @dataclass(frozen=True, kw_only=True)
    class _DocumentUploadedEvent(DomainEvent):
        document_id: UUID
        employer_id: UUID

    document_id = uuid4()
    employer_id = uuid4()
    event = _DocumentUploadedEvent(
        event_type="document.uploaded", document_id=document_id, employer_id=employer_id
    )

    assert event.document_id == document_id
    assert event.employer_id == employer_id
