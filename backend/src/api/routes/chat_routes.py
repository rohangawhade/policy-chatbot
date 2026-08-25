"""Chat routes (files/plan.md Step 9.2): conversation CRUD plus the real
chat SSE endpoint wrapping `RAGService.query()`'s `GenerationStream`
(Step 6.5/6.6) — the first real HTTP caller of the whole RAG pipeline
end-to-end (`files/plan.md`'s Query Flow: guardrails -> cache -> router
-> embed -> Pinecone -> enrollment -> prompt -> generate -> cache/persist
-> analytics).

Response shape matches the established convention from Step 9.1 (see
`auth_routes.py`'s module docstring for the full reasoning): a route
file returns its Pydantic model(s) directly, not wrapped in
`files/coding-standards.md` section 7's `APIResponse[T]` envelope.
"""

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from api.dependencies import (
    get_conversation_repository,
    get_guardrails_service,
    get_message_repository,
    get_rag_service,
)
from api.middleware.auth_middleware import get_current_user
from api.middleware.tenant_context import get_current_employer_id
from core.domain.conversation import Conversation, Message, MessageRole
from core.ports.repository_ports import ConversationRepository, MessageRepository
from core.services.auth_service import TokenPayload
from core.services.guardrails_service import GuardrailsService
from core.services.rag_service import GenerationMetrics, RAGService

router = APIRouter(prefix="/api/chat", tags=["chat"])

_DEFAULT_HISTORY_LIMIT = 50


class ConversationResponse(BaseModel):
    id: UUID
    employee_id: UUID
    employer_id: UUID
    title: str | None


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    model_used: str | None


class SendMessageRequest(BaseModel):
    content: str


def _to_conversation_response(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        employee_id=conversation.employee_id,
        employer_id=conversation.employer_id,
        title=conversation.title,
    )


def _to_message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        model_used=message.model_used,
    )


async def _get_owned_conversation(
    conversation_repository: ConversationRepository, conversation_id: UUID, employee_id: UUID
) -> Conversation:
    conversation = await conversation_repository.get(conversation_id)
    if conversation is None or conversation.employee_id != employee_id:
        # Same 404 for "doesn't exist" and "belongs to someone else" —
        # a 403 would leak that the id exists at all, to a caller who has
        # no business knowing that (matches document_routes.py's Step
        # 8.3 reasoning, applied here to per-employee ownership instead
        # of per-employer).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    current_user: TokenPayload = Depends(get_current_user),
    employer_id: UUID = Depends(get_current_employer_id),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
) -> ConversationResponse:
    conversation = await conversation_repository.create(
        Conversation(employee_id=current_user.user_id, employer_id=employer_id)
    )
    return _to_conversation_response(conversation)


@router.get("/conversations")
async def list_conversations(
    current_user: TokenPayload = Depends(get_current_user),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
) -> list[ConversationResponse]:
    conversations = await conversation_repository.list_by_employee(current_user.user_id)
    return [_to_conversation_response(conversation) for conversation in conversations]


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = _DEFAULT_HISTORY_LIMIT,
    current_user: TokenPayload = Depends(get_current_user),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
    message_repository: MessageRepository = Depends(get_message_repository),
) -> list[MessageResponse]:
    await _get_owned_conversation(conversation_repository, conversation_id, current_user.user_id)
    messages = await message_repository.list_by_conversation(conversation_id, limit=limit)
    return [_to_message_response(message) for message in messages]


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    current_user: TokenPayload = Depends(get_current_user),
    employer_id: UUID = Depends(get_current_employer_id),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
    guardrails_service: GuardrailsService = Depends(get_guardrails_service),
    rag_service: RAGService = Depends(get_rag_service),
) -> StreamingResponse:
    """Send a message into an existing conversation; the response is an
    SSE stream of `data: {"token": "..."}` events, ending with one
    `data: {"done": true, ...}` event carrying the persisted
    `message_id` (and generation metadata) once the response is
    complete — or `"rejected": true` if `GuardrailsService` (Step 6.1)
    blocked the query as off-topic before any retrieval/generation ever
    ran, per `files/plan.md`'s Query Flow diagram.
    """
    await _get_owned_conversation(conversation_repository, conversation_id, current_user.user_id)
    return StreamingResponse(
        _stream_chat_response(
            guardrails_service,
            rag_service,
            conversation_id,
            body.content,
            current_user.user_id,
            employer_id,
        ),
        media_type="text/event-stream",
    )


async def _stream_chat_response(
    guardrails_service: GuardrailsService,
    rag_service: RAGService,
    conversation_id: UUID,
    query_text: str,
    employee_id: UUID,
    employer_id: UUID,
) -> AsyncIterator[str]:
    guardrail = await guardrails_service.check(query_text, employer_id)
    if not guardrail.allowed:
        yield _format_token_event(guardrail.rejection_message or "")
        yield _format_done_event(conversation_id, rejected=True)
        return

    stream = await rag_service.query(query_text, employee_id, employer_id, conversation_id)
    async for token in stream:
        yield _format_token_event(token)
    yield _format_done_event(conversation_id, rejected=False, metrics=stream.metrics)


def _format_token_event(token: str) -> str:
    return f"data: {json.dumps({'token': token})}\n\n"


def _format_done_event(
    conversation_id: UUID, *, rejected: bool, metrics: GenerationMetrics | None = None
) -> str:
    payload: dict[str, object] = {"done": True, "conversation_id": str(conversation_id)}
    if rejected:
        payload["rejected"] = True
    elif metrics is not None:
        payload.update(
            {
                "message_id": str(metrics.message_id),
                "model": metrics.model,
                "model_tier": metrics.model_tier,
                "is_low_confidence": metrics.is_low_confidence,
                "from_cache": metrics.from_cache,
            }
        )
    return f"data: {json.dumps(payload)}\n\n"
