from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import (
    get_conversation_repository,
    get_feedback_repository,
    get_message_repository,
)
from api.middleware.auth_middleware import get_current_user
from api.routes import feedback_routes
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.employee import UserRole
from core.domain.feedback import Feedback, FeedbackRating
from core.ports.repository_ports import (
    ConversationRepository,
    FeedbackRepository,
    MessageRepository,
)
from core.services.auth_service import TokenPayload


class _FakeMessageRepository(MessageRepository):
    def __init__(self, messages: list[Message] | None = None) -> None:
        self._by_id = {m.id: m for m in (messages or [])}

    async def get(self, entity_id: UUID) -> Message | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Message) -> Message:
        raise NotImplementedError

    async def update(self, entity: Message) -> Message:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_conversation(
        self, conversation_id: UUID, *, limit: int = 20
    ) -> list[Message]:
        raise NotImplementedError


class _FakeConversationRepository(ConversationRepository):
    def __init__(self, conversations: list[Conversation] | None = None) -> None:
        self._by_id = {c.id: c for c in (conversations or [])}

    async def get(self, entity_id: UUID) -> Conversation | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Conversation) -> Conversation:
        raise NotImplementedError

    async def update(self, entity: Conversation) -> Conversation:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employee(self, employee_id: UUID) -> list[Conversation]:
        raise NotImplementedError


class _FakeFeedbackRepository(FeedbackRepository):
    def __init__(self, feedback: list[Feedback] | None = None) -> None:
        self._by_id = {f.id: f for f in (feedback or [])}

    async def get(self, entity_id: UUID) -> Feedback | None:
        return self._by_id.get(entity_id)

    async def create(self, entity: Feedback) -> Feedback:
        self._by_id[entity.id] = entity
        return entity

    async def update(self, entity: Feedback) -> Feedback:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employer(self, employer_id: UUID) -> list[Feedback]:
        return [f for f in self._by_id.values() if f.employer_id == employer_id]


def _test_app(
    *,
    message_repository: MessageRepository | None = None,
    conversation_repository: ConversationRepository | None = None,
    feedback_repository: FeedbackRepository | None = None,
    current_user: TokenPayload | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(feedback_routes.router)
    app.dependency_overrides[get_message_repository] = lambda: (
        message_repository or _FakeMessageRepository()
    )
    app.dependency_overrides[get_conversation_repository] = lambda: (
        conversation_repository or _FakeConversationRepository()
    )
    app.dependency_overrides[get_feedback_repository] = lambda: (
        feedback_repository or _FakeFeedbackRepository()
    )
    app.dependency_overrides[get_current_user] = lambda: current_user or TokenPayload(
        user_id=uuid4(), employer_id=uuid4(), role=UserRole.EMPLOYEE, token_type="access"
    )
    return app


def _message(**overrides: Any) -> Message:
    defaults: dict[str, Any] = {
        "conversation_id": uuid4(),
        "employer_id": uuid4(),
        "role": MessageRole.ASSISTANT,
        "content": "You have full dental coverage.",
    }
    defaults.update(overrides)
    return Message(**defaults)


# --- submit -------------------------------------------------------------


def test_submit_feedback_creates_a_feedback_row() -> None:
    employee_id = uuid4()
    employer_id = uuid4()
    conversation = Conversation(employee_id=employee_id, employer_id=employer_id)
    message = _message(conversation_id=conversation.id, employer_id=employer_id)
    client = TestClient(
        _test_app(
            message_repository=_FakeMessageRepository([message]),
            conversation_repository=_FakeConversationRepository([conversation]),
            current_user=TokenPayload(
                user_id=employee_id,
                employer_id=employer_id,
                role=UserRole.EMPLOYEE,
                token_type="access",
            ),
        )
    )

    response = client.post(
        "/api/feedback",
        json={"message_id": str(message.id), "rating": "thumbs_up", "comment": "Very helpful"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["message_id"] == str(message.id)
    assert body["conversation_id"] == str(conversation.id)
    assert body["rating"] == "thumbs_up"
    assert body["comment"] == "Very helpful"


def test_submit_feedback_404s_for_an_unknown_message() -> None:
    client = TestClient(_test_app())

    response = client.post(
        "/api/feedback", json={"message_id": str(uuid4()), "rating": "thumbs_up"}
    )

    assert response.status_code == 404


def test_submit_feedback_404s_for_a_message_in_someone_elses_conversation() -> None:
    conversation = Conversation(employee_id=uuid4(), employer_id=uuid4())
    message = _message(conversation_id=conversation.id)
    client = TestClient(
        _test_app(
            message_repository=_FakeMessageRepository([message]),
            conversation_repository=_FakeConversationRepository([conversation]),
        )
    )

    response = client.post(
        "/api/feedback", json={"message_id": str(message.id), "rating": "thumbs_down"}
    )

    assert response.status_code == 404


# --- analytics ------------------------------------------------------------


def test_get_feedback_analytics_aggregates_correctly() -> None:
    employer_id = uuid4()
    feedback = [
        Feedback(
            message_id=uuid4(),
            conversation_id=uuid4(),
            employer_id=employer_id,
            rating=FeedbackRating.THUMBS_UP,
        ),
        Feedback(
            message_id=uuid4(),
            conversation_id=uuid4(),
            employer_id=employer_id,
            rating=FeedbackRating.THUMBS_UP,
        ),
        Feedback(
            message_id=uuid4(),
            conversation_id=uuid4(),
            employer_id=employer_id,
            rating=FeedbackRating.THUMBS_DOWN,
        ),
    ]
    client = TestClient(
        _test_app(
            feedback_repository=_FakeFeedbackRepository(feedback),
            current_user=TokenPayload(
                user_id=uuid4(), employer_id=None, role=UserRole.ADMIN, token_type="access"
            ),
        )
    )

    response = client.get(f"/api/feedback/analytics?employer_id={employer_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["thumbs_up"] == 2
    assert body["thumbs_down"] == 1
    assert body["thumbs_up_rate"] == 2 / 3


def test_get_feedback_analytics_handles_zero_feedback() -> None:
    client = TestClient(
        _test_app(
            current_user=TokenPayload(
                user_id=uuid4(), employer_id=None, role=UserRole.ADMIN, token_type="access"
            ),
        )
    )

    response = client.get(f"/api/feedback/analytics?employer_id={uuid4()}")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["thumbs_up_rate"] == 0.0


def test_get_feedback_analytics_403s_for_a_non_admin() -> None:
    client = TestClient(_test_app())

    response = client.get(f"/api/feedback/analytics?employer_id={uuid4()}")

    assert response.status_code == 403
