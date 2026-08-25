"""Admin analytics routes (files/plan.md Step 9.6) — admin role only.

Response shape matches the established convention from Step 9.1 (see
`auth_routes.py`'s module docstring) — this file returns its Pydantic
model(s) directly, not wrapped in `files/coding-standards.md` section
7's `APIResponse[T]` envelope.

Every list/aggregate here follows Step 9.5's established convention:
fetch raw rows from the repository, filter/aggregate in Python — no
repository does SQL-level `GROUP BY` in this codebase, and the volumes
involved (per-employer analytics rows) don't need one. `employer_id` is
an optional query param everywhere, not derived from the caller — an
`ADMIN` account has none of its own (`core/domain/employee.py`), and
these endpoints are explicitly cross-tenant (unlike Step 9.5's
per-employer-only feedback analytics) since that's the point of an
admin dashboard.

**Two documented interpretations, not literal spec readings**:
- `GET /api/admin/unanswered-queries`: plan.md describes "queries where
  the bot responded with 'I don't have enough information.'" — no such
  literal string is tracked anywhere (the LLM is only *instructed* to
  say so, per `RAGService`'s `_NO_CONTEXT_NOTICE`; its actual wording is
  generated, not fixed). `FlaggedResponse` rows with
  `flag_reason="low_retrieval_confidence"` are the existing structured
  signal for exactly this situation (Step 6.6), so this endpoint reuses
  them rather than pattern-matching response text.
- `GET /api/admin/document-health`'s "stale" bucket uses a fixed
  `_STALE_THRESHOLD_DAYS` (182, "6+ months") against `updated_at` —
  plan.md doesn't specify an exact day count for "6 months".
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.dependencies import (
    get_analytics_repository,
    get_conversation_repository,
    get_document_repository,
    get_feedback_repository,
    get_message_repository,
)
from api.middleware.auth_middleware import require_role
from config import llm_config
from core.domain.analytics import FlaggedResponse, FlaggedResponseStatus
from core.domain.conversation import MessageRole
from core.domain.document import DocumentStatus
from core.domain.employee import UserRole
from core.domain.feedback import FeedbackRating
from core.domain.policy import PolicyType
from core.ports.repository_ports import (
    AnalyticsRepository,
    ConversationRepository,
    DocumentRepository,
    FeedbackRepository,
    MessageRepository,
)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)

_STALE_THRESHOLD_DAYS = 182
_UNANSWERED_FLAG_REASON = "low_retrieval_confidence"
_TERMINAL_FLAG_STATUSES = frozenset(
    {
        FlaggedResponseStatus.REVIEWED,
        FlaggedResponseStatus.DISMISSED,
        FlaggedResponseStatus.ESCALATED,
    }
)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, ceil(p / 100 * len(ordered)) - 1))
    return ordered[index]


class OverviewResponse(BaseModel):
    total_queries_today: int
    total_queries_week: int
    total_queries_month: int
    active_users_week: int
    document_count: int
    avg_satisfaction: float
    cost_this_month_usd: float


class CostByModel(BaseModel):
    model: str
    total_cost_usd: float
    call_count: int


class CostByEmployer(BaseModel):
    employer_id: UUID
    total_cost_usd: float


class CostByDay(BaseModel):
    date: str
    total_cost_usd: float


class CostDashboardResponse(BaseModel):
    total_cost_usd: float
    by_model: list[CostByModel]
    by_employer: list[CostByEmployer]
    by_day: list[CostByDay]


class CostAlert(BaseModel):
    employer_id: UUID
    date: str
    total_cost_usd: float
    threshold_usd: float


class LatencyStats(BaseModel):
    label: str
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float


class LatencyResponse(BaseModel):
    overall: LatencyStats
    by_model_tier: list[LatencyStats]


class FlaggedResponseItem(BaseModel):
    id: UUID
    employer_id: UUID
    conversation_id: UUID
    message_id: UUID
    query_text: str
    top_similarity_score: float | None
    flag_reason: str
    status: FlaggedResponseStatus
    created_at: datetime


class FlaggedResponseUpdateRequest(BaseModel):
    status: FlaggedResponseStatus


class GuardrailRejectionItem(BaseModel):
    id: UUID
    employer_id: UUID
    query_text: str
    rejection_reason: str
    created_at: datetime


class TopicHeatmapCell(BaseModel):
    date: str
    policy_type: PolicyType | None
    query_count: int


class TopicHeatmapResponse(BaseModel):
    cells: list[TopicHeatmapCell]


class DocumentHealthItem(BaseModel):
    id: UUID
    employer_id: UUID
    title: str
    version: int
    status: DocumentStatus
    is_stale: bool
    zero_query_hits: bool
    last_queried_at: datetime | None
    updated_at: datetime


@router.get("/overview")
async def get_overview(
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
    message_repository: MessageRepository = Depends(get_message_repository),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
    document_repository: DocumentRepository = Depends(get_document_repository),
    feedback_repository: FeedbackRepository = Depends(get_feedback_repository),
) -> OverviewResponse:
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    queries_today = await message_repository.list_for_analytics(
        role=MessageRole.USER, start=today_start
    )
    queries_week = await message_repository.list_for_analytics(
        role=MessageRole.USER, start=week_start
    )
    queries_month = await message_repository.list_for_analytics(
        role=MessageRole.USER, start=month_start
    )
    active_conversations = await conversation_repository.list_active_since(week_start)
    documents = await document_repository.list_all()
    feedback = await feedback_repository.list_all()
    costs_this_month = await analytics_repository.list_llm_costs(start=month_start)

    total_feedback = len(feedback)
    thumbs_up = sum(1 for f in feedback if f.rating == FeedbackRating.THUMBS_UP)

    return OverviewResponse(
        total_queries_today=len(queries_today),
        total_queries_week=len(queries_week),
        total_queries_month=len(queries_month),
        active_users_week=len({c.employee_id for c in active_conversations}),
        document_count=len(documents),
        avg_satisfaction=(thumbs_up / total_feedback) if total_feedback else 0.0,
        cost_this_month_usd=sum(log.estimated_cost_usd for log in costs_this_month),
    )


@router.get("/cost-dashboard")
async def get_cost_dashboard(
    employer_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> CostDashboardResponse:
    logs = await analytics_repository.list_llm_costs(employer_id=employer_id, start=start, end=end)

    by_model: dict[str, list[float]] = defaultdict(list)
    by_employer: dict[UUID, float] = defaultdict(float)
    by_day: dict[str, float] = defaultdict(float)
    for log in logs:
        by_model[log.model].append(log.estimated_cost_usd)
        by_employer[log.employer_id] += log.estimated_cost_usd
        by_day[log.created_at.date().isoformat()] += log.estimated_cost_usd

    return CostDashboardResponse(
        total_cost_usd=sum(log.estimated_cost_usd for log in logs),
        by_model=[
            CostByModel(model=model, total_cost_usd=sum(costs), call_count=len(costs))
            for model, costs in sorted(by_model.items())
        ],
        by_employer=[
            CostByEmployer(employer_id=eid, total_cost_usd=total)
            for eid, total in by_employer.items()
        ],
        by_day=[CostByDay(date=day, total_cost_usd=total) for day, total in sorted(by_day.items())],
    )


@router.get("/cost-dashboard/alerts")
async def get_cost_dashboard_alerts(
    employer_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    threshold_usd: float | None = None,
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> list[CostAlert]:
    effective_threshold = (
        threshold_usd if threshold_usd is not None else llm_config.daily_cost_alert_threshold_usd
    )
    logs = await analytics_repository.list_llm_costs(employer_id=employer_id, start=start, end=end)

    by_employer_day: dict[tuple[UUID, str], float] = defaultdict(float)
    for log in logs:
        by_employer_day[(log.employer_id, log.created_at.date().isoformat())] += (
            log.estimated_cost_usd
        )

    return [
        CostAlert(
            employer_id=eid, date=day, total_cost_usd=total, threshold_usd=effective_threshold
        )
        for (eid, day), total in sorted(by_employer_day.items(), key=lambda item: item[0][1])
        if total > effective_threshold
    ]


@router.get("/latency")
async def get_latency(
    employer_id: UUID | None = None,
    model_tier: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> LatencyResponse:
    logs = await analytics_repository.list_latencies(
        employer_id=employer_id, model_tier=model_tier, start=start, end=end
    )
    overall_values = [float(log.total_ms) for log in logs]

    by_tier: dict[str, list[float]] = defaultdict(list)
    for log in logs:
        if log.model_tier is not None:
            by_tier[log.model_tier].append(float(log.total_ms))

    return LatencyResponse(
        overall=LatencyStats(
            label="overall",
            count=len(overall_values),
            p50_ms=_percentile(overall_values, 50),
            p95_ms=_percentile(overall_values, 95),
            p99_ms=_percentile(overall_values, 99),
        ),
        by_model_tier=[
            LatencyStats(
                label=tier,
                count=len(values),
                p50_ms=_percentile(values, 50),
                p95_ms=_percentile(values, 95),
                p99_ms=_percentile(values, 99),
            )
            for tier, values in sorted(by_tier.items())
        ],
    )


def _to_flagged_response_item(flagged: FlaggedResponse) -> FlaggedResponseItem:
    return FlaggedResponseItem(
        id=flagged.id,
        employer_id=flagged.employer_id,
        conversation_id=flagged.conversation_id,
        message_id=flagged.message_id,
        query_text=flagged.query_text,
        top_similarity_score=flagged.top_similarity_score,
        flag_reason=flagged.flag_reason,
        status=flagged.status,
        created_at=flagged.created_at,
    )


@router.get("/flagged-responses")
async def list_flagged_responses(
    employer_id: UUID | None = None,
    status_filter: FlaggedResponseStatus | None = None,
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> list[FlaggedResponseItem]:
    flagged = await analytics_repository.list_flagged_responses(
        employer_id=employer_id, status=status_filter
    )
    return [_to_flagged_response_item(f) for f in flagged]


@router.patch("/flagged-responses/{flagged_response_id}")
async def update_flagged_response(
    flagged_response_id: UUID,
    body: FlaggedResponseUpdateRequest,
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> FlaggedResponseItem:
    """Mark a flagged response reviewed, dismissed, or escalated.

    Raises:
        HTTPException: 422 if `status` is `PENDING_REVIEW` — that's the
            initial state a flagged response is created in
            (`FlaggedResponse.status`'s default, Step 6.6), never a
            target an admin action moves it *to*. 404 if no flagged
            response with this id exists.
    """
    if body.status not in _TERMINAL_FLAG_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be one of: reviewed, dismissed, escalated.",
        )
    try:
        updated = await analytics_repository.update_flagged_response_status(
            flagged_response_id, body.status
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flagged response not found."
        ) from exc
    return _to_flagged_response_item(updated)


@router.get("/guardrail-rejections")
async def list_guardrail_rejections(
    employer_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> list[GuardrailRejectionItem]:
    rejections = await analytics_repository.list_guardrail_rejections(
        employer_id=employer_id, start=start, end=end
    )
    return [
        GuardrailRejectionItem(
            id=r.id,
            employer_id=r.employer_id,
            query_text=r.query_text,
            rejection_reason=r.rejection_reason,
            created_at=r.created_at,
        )
        for r in rejections
    ]


@router.get("/unanswered-queries")
async def list_unanswered_queries(
    employer_id: UUID | None = None,
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> list[FlaggedResponseItem]:
    flagged = await analytics_repository.list_flagged_responses(employer_id=employer_id)
    return [
        _to_flagged_response_item(f) for f in flagged if f.flag_reason == _UNANSWERED_FLAG_REASON
    ]


@router.get("/topic-heatmap")
async def get_topic_heatmap(
    employer_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    message_repository: MessageRepository = Depends(get_message_repository),
) -> TopicHeatmapResponse:
    messages = await message_repository.list_for_analytics(
        employer_id=employer_id, role=MessageRole.USER, start=start, end=end
    )

    counts: dict[tuple[str, PolicyType | None], int] = defaultdict(int)
    for message in messages:
        counts[(message.created_at.date().isoformat(), message.policy_type)] += 1

    cells = [
        TopicHeatmapCell(date=day, policy_type=policy_type, query_count=count)
        for (day, policy_type), count in counts.items()
    ]
    cells.sort(key=lambda cell: (cell.date, cell.policy_type.value if cell.policy_type else ""))
    return TopicHeatmapResponse(cells=cells)


@router.get("/document-health")
async def get_document_health(
    employer_id: UUID | None = None,
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> list[DocumentHealthItem]:
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(days=_STALE_THRESHOLD_DAYS)
    documents = await document_repository.list_all(employer_id=employer_id)

    return [
        DocumentHealthItem(
            id=doc.id,
            employer_id=doc.employer_id,
            title=doc.title,
            version=doc.version,
            status=doc.status,
            is_stale=doc.updated_at < stale_cutoff,
            zero_query_hits=doc.last_queried_at is None,
            last_queried_at=doc.last_queried_at,
            updated_at=doc.updated_at,
        )
        for doc in documents
    ]
