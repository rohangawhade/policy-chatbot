import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import (
    get_chat_rate_limiter,
    get_conversation_repository,
    get_guardrails_service,
    get_message_repository,
    get_rag_service,
)
from api.error_handlers import register_exception_handlers
from api.middleware.auth_middleware import get_current_user
from api.middleware.tenant_context import get_current_employer_id
from api.routes import chat_routes
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.employee import UserRole
from core.domain.errors import RateLimitError
from core.ports.repository_ports import ConversationRepository, MessageRepository
from core.services.auth_service import TokenPayload
from core.services.guardrails_service import GuardrailResult
from core.services.rag_service import GenerationMetrics


class _FakeConversationRepository(ConversationRepository):
    def __init__(self, conversations: list[Conversation] | None = None) -> None:
        self._by_id = {c.id: c for c in (conversations or [])}

    async def get(self, entity_id: UUID) -> Conversation | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Conversation) -> Conversation:
        self._by_id[entity.id] = entity
        return entity

    async def update(self, entity: Conversation) -> Conversation:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employee(self, employee_id: UUID) -> list[Conversation]:
        return [c for c in self._by_id.values() if c.employee_id == employee_id]

    async def list_active_since(
        self, since: datetime, *, employer_id: UUID | None = None
    ) -> list[Conversation]:
        raise NotImplementedError


class _FakeMessageRepository(MessageRepository):
    def __init__(self, messages: list[Message] | None = None) -> None:
        self._messages = list(messages or [])

    async def get(self, entity_id: UUID) -> Message | None:
        return next((m for m in self._messages if m.id == entity_id), None)

    async def create(self, entity: Message) -> Message:
        self._messages.append(entity)
        return entity

    async def update(self, entity: Message) -> Message:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_conversation(
        self, conversation_id: UUID, *, limit: int = 20
    ) -> list[Message]:
        matches = [m for m in self._messages if m.conversation_id == conversation_id]
        return matches[-limit:]

    async def list_for_analytics(
        self,
        *,
        employer_id: UUID | None = None,
        role: MessageRole | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Message]:
        raise NotImplementedError


class _FakeRateLimiter:
    def __init__(self, *, exceeded: bool = False) -> None:
        self._exceeded = exceeded
        self.checked_keys: list[str] = []

    async def check(self, key: str) -> None:
        self.checked_keys.append(key)
        if self._exceeded:
            raise RateLimitError(
                "Rate limit exceeded: max 20 requests per 60s. Please slow down and try again "
                "shortly.",
                code="rate_limit_exceeded",
            )


class _FakeGuardrailsService:
    def __init__(self, *, allowed: bool, rejection_message: str | None = None) -> None:
        self._result = GuardrailResult(allowed=allowed, rejection_message=rejection_message)
        self.calls: list[tuple[str, UUID]] = []

    async def check(self, query_text: str, employer_id: UUID) -> GuardrailResult:
        self.calls.append((query_text, employer_id))
        return self._result


class _FakeGenerationStream:
    def __init__(self, tokens: list[str], metrics: GenerationMetrics) -> None:
        self._tokens = tokens
        self._final_metrics = metrics
        self.metrics: GenerationMetrics | None = None

    async def __aiter__(self) -> Any:
        for token in self._tokens:
            yield token
        self.metrics = self._final_metrics


class _FakeRAGService:
    def __init__(self, stream: _FakeGenerationStream) -> None:
        self._stream = stream
        self.last_call: dict[str, object] | None = None

    async def query(
        self,
        query_text: str,
        employee_id: UUID,
        employer_id: UUID,
        conversation_id: UUID | None = None,
    ) -> _FakeGenerationStream:
        self.last_call = {
            "query_text": query_text,
            "employee_id": employee_id,
            "employer_id": employer_id,
            "conversation_id": conversation_id,
        }
        return self._stream


def _conversation(**overrides: Any) -> Conversation:
    defaults: dict[str, Any] = {"employee_id": uuid4(), "employer_id": uuid4()}
    defaults.update(overrides)
    return Conversation(**defaults)


def _message(**overrides: Any) -> Message:
    defaults: dict[str, Any] = {
        "conversation_id": uuid4(),
        "employer_id": uuid4(),
        "role": MessageRole.USER,
        "content": "hello",
    }
    defaults.update(overrides)
    return Message(**defaults)


