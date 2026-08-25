"""Pure domain models for documents and their chunks. No framework imports."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from core.domain.policy import PolicyType


class DocumentStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    employer_id: UUID
    policy_type: PolicyType | None = None
    title: str
    source_type: str
    source_path: str
    version: int = 1
    status: DocumentStatus = DocumentStatus.PROCESSING
    error_message: str | None = None
    # Set by `DocumentRepository.mark_queried()` whenever a retrieval
    # (RAGService.retrieve()) matches one of this document's chunks —
    # `None` means "never retrieved". Step 9.6's document-health endpoint
    # is the only consumer; nothing else reads or writes it.
    last_queried_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentChunk(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    employer_id: UUID
    chunk_index: int
    text: str
    section_title: str | None = None
    page_number: int | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
