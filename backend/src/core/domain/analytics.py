"""Pure domain models for admin observability: LLM cost, latency, flagged
responses, guardrail rejections. No framework imports.

These back the admin dashboard (files/plan.md Phase 9's admin-analytics
routes) and files/coding-standards.md section 12's analytics event
logging — every LLM call, retrieval, and guardrail action becomes one of
these.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class LLMCostLog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employer_id: UUID
    model: str
    model_tier: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    query_complexity_score: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RequestLatencyLog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employer_id: UUID
    total_ms: int
    retrieval_ms: int | None = None
    llm_ms: int | None = None
    overhead_ms: int | None = None
    model_tier: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FlaggedResponseStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    ESCALATED = "escalated"


class FlaggedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employer_id: UUID
    conversation_id: UUID
    message_id: UUID
    query_text: str
    top_similarity_score: float | None = None
    flag_reason: str
    status: FlaggedResponseStatus = FlaggedResponseStatus.PENDING_REVIEW
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GuardrailRejection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employer_id: UUID
    query_text: str
    rejection_reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
