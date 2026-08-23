"""Pure domain models for policies and enrollments. No framework imports."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class PolicyType(str, Enum):
    HEALTH = "health"
    DENTAL = "dental"
    VISION = "vision"
    LIFE = "life"
    DISABILITY = "disability"


class Policy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employer_id: UUID
    policy_type: PolicyType
    name: str
    description: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Enrollment(BaseModel):
    """An employee's enrollment in a policy."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employee_id: UUID
    policy_id: UUID
    enrolled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True
