"""Pure domain model for user feedback (thumbs up/down). No framework imports."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class FeedbackRating(str, Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class Feedback(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    message_id: UUID
    conversation_id: UUID
    employer_id: UUID
    rating: FeedbackRating
    comment: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
