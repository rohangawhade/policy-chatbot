"""SQLAlchemy ORM models.

These are persistence-layer models only — never imported by core/. Services
depend on repository ports and pure domain models (core/domain/, added in
Phase 2); repository adapters (Phase 3) map between the two.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    # timezone=True is required: domain models (Step 2.1) generate
    # timezone-aware `datetime.now(UTC)` values, which asyncpg refuses to
    # bind into a naive `TIMESTAMP WITHOUT TIME ZONE` column (SQLAlchemy's
    # default for a bare `Mapped[datetime]`).
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserRole(PyEnum):
    ADMIN = "admin"
    EMPLOYER = "employer"
    EMPLOYEE = "employee"


class PolicyType(PyEnum):
    HEALTH = "health"
    DENTAL = "dental"
    VISION = "vision"
    LIFE = "life"
    DISABILITY = "disability"


class DocumentStatus(PyEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MessageRole(PyEnum):
    USER = "user"
    ASSISTANT = "assistant"


class FeedbackRating(PyEnum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class FlaggedResponseStatus(PyEnum):
    PENDING_REVIEW = "pending_review"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class Employer(Base, TimestampMixin):
    __tablename__ = "employers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    employees: Mapped[list["Employee"]] = relationship(back_populates="employer")
    policies: Mapped[list["Policy"]] = relationship(back_populates="employer")
    documents: Mapped[list["Document"]] = relationship(back_populates="employer")


class Employee(Base, TimestampMixin):
    """The login principal — every user (admin, employer contact, or
    individual employee) is a row here, distinguished by `role`."""

    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("email", name="uq_employees_email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employers.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    employer: Mapped[Employer | None] = relationship(back_populates="employees")
    enrollments: Mapped[list["EmployeePolicy"]] = relationship(back_populates="employee")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="employee")


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    policy_type: Mapped[PolicyType] = mapped_column(Enum(PolicyType, name="policy_type"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    employer: Mapped[Employer] = relationship(back_populates="policies")
    enrollments: Mapped[list["EmployeePolicy"]] = relationship(back_populates="policy")


class EmployeePolicy(Base):
    """Enrollment: which employee is enrolled in which policy."""

    __tablename__ = "employee_policies"
    __table_args__ = (UniqueConstraint("employee_id", "policy_id", name="uq_employee_policy"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policies.id"), index=True)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    employee: Mapped[Employee] = relationship(back_populates="enrollments")
    policy: Mapped[Policy] = relationship(back_populates="enrollments")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    policy_type: Mapped[PolicyType | None] = mapped_column(Enum(PolicyType, name="policy_type"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"), default=DocumentStatus.PROCESSING
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    employer: Mapped[Employer] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(512))
    page_number: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), index=True)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255))

    employee: Mapped[Employee] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="message")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    rating: Mapped[FeedbackRating] = mapped_column(Enum(FeedbackRating, name="feedback_rating"))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped[Message] = relationship(back_populates="feedback")


class LLMCostLog(Base):
    __tablename__ = "llm_cost_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    model_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    query_complexity_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequestLatencyLog(Base):
    __tablename__ = "request_latency_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    total_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_ms: Mapped[int | None] = mapped_column(Integer)
    llm_ms: Mapped[int | None] = mapped_column(Integer)
    overhead_ms: Mapped[int | None] = mapped_column(Integer)
    model_tier: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FlaggedResponse(Base, TimestampMixin):
    __tablename__ = "flagged_responses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    top_similarity_score: Mapped[float | None] = mapped_column(Float)
    flag_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[FlaggedResponseStatus] = mapped_column(
        Enum(FlaggedResponseStatus, name="flagged_response_status"),
        default=FlaggedResponseStatus.PENDING_REVIEW,
    )


class GuardrailRejection(Base):
    __tablename__ = "guardrail_rejections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
