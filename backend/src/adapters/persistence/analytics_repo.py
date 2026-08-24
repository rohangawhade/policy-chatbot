"""PostgreSQL implementation of `AnalyticsRepository` — covers
`LLMCostLog`, `RequestLatencyLog`, `FlaggedResponse`, and
`GuardrailRejection` (files/plan.md Step 1.3's four observability
tables). Doesn't extend `PostgresRepository`: these are append-only
records with no `update`/`delete` in the port, and four different ORM
tables rather than one, so the generic CRUD base doesn't fit.
"""

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
from core.ports.repository_ports import AnalyticsRepository


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

    async def list_flagged_responses(
        self, employer_id: UUID, *, status: FlaggedResponseStatus | None = None
    ) -> list[FlaggedResponse]:
        query = select(models.FlaggedResponse).where(
            models.FlaggedResponse.employer_id == employer_id
        )
        if status is not None:
            query = query.where(
                models.FlaggedResponse.status == models.FlaggedResponseStatus[status.name]
            )
        result = await self._session.execute(query)
        return [FlaggedResponse.model_validate(row) for row in result.scalars().all()]

    async def list_guardrail_rejections(self, employer_id: UUID) -> list[GuardrailRejection]:
        result = await self._session.execute(
            select(models.GuardrailRejection).where(
                models.GuardrailRejection.employer_id == employer_id
            )
        )
        return [GuardrailRejection.model_validate(row) for row in result.scalars().all()]
