from uuid import UUID, uuid4

from core.domain.document import Document, DocumentStatus
from core.domain.events import DocumentUploadedEvent, DomainEvent
from core.domain.policy import PolicyType
from core.ports.event_bus_port import EventBusPort, EventHandler
from core.ports.repository_ports import DocumentRepository
from core.services.document_service import DocumentService


class FakeDocumentRepository(DocumentRepository):
    def __init__(self, existing: list[Document] | None = None) -> None:
        self.documents: list[Document] = list(existing or [])
        self.created: list[Document] = []

    async def get(self, entity_id: UUID) -> Document | None:
        raise NotImplementedError

    async def create(self, entity: Document) -> Document:
        self.created.append(entity)
        self.documents.append(entity)
        return entity

    async def update(self, entity: Document) -> Document:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def list_by_employer(self, employer_id: UUID) -> list[Document]:
        raise NotImplementedError

    async def get_latest_version(self, employer_id: UUID, title: str) -> Document | None:
        matches = [
            document
            for document in self.documents
            if document.employer_id == employer_id and document.title == title
        ]
        if not matches:
            return None
        return max(matches, key=lambda document: document.version)

    async def list_all(self, *, employer_id: UUID | None = None) -> list[Document]:
        raise NotImplementedError

    async def mark_queried(self, document_ids: list[UUID]) -> None:
        raise NotImplementedError


class FakeEventBus(EventBusPort):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError


async def test_first_upload_of_a_title_starts_at_version_one() -> None:
    repository = FakeDocumentRepository()
    service = DocumentService(document_repository=repository, event_bus=FakeEventBus())
    employer_id = uuid4()

    document = await service.register_upload(
        employer_id=employer_id,
        title="Summary Plan Description",
        source_type="pdf",
        source_path="s3://bucket/spd-v1.pdf",
    )

    assert document.version == 1
    assert document.status == DocumentStatus.PROCESSING
    assert repository.created == [document]


async def test_reupload_of_the_same_title_and_employer_increments_version() -> None:
    employer_id = uuid4()
    existing = Document(
        employer_id=employer_id,
        title="Summary Plan Description",
        source_type="pdf",
        source_path="s3://bucket/spd-v1.pdf",
        version=1,
        status=DocumentStatus.READY,
    )
    repository = FakeDocumentRepository(existing=[existing])
    service = DocumentService(document_repository=repository, event_bus=FakeEventBus())

    document = await service.register_upload(
        employer_id=employer_id,
        title="Summary Plan Description",
        source_type="pdf",
        source_path="s3://bucket/spd-v2.pdf",
    )

    assert document.version == 2
    assert document.id != existing.id


async def test_increments_from_the_highest_existing_version_not_just_the_first_match() -> None:
    employer_id = uuid4()
    v1 = Document(
        employer_id=employer_id,
        title="Dental Plan",
        source_type="pdf",
        source_path="s3://bucket/dental-v1.pdf",
        version=1,
    )
    v2 = Document(
        employer_id=employer_id,
        title="Dental Plan",
        source_type="pdf",
        source_path="s3://bucket/dental-v2.pdf",
        version=2,
    )
    repository = FakeDocumentRepository(existing=[v1, v2])
    service = DocumentService(document_repository=repository, event_bus=FakeEventBus())

    document = await service.register_upload(
        employer_id=employer_id,
        title="Dental Plan",
        source_type="pdf",
        source_path="s3://bucket/dental-v3.pdf",
    )

    assert document.version == 3


async def test_same_title_under_a_different_employer_does_not_share_versions() -> None:
    other_employer_existing = Document(
        employer_id=uuid4(),
        title="Summary Plan Description",
        source_type="pdf",
        source_path="s3://bucket/other-employer.pdf",
        version=5,
    )
    repository = FakeDocumentRepository(existing=[other_employer_existing])
    service = DocumentService(document_repository=repository, event_bus=FakeEventBus())

    document = await service.register_upload(
        employer_id=uuid4(),
        title="Summary Plan Description",
        source_type="pdf",
        source_path="s3://bucket/spd.pdf",
    )

    assert document.version == 1


async def test_a_different_title_under_the_same_employer_does_not_share_versions() -> None:
    employer_id = uuid4()
    existing = Document(
        employer_id=employer_id,
        title="Dental Plan",
        source_type="pdf",
        source_path="s3://bucket/dental.pdf",
        version=4,
    )
    repository = FakeDocumentRepository(existing=[existing])
    service = DocumentService(document_repository=repository, event_bus=FakeEventBus())

    document = await service.register_upload(
        employer_id=employer_id,
        title="Vision Plan",
        source_type="pdf",
        source_path="s3://bucket/vision.pdf",
    )

    assert document.version == 1


async def test_registers_optional_policy_type() -> None:
    repository = FakeDocumentRepository()
    service = DocumentService(document_repository=repository, event_bus=FakeEventBus())

    document = await service.register_upload(
        employer_id=uuid4(),
        title="Dental Plan",
        source_type="pdf",
        source_path="s3://bucket/dental.pdf",
        policy_type=PolicyType.DENTAL,
    )

    assert document.policy_type == PolicyType.DENTAL


async def test_publishes_document_uploaded_event_with_the_created_documents_identity() -> None:
    repository = FakeDocumentRepository()
    event_bus = FakeEventBus()
    service = DocumentService(document_repository=repository, event_bus=event_bus)
    employer_id = uuid4()

    document = await service.register_upload(
        employer_id=employer_id,
        title="Summary Plan Description",
        source_type="pdf",
        source_path="s3://bucket/spd.pdf",
    )

    assert len(event_bus.published) == 1
    event = event_bus.published[0]
    assert isinstance(event, DocumentUploadedEvent)
    assert event.document_id == document.id
    assert event.employer_id == employer_id
    assert event.title == "Summary Plan Description"
