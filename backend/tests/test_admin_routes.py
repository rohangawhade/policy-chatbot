from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import (
    get_analytics_repository,
    get_conversation_repository,
    get_document_repository,
    get_feedback_repository,
    get_message_repository,
)
from api.middleware.auth_middleware import get_current_user
from api.routes import admin_routes
from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.document import Document, DocumentStatus
from core.domain.employee import UserRole
from core.domain.feedback import Feedback, FeedbackRating
from core.domain.policy import PolicyType
from core.ports.repository_ports import (
    AnalyticsRepository,
    ConversationRepository,
    DocumentRepository,
    FeedbackRepository,
    MessageRepository,
)
from core.services.auth_service import TokenPayload


class _FakeAnalyticsRepository(AnalyticsRepository):
    def __init__(
        self,
        *,
        llm_costs: list[LLMCostLog] | None = None,
        latencies: list[RequestLatencyLog] | None = None,
        flagged: list[FlaggedResponse] | None = None,
        rejections: list[GuardrailRejection] | None = None,
    ) -> None:
        self._llm_costs = list(llm_costs or [])
        self._latencies = list(latencies or [])
        self._flagged = {f.id: f for f in (flagged or [])}
        self._rejections = list(rejections or [])

    async def record_llm_cost(self, log: LLMCostLog) -> None:
        raise NotImplementedError

    async def record_latency(self, log: RequestLatencyLog) -> None:
        raise NotImplementedError

    async def record_flagged_response(self, flagged: FlaggedResponse) -> None:
        raise NotImplementedError

    async def record_guardrail_rejection(self, rejection: GuardrailRejection) -> None:
        raise NotImplementedError

    async def list_llm_costs(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[LLMCostLog]:
        result = self._llm_costs
        if employer_id is not None:
            result = [log for log in result if log.employer_id == employer_id]
        if start is not None:
            result = [log for log in result if log.created_at >= start]
        if end is not None:
            result = [log for log in result if log.created_at < end]
        return result

    async def list_latencies(
        self,
        *,
        employer_id: UUID | None = None,
        model_tier: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[RequestLatencyLog]:
        result = self._latencies
        if employer_id is not None:
            result = [log for log in result if log.employer_id == employer_id]
        if model_tier is not None:
            result = [log for log in result if log.model_tier == model_tier]
        return result

    async def list_flagged_responses(
        self, *, employer_id: UUID | None = None, status: FlaggedResponseStatus | None = None
    ) -> list[FlaggedResponse]:
        result = list(self._flagged.values())
        if employer_id is not None:
            result = [f for f in result if f.employer_id == employer_id]
        if status is not None:
            result = [f for f in result if f.status == status]
        return result

    async def get_flagged_response(self, flagged_response_id: UUID) -> FlaggedResponse | None:
        return self._flagged.get(flagged_response_id)

    async def update_flagged_response_status(
        self, flagged_response_id: UUID, status: FlaggedResponseStatus
    ) -> FlaggedResponse:
        existing = self._flagged.get(flagged_response_id)
        if existing is None:
            raise ValueError(f"FlaggedResponse {flagged_response_id} does not exist.")
        updated = existing.model_copy(update={"status": status})
        self._flagged[flagged_response_id] = updated
        return updated

    async def list_guardrail_rejections(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[GuardrailRejection]:
        result = self._rejections
        if employer_id is not None:
            result = [r for r in result if r.employer_id == employer_id]
        return result


class _FakeConversationRepository(ConversationRepository):
    def __init__(self, conversations: list[Conversation] | None = None) -> None:
        self._conversations = list(conversations or [])

    async def get(self, entity_id: UUID) -> Conversation | None:
        raise NotImplementedError

    async def create(self, entity: Conversation) -> Conversation:
        raise NotImplementedError

    async def update(self, entity: Conversation) -> Conversation:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employee(self, employee_id: UUID) -> list[Conversation]:
        raise NotImplementedError

    async def list_active_since(
        self, since: datetime, *, employer_id: UUID | None = None
    ) -> list[Conversation]:
        return [c for c in self._conversations if c.updated_at >= since]


class _FakeMessageRepository(MessageRepository):
    def __init__(self, messages: list[Message] | None = None) -> None:
        self._messages = list(messages or [])

    async def get(self, entity_id: UUID) -> Message | None:
        return next((m for m in self._messages if m.id == entity_id), None)

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

    async def list_for_analytics(
        self,
        *,
        employer_id: UUID | None = None,
        role: MessageRole | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Message]:
        result = self._messages
        if employer_id is not None:
            result = [m for m in result if m.employer_id == employer_id]
        if role is not None:
            result = [m for m in result if m.role == role]
        if start is not None:
            result = [m for m in result if m.created_at >= start]
        if end is not None:
            result = [m for m in result if m.created_at < end]
        return result


class _FakeDocumentRepository(DocumentRepository):
    def __init__(self, documents: list[Document] | None = None) -> None:
        self._documents = list(documents or [])

    async def get(self, entity_id: UUID) -> Document | None:
        raise NotImplementedError

    async def create(self, entity: Document) -> Document:
        raise NotImplementedError

    async def update(self, entity: Document) -> Document:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employer(self, employer_id: UUID) -> list[Document]:
        raise NotImplementedError

    async def get_latest_version(self, employer_id: UUID, title: str) -> Document | None:
        raise NotImplementedError

    async def list_all(self, *, employer_id: UUID | None = None) -> list[Document]:
        if employer_id is None:
            return self._documents
        return [d for d in self._documents if d.employer_id == employer_id]

    async def mark_queried(self, document_ids: list[UUID]) -> None:
        raise NotImplementedError


class _FakeFeedbackRepository(FeedbackRepository):
    def __init__(self, feedback: list[Feedback] | None = None) -> None:
        self._feedback = list(feedback or [])

    async def get(self, entity_id: UUID) -> Feedback | None:
        raise NotImplementedError

    async def create(self, entity: Feedback) -> Feedback:
        raise NotImplementedError

    async def update(self, entity: Feedback) -> Feedback:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employer(self, employer_id: UUID) -> list[Feedback]:
        raise NotImplementedError

    async def list_all(self, *, employer_id: UUID | None = None) -> list[Feedback]:
        if employer_id is None:
            return self._feedback
        return [f for f in self._feedback if f.employer_id == employer_id]


def _test_app(
    *,
    analytics_repository: AnalyticsRepository | None = None,
    conversation_repository: ConversationRepository | None = None,
    message_repository: MessageRepository | None = None,
    document_repository: DocumentRepository | None = None,
    feedback_repository: FeedbackRepository | None = None,
    role: UserRole = UserRole.ADMIN,
) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_routes.router)
    app.dependency_overrides[get_analytics_repository] = lambda: (
        analytics_repository or _FakeAnalyticsRepository()
    )
    app.dependency_overrides[get_conversation_repository] = lambda: (
        conversation_repository or _FakeConversationRepository()
    )
    app.dependency_overrides[get_message_repository] = lambda: (
        message_repository or _FakeMessageRepository()
    )
    app.dependency_overrides[get_document_repository] = lambda: (
        document_repository or _FakeDocumentRepository()
    )
    app.dependency_overrides[get_feedback_repository] = lambda: (
        feedback_repository or _FakeFeedbackRepository()
    )
    app.dependency_overrides[get_current_user] = lambda: TokenPayload(
        user_id=uuid4(), employer_id=None, role=role, token_type="access"
    )
    return app


def _cost_log(**overrides: Any) -> LLMCostLog:
    defaults: dict[str, Any] = {
        "employer_id": uuid4(),
        "model": "claude-haiku-4-5-20251001",
        "model_tier": "cheap",
        "input_tokens": 100,
        "output_tokens": 40,
        "estimated_cost_usd": 1.0,
    }
    defaults.update(overrides)
    return LLMCostLog(**defaults)


def test_admin_routes_403_for_a_non_admin() -> None:
    client = TestClient(_test_app(role=UserRole.EMPLOYER))

    response = client.get("/api/admin/overview")

    assert response.status_code == 403


def test_get_overview_counts_queries_users_documents_and_cost() -> None:
    employer_id = uuid4()
    now = datetime.now(UTC)
    messages = [
        Message(
            conversation_id=uuid4(),
            employer_id=employer_id,
            role=MessageRole.USER,
            content="q",
            created_at=now,
        )
    ]
    conversation = Conversation(employee_id=uuid4(), employer_id=employer_id, updated_at=now)
    documents = [
        Document(employer_id=employer_id, title="SPD.pdf", source_type="pdf", source_path="x")
    ]
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
            rating=FeedbackRating.THUMBS_DOWN,
        ),
    ]
    costs = [_cost_log(employer_id=employer_id, estimated_cost_usd=2.5, created_at=now)]
    client = TestClient(
        _test_app(
            message_repository=_FakeMessageRepository(messages),
            conversation_repository=_FakeConversationRepository([conversation]),
            document_repository=_FakeDocumentRepository(documents),
            feedback_repository=_FakeFeedbackRepository(feedback),
            analytics_repository=_FakeAnalyticsRepository(llm_costs=costs),
        )
    )

    response = client.get("/api/admin/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["total_queries_today"] == 1
    assert body["total_queries_week"] == 1
    assert body["total_queries_month"] == 1
    assert body["active_users_week"] == 1
    assert body["document_count"] == 1
    assert body["avg_satisfaction"] == 0.5
    assert body["cost_this_month_usd"] == 2.5


def test_get_overview_with_no_data_returns_zeroes() -> None:
    client = TestClient(_test_app())

    response = client.get("/api/admin/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["total_queries_today"] == 0
    assert body["avg_satisfaction"] == 0.0
    assert body["cost_this_month_usd"] == 0.0


def test_get_cost_dashboard_aggregates_by_model_employer_and_day() -> None:
    employer_id = uuid4()
    now = datetime.now(UTC)
    costs = [
        _cost_log(
            employer_id=employer_id,
            model="claude-haiku-4-5-20251001",
            estimated_cost_usd=1.0,
            created_at=now,
        ),
        _cost_log(
            employer_id=employer_id,
            model="claude-sonnet-4-6",
            estimated_cost_usd=3.0,
            created_at=now,
        ),
    ]
    client = TestClient(_test_app(analytics_repository=_FakeAnalyticsRepository(llm_costs=costs)))

    response = client.get("/api/admin/cost-dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["total_cost_usd"] == 4.0
    assert {row["model"] for row in body["by_model"]} == {
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6",
    }
    assert len(body["by_employer"]) == 1
    assert body["by_employer"][0]["total_cost_usd"] == 4.0
    assert len(body["by_day"]) == 1


def test_get_cost_dashboard_alerts_flags_days_over_threshold() -> None:
    employer_id = uuid4()
    now = datetime.now(UTC)
    costs = [_cost_log(employer_id=employer_id, estimated_cost_usd=100.0, created_at=now)]
    client = TestClient(_test_app(analytics_repository=_FakeAnalyticsRepository(llm_costs=costs)))

    response = client.get("/api/admin/cost-dashboard/alerts", params={"threshold_usd": 50})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["employer_id"] == str(employer_id)
    assert body[0]["total_cost_usd"] == 100.0
    assert body[0]["threshold_usd"] == 50.0


def test_get_cost_dashboard_alerts_uses_the_configured_default_threshold() -> None:
    costs = [_cost_log(estimated_cost_usd=1.0)]
    client = TestClient(_test_app(analytics_repository=_FakeAnalyticsRepository(llm_costs=costs)))

    response = client.get("/api/admin/cost-dashboard/alerts")

    assert response.status_code == 200
    assert response.json() == []


def test_get_latency_computes_percentiles_and_breaks_down_by_tier() -> None:
    latencies = [
        RequestLatencyLog(employer_id=uuid4(), total_ms=ms, model_tier="cheap")
        for ms in (100, 200, 300, 400, 500)
    ] + [RequestLatencyLog(employer_id=uuid4(), total_ms=900, model_tier="powerful")]
    client = TestClient(
        _test_app(analytics_repository=_FakeAnalyticsRepository(latencies=latencies))
    )

    response = client.get("/api/admin/latency")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["count"] == 6
    assert body["overall"]["p50_ms"] > 0
    tiers = {row["label"] for row in body["by_model_tier"]}
    assert tiers == {"cheap", "powerful"}


def test_get_latency_splits_retrieval_and_generation() -> None:
    latencies = [
        RequestLatencyLog(
            employer_id=uuid4(), total_ms=300, retrieval_ms=100, llm_ms=180, model_tier="cheap"
        ),
        RequestLatencyLog(
            employer_id=uuid4(), total_ms=500, retrieval_ms=120, llm_ms=350, model_tier="cheap"
        ),
        # A log with no retrieval_ms/llm_ms (Step 8 logging can omit either) --
        # must not count toward those percentiles, only `overall`.
        RequestLatencyLog(employer_id=uuid4(), total_ms=200, model_tier="cheap"),
    ]
    client = TestClient(
        _test_app(analytics_repository=_FakeAnalyticsRepository(latencies=latencies))
    )

    response = client.get("/api/admin/latency")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["count"] == 3
    assert body["retrieval"]["count"] == 2
    assert body["retrieval"]["label"] == "retrieval"
    assert body["generation"]["count"] == 2
    assert body["generation"]["label"] == "generation"


def test_get_latency_with_no_data_returns_zeroed_stats() -> None:
    client = TestClient(_test_app())

    response = client.get("/api/admin/latency")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == {
        "label": "overall",
        "count": 0,
        "p50_ms": 0.0,
        "p95_ms": 0.0,
        "p99_ms": 0.0,
    }
    assert body["retrieval"]["count"] == 0
    assert body["generation"]["count"] == 0
    assert body["by_model_tier"] == []


def test_list_flagged_responses_returns_every_row() -> None:
    flagged = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    client = TestClient(_test_app(analytics_repository=_FakeAnalyticsRepository(flagged=[flagged])))

    response = client.get("/api/admin/flagged-responses")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(flagged.id)
    assert body[0]["status"] == "pending_review"


def test_list_flagged_responses_enriches_from_the_flagged_message() -> None:
    message = Message(
        conversation_id=uuid4(),
        employer_id=uuid4(),
        role=MessageRole.ASSISTANT,
        content="Your HSA limit is $4,150 for 2026.",
        model_used="gpt-4o-mini",
        policy_type=PolicyType.HEALTH,
    )
    flagged = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=message.id,
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    client = TestClient(
        _test_app(
            analytics_repository=_FakeAnalyticsRepository(flagged=[flagged]),
            message_repository=_FakeMessageRepository([message]),
        )
    )

    response = client.get("/api/admin/flagged-responses")

    assert response.status_code == 200
    body = response.json()[0]
    assert body["response_text"] == "Your HSA limit is $4,150 for 2026."
    assert body["model_used"] == "gpt-4o-mini"
    assert body["policy_type"] == "health"


def test_list_flagged_responses_leaves_enrichment_null_when_message_is_gone() -> None:
    flagged = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    client = TestClient(
        _test_app(
            analytics_repository=_FakeAnalyticsRepository(flagged=[flagged]),
            message_repository=_FakeMessageRepository([]),
        )
    )

    response = client.get("/api/admin/flagged-responses")

    assert response.status_code == 200
    body = response.json()[0]
    assert body["response_text"] is None
    assert body["model_used"] is None
    assert body["policy_type"] is None


def test_update_flagged_response_marks_it_reviewed() -> None:
    flagged = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    client = TestClient(_test_app(analytics_repository=_FakeAnalyticsRepository(flagged=[flagged])))

    response = client.patch(
        f"/api/admin/flagged-responses/{flagged.id}", json={"status": "reviewed"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "reviewed"


def test_update_flagged_response_to_escalated() -> None:
    flagged = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    client = TestClient(_test_app(analytics_repository=_FakeAnalyticsRepository(flagged=[flagged])))

    response = client.patch(
        f"/api/admin/flagged-responses/{flagged.id}", json={"status": "escalated"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "escalated"


def test_update_flagged_response_rejects_pending_review_as_a_target_status() -> None:
    flagged = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    client = TestClient(_test_app(analytics_repository=_FakeAnalyticsRepository(flagged=[flagged])))

    response = client.patch(
        f"/api/admin/flagged-responses/{flagged.id}", json={"status": "pending_review"}
    )

    assert response.status_code == 422


def test_update_flagged_response_404s_for_an_unknown_id() -> None:
    client = TestClient(_test_app())

    response = client.patch(f"/api/admin/flagged-responses/{uuid4()}", json={"status": "reviewed"})

    assert response.status_code == 404


def test_list_guardrail_rejections_returns_every_row() -> None:
    rejection = GuardrailRejection(
        employer_id=uuid4(), query_text="weather?", rejection_reason="off_topic"
    )
    client = TestClient(
        _test_app(analytics_repository=_FakeAnalyticsRepository(rejections=[rejection]))
    )

    response = client.get("/api/admin/guardrail-rejections")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["rejection_reason"] == "off_topic"


def test_list_unanswered_queries_only_returns_low_confidence_flags() -> None:
    low_confidence = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="hsa limit?",
        flag_reason="low_retrieval_confidence",
    )
    other = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        query_text="unrelated",
        flag_reason="some_other_reason",
    )
    client = TestClient(
        _test_app(analytics_repository=_FakeAnalyticsRepository(flagged=[low_confidence, other]))
    )

    response = client.get("/api/admin/unanswered-queries")

    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body] == [str(low_confidence.id)]


def test_list_unanswered_queries_includes_policy_type_for_grouping() -> None:
    message = Message(
        conversation_id=uuid4(),
        employer_id=uuid4(),
        role=MessageRole.ASSISTANT,
        content="I don't have enough information to answer that.",
        policy_type=PolicyType.DENTAL,
    )
    flagged = FlaggedResponse(
        employer_id=uuid4(),
        conversation_id=uuid4(),
        message_id=message.id,
        query_text="orthodontia coverage?",
        flag_reason="low_retrieval_confidence",
    )
    client = TestClient(
        _test_app(
            analytics_repository=_FakeAnalyticsRepository(flagged=[flagged]),
            message_repository=_FakeMessageRepository([message]),
        )
    )

    response = client.get("/api/admin/unanswered-queries")

    assert response.status_code == 200
    assert response.json()[0]["policy_type"] == "dental"


def test_get_topic_heatmap_groups_by_date_and_policy_type() -> None:
    employer_id = uuid4()
    now = datetime.now(UTC)
    messages = [
        Message(
            conversation_id=uuid4(),
            employer_id=employer_id,
            role=MessageRole.USER,
            content="dental question",
            policy_type=PolicyType.DENTAL,
            created_at=now,
        ),
        Message(
            conversation_id=uuid4(),
            employer_id=employer_id,
            role=MessageRole.USER,
            content="dental question 2",
            policy_type=PolicyType.DENTAL,
            created_at=now,
        ),
        Message(
            conversation_id=uuid4(),
            employer_id=employer_id,
            role=MessageRole.USER,
            content="untyped question",
            created_at=now,
        ),
    ]
    client = TestClient(_test_app(message_repository=_FakeMessageRepository(messages)))

    response = client.get("/api/admin/topic-heatmap")

    assert response.status_code == 200
    cells = response.json()["cells"]
    dental_cell = next(c for c in cells if c["policy_type"] == "dental")
    assert dental_cell["query_count"] == 2
    untyped_cell = next(c for c in cells if c["policy_type"] is None)
    assert untyped_cell["query_count"] == 1


def test_get_document_health_flags_stale_and_zero_hit_documents() -> None:
    employer_id = uuid4()
    stale_document = Document(
        employer_id=employer_id,
        title="Old.pdf",
        source_type="pdf",
        source_path="x",
        status=DocumentStatus.READY,
        updated_at=datetime.now(UTC) - timedelta(days=200),
    )
    fresh_document = Document(
        employer_id=employer_id,
        title="New.pdf",
        source_type="pdf",
        source_path="y",
        status=DocumentStatus.READY,
        last_queried_at=datetime.now(UTC),
    )
    client = TestClient(
        _test_app(document_repository=_FakeDocumentRepository([stale_document, fresh_document]))
    )

    response = client.get("/api/admin/document-health")

    assert response.status_code == 200
    body = {row["id"]: row for row in response.json()}
    assert body[str(stale_document.id)]["is_stale"] is True
    assert body[str(stale_document.id)]["zero_query_hits"] is True
    assert body[str(fresh_document.id)]["is_stale"] is False
    assert body[str(fresh_document.id)]["zero_query_hits"] is False


def test_get_document_health_surfaces_the_failed_ingestion_error_message() -> None:
    failed_document = Document(
        employer_id=uuid4(),
        title="Corrupt.pdf",
        source_type="pdf",
        source_path="z",
        status=DocumentStatus.FAILED,
        error_message="Could not parse PDF: unexpected EOF",
    )
    client = TestClient(_test_app(document_repository=_FakeDocumentRepository([failed_document])))

    response = client.get("/api/admin/document-health")

    assert response.status_code == 200
    body = response.json()[0]
    assert body["status"] == "failed"
    assert body["error_message"] == "Could not parse PDF: unexpected EOF"


def test_get_document_health_filters_by_employer() -> None:
    employer_a, employer_b = uuid4(), uuid4()
    document_a = Document(employer_id=employer_a, title="A.pdf", source_type="pdf", source_path="a")
    document_b = Document(employer_id=employer_b, title="B.pdf", source_type="pdf", source_path="b")
    client = TestClient(
        _test_app(document_repository=_FakeDocumentRepository([document_a, document_b]))
    )

    response = client.get("/api/admin/document-health", params={"employer_id": str(employer_a)})

    assert [row["id"] for row in response.json()] == [str(document_a.id)]