def _test_app(
    *,
    employee_id: UUID,
    employer_id: UUID,
    conversation_repository: ConversationRepository,
    message_repository: MessageRepository | None = None,
    guardrails_service: object | None = None,
    rag_service: object | None = None,
    rate_limiter: object | None = None,
) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(chat_routes.router)
    app.dependency_overrides[get_conversation_repository] = lambda: conversation_repository
    app.dependency_overrides[get_message_repository] = lambda: (
        message_repository or _FakeMessageRepository()
    )
    app.dependency_overrides[get_guardrails_service] = lambda: (
        guardrails_service or _FakeGuardrailsService(allowed=True)
    )
    app.dependency_overrides[get_rag_service] = lambda: rag_service
    app.dependency_overrides[get_chat_rate_limiter] = lambda: (rate_limiter or _FakeRateLimiter())
    app.dependency_overrides[get_current_user] = lambda: TokenPayload(
        user_id=employee_id, employer_id=employer_id, role=UserRole.EMPLOYEE, token_type="access"
    )
    app.dependency_overrides[get_current_employer_id] = lambda: employer_id
    return app


# --- POST /conversations ---------------------------------------------------


def test_create_conversation_returns_a_new_conversation_for_the_current_user() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository(),
        )
    )

    response = client.post("/api/chat/conversations")

    assert response.status_code == 201
    body = response.json()
    assert body["employee_id"] == str(employee_id)
    assert body["employer_id"] == str(employer_id)
    assert body["title"] is None


# --- GET /conversations ------------------------------------------------


def test_list_conversations_returns_only_the_current_employees_conversations() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    mine = _conversation(employee_id=employee_id, employer_id=employer_id)
    someone_elses = _conversation(employee_id=uuid4(), employer_id=employer_id)
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository([mine, someone_elses]),
        )
    )

    response = client.get("/api/chat/conversations")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(mine.id)


# --- GET /conversations/{id}/messages ------------------------------------


def test_get_conversation_messages_returns_history() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    conversation = _conversation(employee_id=employee_id, employer_id=employer_id)
    user_message = _message(conversation_id=conversation.id, employer_id=employer_id, content="hi")
    assistant_message = _message(
        conversation_id=conversation.id,
        employer_id=employer_id,
        role=MessageRole.ASSISTANT,
        content="hello there",
        model_used="claude-haiku",
    )
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository([conversation]),
            message_repository=_FakeMessageRepository([user_message, assistant_message]),
        )
    )

    response = client.get(f"/api/chat/conversations/{conversation.id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert [m["content"] for m in body] == ["hi", "hello there"]
    assert body[1]["model_used"] == "claude-haiku"


def test_get_conversation_messages_404s_for_an_unknown_conversation() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository(),
        )
    )

    response = client.get(f"/api/chat/conversations/{uuid4()}/messages")

    assert response.status_code == 404


def test_get_conversation_messages_404s_for_another_employees_conversation() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    conversation = _conversation(employee_id=uuid4(), employer_id=employer_id)
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository([conversation]),
        )
    )

    response = client.get(f"/api/chat/conversations/{conversation.id}/messages")

    assert response.status_code == 404


# --- POST /conversations/{id}/messages -----------------------------------


def test_send_message_404s_for_an_unknown_conversation() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository(),
        )
    )

    response = client.post(f"/api/chat/conversations/{uuid4()}/messages", json={"content": "hi"})

    assert response.status_code == 404


