"""Repository interfaces — one per entity, plus AnalyticsRepository for
the four observability tables. PostgreSQL adapters (Phase 3) implement
these; swapping to a different store means writing new adapters, zero
service-layer changes (files/plan.md's Repository Pattern principle).
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from core.domain.analytics import (
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    RequestLatencyLog,
)
from core.domain.conversation import Conversation, Message
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


class MessageRepository(RepositoryPort[Message]):
    @abstractmethod
    async def list_by_conversation(
        self, conversation_id: UUID, *, limit: int = 20
    ) -> list[Message]:
        """Most recent `limit` messages, for conversation memory (Step 6.6)."""
        ...


class FeedbackRepository(RepositoryPort[Feedback]):
    @abstractmethod
    async def list_by_employer(self, employer_id: UUID) -> list[Feedback]: ...


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
    async def list_flagged_responses(
        self, employer_id: UUID, *, status: FlaggedResponseStatus | None = None
    ) -> list[FlaggedResponse]: ...

    @abstractmethod
    async def list_guardrail_rejections(self, employer_id: UUID) -> list[GuardrailRejection]: ...
