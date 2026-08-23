"""Pure domain model for the login principal. No framework imports.

Every user — admin, employer contact, or individual employee — is an
Employee, distinguished by `role`. `employer_id` is only None for `ADMIN`
(a superuser scoped to no single employer).
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    ADMIN = "admin"
    EMPLOYER = "employer"
    EMPLOYEE = "employee"


class Employee(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employer_id: UUID | None = None
    email: str
    hashed_password: str
    full_name: str
    role: UserRole
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
