"""PostgreSQL implementations of `DocumentRepository` and
`DocumentChunkRepository`."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence import models
from adapters.persistence.base_repository import PostgresRepository
from core.domain.document import Document, DocumentChunk
from core.domain.policy import PolicyType
from core.ports.repository_ports import DocumentChunkRepository, DocumentRepository


def _orm_policy_type(policy_type: PolicyType | None) -> models.PolicyType | None:
    return models.PolicyType[policy_type.name] if policy_type is not None else None


class PostgresDocumentRepository(PostgresRepository[Document, models.Document], DocumentRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.Document)

    def _to_orm(self, entity: Document) -> models.Document:
        return models.Document(
            id=entity.id,
            employer_id=entity.employer_id,
            policy_type=_orm_policy_type(entity.policy_type),
            title=entity.title,
            source_type=entity.source_type,
            source_path=entity.source_path,
            version=entity.version,
            status=models.DocumentStatus[entity.status.name],
            error_message=entity.error_message,
            last_queried_at=entity.last_queried_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_domain(self, orm_obj: models.Document) -> Document:
        return Document.model_validate(orm_obj)

    def _apply_update(self, existing: models.Document, entity: Document) -> None:
        existing.employer_id = entity.employer_id
        existing.policy_type = _orm_policy_type(entity.policy_type)
        existing.title = entity.title
        existing.source_type = entity.source_type
        existing.source_path = entity.source_path
        existing.version = entity.version
        existing.status = models.DocumentStatus[entity.status.name]
        existing.error_message = entity.error_message
        existing.last_queried_at = entity.last_queried_at

    async def list_by_employer(self, employer_id: UUID) -> list[Document]:
        result = await self._session.execute(
            select(models.Document).where(models.Document.employer_id == employer_id)
        )
        return [self._to_domain(row) for row in result.scalars().all()]

    async def get_latest_version(self, employer_id: UUID, title: str) -> Document | None:
        result = await self._session.execute(
            select(models.Document)
            .where(models.Document.employer_id == employer_id, models.Document.title == title)
            .order_by(models.Document.version.desc())
            .limit(1)
        )
        orm_obj = result.scalar_one_or_none()
        return self._to_domain(orm_obj) if orm_obj is not None else None

    async def list_all(self, *, employer_id: UUID | None = None) -> list[Document]:
        query = select(models.Document)
        if employer_id is not None:
            query = query.where(models.Document.employer_id == employer_id)
        result = await self._session.execute(query)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def mark_queried(self, document_ids: list[UUID]) -> None:
        if not document_ids:
            return
        await self._session.execute(
            update(models.Document)
            .where(models.Document.id.in_(document_ids))
            .values(last_queried_at=datetime.now(UTC))
        )
        await self._session.flush()


class PostgresDocumentChunkRepository(
    PostgresRepository[DocumentChunk, models.DocumentChunk], DocumentChunkRepository
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.DocumentChunk)

    def _to_orm(self, entity: DocumentChunk) -> models.DocumentChunk:
        return models.DocumentChunk(
            id=entity.id,
            document_id=entity.document_id,
            employer_id=entity.employer_id,
            chunk_index=entity.chunk_index,
            text=entity.text,
            section_title=entity.section_title,
            page_number=entity.page_number,
            is_active=entity.is_active,
            created_at=entity.created_at,
        )

    def _to_domain(self, orm_obj: models.DocumentChunk) -> DocumentChunk:
        return DocumentChunk.model_validate(orm_obj)

    def _apply_update(self, existing: models.DocumentChunk, entity: DocumentChunk) -> None:
        existing.document_id = entity.document_id
        existing.employer_id = entity.employer_id
        existing.chunk_index = entity.chunk_index
        existing.text = entity.text
        existing.section_title = entity.section_title
        existing.page_number = entity.page_number
        existing.is_active = entity.is_active

    async def list_by_document(self, document_id: UUID) -> list[DocumentChunk]:
        result = await self._session.execute(
            select(models.DocumentChunk).where(models.DocumentChunk.document_id == document_id)
        )
        return [self._to_domain(row) for row in result.scalars().all()]

    async def deactivate_by_document(self, document_id: UUID) -> None:
        await self._session.execute(
            update(models.DocumentChunk)
            .where(models.DocumentChunk.document_id == document_id)
            .values(is_active=False)
        )
        await self._session.flush()
