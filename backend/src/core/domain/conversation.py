"""Pure domain models for conversations and messages. No framework imports."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employee_id: UUID
    employer_id: UUID
    title: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    employer_id: UUID
    role: MessageRole
    content: str
    model_used: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
