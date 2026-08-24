"""Document upload orchestration (files/plan.md Step 7.1, folder-structure
comment "Ingestion orchestration"). This file is the natural home for
Phase 8's fuller ingestion pipeline too — Step 7.1 adds only version
tracking, the one piece of upload behavior that has no dependency on
Celery/document processors.
"""

from uuid import UUID

from core.domain.document import Document, DocumentStatus
from core.domain.events import DocumentUploadedEvent
from core.domain.policy import PolicyType
from core.ports.event_bus_port import EventBusPort
from core.ports.repository_ports import DocumentRepository


class DocumentService:
    """Registers a new document upload, assigning it the correct version.

    Attributes:
        document_repository: Source of truth for the previous version, if
            any (`get_latest_version`, added Step 2.2/3.5 for exactly this).
        event_bus: Publishes `DocumentUploadedEvent` so Phase 8's Celery
            ingestion task can pick the document up for processing.
    """

    def __init__(self, document_repository: DocumentRepository, event_bus: EventBusPort) -> None:
        self._document_repository = document_repository
        self._event_bus = event_bus

    async def register_upload(
        self,
        employer_id: UUID,
        title: str,
        source_type: str,
        source_path: str,
        policy_type: PolicyType | None = None,
    ) -> Document:
        """Create a `Document` row for a newly uploaded file.

        Re-uploading a file with the same `title` under the same
        `employer_id` increments the version rather than creating an
        unrelated document — `get_latest_version` returning `None` means
        this is the first upload of that title, so version starts at 1.
        The new document always starts `PROCESSING`; Step 7.2's Celery
        task flips it to `READY`/`FAILED` and purges the previous
        version's vectors/chunks once re-processing completes.
        """
        previous = await self._document_repository.get_latest_version(employer_id, title)
        next_version = previous.version + 1 if previous is not None else 1

        document = Document(
            employer_id=employer_id,
            policy_type=policy_type,
            title=title,
            source_type=source_type,
            source_path=source_path,
            version=next_version,
            status=DocumentStatus.PROCESSING,
        )
        created = await self._document_repository.create(document)

        await self._event_bus.publish(
            DocumentUploadedEvent(
                document_id=created.id,
                employer_id=created.employer_id,
                title=created.title,
            )
        )
        return created