def test_send_message_streams_tokens_then_a_done_event_with_metrics() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    conversation = _conversation(employee_id=employee_id, employer_id=employer_id)
    metrics = GenerationMetrics(
        full_text="Hello there",
        model="claude-haiku-4-5-20251001",
        model_tier="cheap",
        complexity_score=0.1,
        top_similarity_score=0.9,
        is_low_confidence=False,
        from_cache=False,
        conversation_id=conversation.id,
        message_id=uuid4(),
        retrieved_contexts=["The deductible is $500."],
    )
    stream = _FakeGenerationStream(["Hello", " there"], metrics)
    rag_service = _FakeRAGService(stream)
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository([conversation]),
            rag_service=rag_service,
        )
    )

    with client.stream(
        "POST",
        f"/api/chat/conversations/{conversation.id}/messages",
        json={"content": "What is my deductible?"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [
            json.loads(line.removeprefix("data: "))
            for line in "".join(response.iter_text()).strip().split("\n\n")
            if line
        ]

    assert [e["token"] for e in events[:2]] == ["Hello", " there"]
    done = events[-1]
    assert done["done"] is True
    assert done["conversation_id"] == str(conversation.id)
    assert done["message_id"] == str(metrics.message_id)
    assert done["model"] == "claude-haiku-4-5-20251001"
    assert done["contexts"] == ["The deductible is $500."]
    assert "rejected" not in done
    assert rag_service.last_call == {
        "query_text": "What is my deductible?",
        "employee_id": employee_id,
        "employer_id": employer_id,
        "conversation_id": conversation.id,
    }


def test_send_message_streams_a_rejection_when_guardrails_blocks_it() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    conversation = _conversation(employee_id=employee_id, employer_id=employer_id)
    guardrails_service = _FakeGuardrailsService(
        allowed=False, rejection_message="I can only help with benefits questions."
    )
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository([conversation]),
            guardrails_service=guardrails_service,
            rag_service=_FakeRAGService(_FakeGenerationStream([], None)),  # type: ignore[arg-type]
        )
    )

    with client.stream(
        "POST",
        f"/api/chat/conversations/{conversation.id}/messages",
        json={"content": "What's the weather?"},
    ) as response:
        assert response.status_code == 200
        events = [
            json.loads(line.removeprefix("data: "))
            for line in "".join(response.iter_text()).strip().split("\n\n")
            if line
        ]

    assert events[0]["token"] == "I can only help with benefits questions."
    assert events[1] == {
        "done": True,
        "conversation_id": str(conversation.id),
        "rejected": True,
    }
    assert guardrails_service.calls == [("What's the weather?", employer_id)]


def test_send_message_429s_when_the_rate_limit_is_exceeded() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    conversation = _conversation(employee_id=employee_id, employer_id=employer_id)
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository([conversation]),
            rate_limiter=_FakeRateLimiter(exceeded=True),
        )
    )

    response = client.post(
        f"/api/chat/conversations/{conversation.id}/messages", json={"content": "hi"}
    )

    assert response.status_code == 429


def test_send_message_checks_the_rate_limiter_with_the_employees_id() -> None:
    employee_id, employer_id = uuid4(), uuid4()
    conversation = _conversation(employee_id=employee_id, employer_id=employer_id)
    metrics = GenerationMetrics(
        full_text="Hello",
        model="claude-haiku-4-5-20251001",
        model_tier="cheap",
        complexity_score=0.1,
        top_similarity_score=0.9,
        is_low_confidence=False,
        from_cache=False,
        conversation_id=conversation.id,
        message_id=uuid4(),
        retrieved_contexts=[],
    )
    rate_limiter = _FakeRateLimiter()
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository([conversation]),
            rag_service=_FakeRAGService(_FakeGenerationStream(["Hello"], metrics)),
            rate_limiter=rate_limiter,
        )
    )

    with client.stream(
        "POST",
        f"/api/chat/conversations/{conversation.id}/messages",
        json={"content": "hi"},
    ) as response:
        assert response.status_code == 200
        "".join(response.iter_text())  # drain the stream

    assert rate_limiter.checked_keys == [str(employee_id)]


def test_send_message_checks_the_rate_limit_before_the_conversation_lookup() -> None:
    """The rate-limit check must reject an abusive caller even for a
    conversation id that doesn't exist/isn't theirs -- otherwise spamming
    bogus ids would be a free way around it."""
    employee_id, employer_id = uuid4(), uuid4()
    client = TestClient(
        _test_app(
            employee_id=employee_id,
            employer_id=employer_id,
            conversation_repository=_FakeConversationRepository(),
            rate_limiter=_FakeRateLimiter(exceeded=True),
        )
    )

    response = client.post(f"/api/chat/conversations/{uuid4()}/messages", json={"content": "hi"})

    assert response.status_code == 429
