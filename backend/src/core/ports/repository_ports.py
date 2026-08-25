"""Repository interfaces — one per entity, plus AnalyticsRepository for
the four observability tables. PostgreSQL adapters (Phase 3) implement
these; swapping to a different store means writing new adapters, zero
service-layer changes (files/plan.md's Repository Pattern principle).
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.conversation import Conversation, Message, MessageRole
from core.domain.document import Document, DocumentChunk
from core.domain.employee import Employee
from core.domain.employer import Employer
from core.domain.feedback import Feedback
from core.domain.policy import Enrollment, Policy

T = TypeVar("T")


class RepositoryPort(ABC, Generic[T]):
    """Common CRUD every entity repository shares."""

    @abstractmethod
    async def get(self, entity_id: UUID) -> T | None: ...

    @abstractmethod
    async def create(self, entity: T) -> T: ...

    @abstractmethod
    async def update(self, entity: T) -> T: ...

    @abstractmethod
    async def delete(self, entity_id: UUID) -> None: ...


class EmployerRepository(RepositoryPort[Employer]):
    @abstractmethod
    async def list_all(self) -> list[Employer]: ...


class EmployeeRepository(RepositoryPort[Employee]):
    @abstractmethod
    async def get_by_email(self, email: str) -> Employee | None: ...

    @abstractmethod
    async def list_by_employer(self, employer_id: UUID) -> list[Employee]: ...


class PolicyRepository(RepositoryPort[Policy]):
    @abstractmethod
    async def list_by_employer(self, employer_id: UUID) -> list[Policy]: ...


class EnrollmentRepository(RepositoryPort[Enrollment]):
    @abstractmethod
    async def list_by_employee(self, employee_id: UUID) -> list[Enrollment]: ...

    @abstractmethod
    async def list_by_policy(self, policy_id: UUID) -> list[Enrollment]: ...


class DocumentRepository(RepositoryPort[Document]):
    @abstractmethod
    async def list_by_employer(self, employer_id: UUID) -> list[Document]: ...

    @abstractmethod
    async def get_latest_version(self, employer_id: UUID, title: str) -> Document | None:
        """Used by Step 7.1's version tracking: re-uploading a document
        with the same title under the same employer increments the
        version rather than creating an unrelated new document."""
        ...

    @abstractmethod
    async def list_all(self, *, employer_id: UUID | None = None) -> list[Document]:
        """Every document, optionally scoped to one employer. Distinct
        from `list_by_employer` (which requires one): Step 9.6's
        admin-wide `document-health` endpoint has no single tenant to
        scope to unless the caller passes one explicitly."""
        ...

    @abstractmethod
    async def mark_queried(self, document_ids: list[UUID]) -> None:
        """Set `last_queried_at` to now for every id in `document_ids`
        (Step 9.6's document-health "zero query hits" signal) — called
        by `RAGService.retrieve()` for every document a retrieval
        actually matched. A no-op for an empty list."""
        ...


class DocumentChunkRepository(RepositoryPort[DocumentChunk]):
    @abstractmethod
    async def list_by_document(self, document_id: UUID) -> list[DocumentChunk]: ...

    @abstractmethod
    async def deactivate_by_document(self, document_id: UUID) -> None:
        """Soft-delete: mark chunks inactive rather than destroying them,
        per Step 7.2's document version replacement."""
        ...


class ConversationRepository(RepositoryPort[Conversation]):
    @abstractmethod
    async def list_by_employee(self, employee_id: UUID) -> list[Conversation]: ...

    @abstractmethod
    async def list_active_since(
        self, since: datetime, *, employer_id: UUID | None = None
    ) -> list[Conversation]:
        """Conversations with at least one message created at/after
        `since` — Step 9.6's admin overview derives "active users" from
        the distinct `employee_id`s this returns, since `Message` itself
        carries no `employee_id` (only `Conversation` does)."""
        ...


class MessageRepository(RepositoryPort[Message]):
    @abstractmethod
    async def list_by_conversation(
        self, conversation_id: UUID, *, limit: int = 20
    ) -> list[Message]:
        """Most recent `limit` messages, for conversation memory (Step 6.6)."""
        ...

    @abstractmethod
    async def list_for_analytics(
        self,
        *,
        employer_id: UUID | None = None,
        role: MessageRole | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Message]:
        """Every message matching the given filters, unordered — Step
        9.6's admin overview (query counts) and topic-heatmap (grouped
        by `policy_type`, which is only ever set on `role=USER`
        messages) read through this rather than a per-conversation
        query. `employer_id=None` spans every tenant, matching every
        other admin-analytics filter in this port."""
        ...


class FeedbackRepository(RepositoryPort[Feedback]):
    @abstractmethod
    async def list_by_employer(self, employer_id: UUID) -> list[Feedback]: ...

    @abstractmethod
    async def list_all(self, *, employer_id: UUID | None = None) -> list[Feedback]:
        """Every feedback row, optionally scoped to one employer — Step
        9.6's admin overview computes an all-tenant satisfaction rate
        from this; `list_by_employer` alone can't span tenants."""
        ...


class AnalyticsRepository(ABC):
    """Covers LLMCostLog, RequestLatencyLog, FlaggedResponse, and
    GuardrailRejection — the four admin-observability tables from Step 1.3.
    A single port rather than four, since they're written together
    (fire-and-forget, off the event bus per coding-standards.md section 12)
    and read together by the admin dashboard (Phase 9)."""

    @abstractmethod
    async def record_llm_cost(self, log: LLMCostLog) -> None: ...

    @abstractmethod
    async def record_latency(self, log: RequestLatencyLog) -> None: ...

    @abstractmethod
    async def record_flagged_response(self, flagged: FlaggedResponse) -> None: ...

    @abstractmethod
    async def record_guardrail_rejection(self, rejection: GuardrailRejection) -> None: ...

    @abstractmethod
    async def list_llm_costs(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[LLMCostLog]:
        """Raw cost logs matching the given filters — Step 9.6's
        cost-dashboard aggregates (by model/employer/day) in-process from
        this, the same "fetch raw, aggregate in Python" convention Step
        9.5's feedback-analytics endpoint already established (no other
        repository in this codebase does SQL-level `GROUP BY` either)."""
        ...

    @abstractmethod
    async def list_latencies(
        self,
        *,
        employer_id: UUID | None = None,
        model_tier: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[RequestLatencyLog]:
        """Raw latency logs matching the given filters — Step 9.6's
        latency endpoint computes P50/P95/P99 in-process from this."""
        ...

    @abstractmethod
    async def list_flagged_responses(
        self, *, employer_id: UUID | None = None, status: FlaggedResponseStatus | None = None
    ) -> list[FlaggedResponse]: ...

    @abstractmethod
    async def get_flagged_response(self, flagged_response_id: UUID) -> FlaggedResponse | None: ...

    @abstractmethod
    async def update_flagged_response_status(
        self, flagged_response_id: UUID, status: FlaggedResponseStatus
    ) -> FlaggedResponse:
        """Raises `ValueError` if no flagged response with this id
        exists — same not-found contract as `PostgresRepository.update()`
        (Step 3.5); Step 9.6's `PATCH` route maps that to a 404."""
        ...

    @abstractmethod
    async def list_guardrail_rejections(
        self,
        *,
        employer_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[GuardrailRejection]: ...
