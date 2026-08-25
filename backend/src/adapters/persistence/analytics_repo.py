"""PostgreSQL implementation of `AnalyticsRepository` — covers
`LLMCostLog`, `RequestLatencyLog`, `FlaggedResponse`, and
`GuardrailRejection` (files/plan.md Step 1.3's four observability
tables). Doesn't extend `PostgresRepository`: these are append-only
records with no `update`/`delete` in the port, and four different ORM
tables rather than one, so the generic CRUD base doesn't fit.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.policy import PolicyType
from core.ports.repository_ports import AnalyticsRepository


def _orm_policy_type(policy_type: PolicyType | None) -> models.PolicyType | None:
    return models.PolicyType[policy_type.name] if policy_type is not None else None


class PostgresAnalyticsRepository(AnalyticsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_llm_cost(self, log: LLMCostLog) -> None:
        self._session.add(
            models.LLMCostLog(
                id=log.id,
                employer_id=log.employer_id,
                model=log.model,
                model_tier=log.model_tier,
                input_tokens=log.input_tokens,
                output_tokens=log.output_tokens,
                estimated_cost_usd=log.estimated_cost_usd,
                query_complexity_score=log.query_complexity_score,
                created_at=log.created_at,
            )
        )
        await self._session.flush()

    async def record_latency(self, log: RequestLatencyLog) -> None:
        self._session.add(
            models.RequestLatencyLog(
                id=log.id,
                employer_id=log.employer_id,
                total_ms=log.total_ms,
                retrieval_ms=log.retrieval_ms,
                llm_ms=log.llm_ms,
                overhead_ms=log.overhead_ms,
                model_tier=log.model_tier,
                created_at=log.created_at,
            )
        )
        await self._session.flush()

    async def record_flagged_response(self, flagged: FlaggedResponse) -> None:
        self._session.add(
            models.FlaggedResponse(
                id=flagged.id,
                employer_id=flagged.employer_id,
                conversation_id=flagged.conversation_id,
                message_id=flagged.message_id,
                query_text=flagged.query_text,
                top_similarity_score=flagged.top_similarity_score,
                flag_reason=flagged.flag_reason,
                status=models.FlaggedResponseStatus[flagged.status.name],
                policy_type=_orm_policy_type(flagged.policy_type),
                created_at=flagged.created_at,
                updated_at=flagged.updated_at,
            )
        )
        await self._session.flush()

    async def record_guardrail_rejection(self, rejection: GuardrailRejection) -> None:
        self._session.add(
            models.GuardrailRejection(
                id=rejection.id,
                employer_id=rejection.employer_id,
                query_text=rejection.query_text,
                rejection_reason=rejection.rejection_reason,
                created_at=rejection.created_at,
            )
        )
        await self._session.flush()

    async def list_llm_costs(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[LLMCostLog]:
        query = select(models.LLMCostLog)
        if employer_id is not None:
            query = query.where(models.LLMCostLog.employer_id == employer_id)
        if start is not None:
            query = query.where(models.LLMCostLog.created_at >= start)
        if end is not None:
            query = query.where(models.LLMCostLog.created_at < end)
        result = await self._session.execute(query)
        return [LLMCostLog.model_validate(row) for row in result.scalars().all()]

    async def list_latencies(
        self,
        *,
        employer_id: UUID | None = None,
        model_tier: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[RequestLatencyLog]:
        query = select(models.RequestLatencyLog)
        if employer_id is not None:
            query = query.where(models.RequestLatencyLog.employer_id == employer_id)
        if model_tier is not None:
            query = query.where(models.RequestLatencyLog.model_tier == model_tier)
        if start is not None:
            query = query.where(models.RequestLatencyLog.created_at >= start)
        if end is not None:
            query = query.where(models.RequestLatencyLog.created_at < end)
        result = await self._session.execute(query)
        return [RequestLatencyLog.model_validate(row) for row in result.scalars().all()]

    async def list_flagged_responses(
        self, *, employer_id: UUID | None = None, status: FlaggedResponseStatus | None = None
    ) -> list[FlaggedResponse]:
        query = select(models.FlaggedResponse)
        if employer_id is not None:
            query = query.where(models.FlaggedResponse.employer_id == employer_id)
        if status is not None:
            query = query.where(
                models.FlaggedResponse.status == models.FlaggedResponseStatus[status.name]
            )
        result = await self._session.execute(query)
        return [FlaggedResponse.model_validate(row) for row in result.scalars().all()]

    async def get_flagged_response(self, flagged_response_id: UUID) -> FlaggedResponse | None:
        orm_obj = await self._session.get(models.FlaggedResponse, flagged_response_id)
        return FlaggedResponse.model_validate(orm_obj) if orm_obj is not None else None

    async def update_flagged_response_status(
        self, flagged_response_id: UUID, status: FlaggedResponseStatus
    ) -> FlaggedResponse:
        orm_obj = await self._session.get(models.FlaggedResponse, flagged_response_id)
        if orm_obj is None:
            raise ValueError(f"FlaggedResponse {flagged_response_id} does not exist.")
        orm_obj.status = models.FlaggedResponseStatus[status.name]
        await self._session.flush()
        await self._session.refresh(orm_obj)
        return FlaggedResponse.model_validate(orm_obj)

    async def list_guardrail_rejections(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[GuardrailRejection]:
        query = select(models.GuardrailRejection)
        if employer_id is not None:
            query = query.where(models.GuardrailRejection.employer_id == employer_id)
        if start is not None:
            query = query.where(models.GuardrailRejection.created_at >= start)
        if end is not None:
            query = query.where(models.GuardrailRejection.created_at < end)
        result = await self._session.execute(query)
        return [GuardrailRejection.model_validate(row) for row in result.scalars().all()]
