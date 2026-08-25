"""Feedback routes (files/plan.md Step 9.5): submit thumbs up/down on a
message, and aggregated feedback stats for an employer (admin only).

Response shape matches the established convention from Step 9.1 (see
`auth_routes.py`'s module docstring) — this file returns its Pydantic
model(s) directly, not wrapped in `files/coding-standards.md` section
7's `APIResponse[T]` envelope.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.dependencies import (
    get_conversation_repository,
    get_feedback_repository,
    get_message_repository,
)
from api.middleware.auth_middleware import get_current_user, require_role
from core.domain.employee import UserRole
from core.domain.feedback import Feedback, FeedbackRating
from core.ports.repository_ports import (
    ConversationRepository,
    FeedbackRepository,
    MessageRepository,
)
from core.services.auth_service import TokenPayload

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackCreateRequest(BaseModel):
    message_id: UUID
    rating: FeedbackRating
    comment: str | None = None


class FeedbackResponse(BaseModel):
    id: UUID
    message_id: UUID
    conversation_id: UUID
    rating: FeedbackRating
    comment: str | None


class FeedbackAnalyticsResponse(BaseModel):
    employer_id: UUID
    total: int
    thumbs_up: int
    thumbs_down: int
    thumbs_up_rate: float


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackCreateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    message_repository: MessageRepository = Depends(get_message_repository),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
    feedback_repository: FeedbackRepository = Depends(get_feedback_repository),
) -> FeedbackResponse:
    """Submit thumbs up/down (+ optional text) for a message.

    Raises:
        HTTPException: 404 if the message doesn't exist or doesn't
            belong to a conversation owned by the current user — same
            not-found-vs-forbidden reasoning as `chat_routes.py`'s
            conversation ownership checks.
    """
    message = await message_repository.get(body.message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
    conversation = await conversation_repository.get(message.conversation_id)
    if conversation is None or conversation.employee_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

    created = await feedback_repository.create(
        Feedback(
            message_id=message.id,
            conversation_id=conversation.id,
            employer_id=conversation.employer_id,
            rating=body.rating,
            comment=body.comment,
        )
    )
    return FeedbackResponse(
        id=created.id,
        message_id=created.message_id,
        conversation_id=created.conversation_id,
        rating=created.rating,
        comment=created.comment,
    )


@router.get("/analytics", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def get_feedback_analytics(
    employer_id: UUID,
    feedback_repository: FeedbackRepository = Depends(get_feedback_repository),
) -> FeedbackAnalyticsResponse:
    """Aggregated feedback stats for one employer (admin only).

    `employer_id` is a required query param, not derived from the
    caller — an `ADMIN` has none of its own (`core/domain/employee.py`)
    and `FeedbackRepository` (Step 3.5) only offers `list_by_employer`,
    not a cross-tenant aggregate.
    """
    feedback = await feedback_repository.list_by_employer(employer_id)
    thumbs_up = sum(1 for f in feedback if f.rating == FeedbackRating.THUMBS_UP)
    thumbs_down = sum(1 for f in feedback if f.rating == FeedbackRating.THUMBS_DOWN)
    total = len(feedback)
    return FeedbackAnalyticsResponse(
        employer_id=employer_id,
        total=total,
        thumbs_up=thumbs_up,
        thumbs_down=thumbs_down,
        thumbs_up_rate=(thumbs_up / total) if total else 0.0,
    )
