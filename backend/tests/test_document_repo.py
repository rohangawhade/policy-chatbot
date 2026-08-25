from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.document_repo import (
    PostgresDocumentChunkRepository,
    PostgresDocumentRepository,
)
from adapters.persistence.employer_repo import PostgresEmployerRepository
from core.domain.document import Document, DocumentChunk, DocumentStatus
from core.domain.employer import Employer
from core.domain.policy import PolicyType
from core.ports.repository_ports import DocumentChunkRepository, DocumentRepository


async def _make_employer(db_session: AsyncSession) -> Employer:
    return await PostgresEmployerRepository(db_session).create(Employer(name="Acme Corp"))


async def _make_document(
    db_session: AsyncSession, employer_id: UUID, **overrides: object
) -> Document:
    defaults: dict[str, object] = {
        "employer_id": employer_id,
        "policy_type": PolicyType.HEALTH,
        "title": "SPD.pdf",
        "source_type": "pdf",
        "source_path": "/uploads/spd.pdf",
    }
    defaults.update(overrides)
    return await PostgresDocumentRepository(db_session).create(Document(**defaults))  # type: ignore[arg-type]


def test_is_a_document_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresDocumentRepository(db_session), DocumentRepository)


def test_is_a_document_chunk_repository(db_session: AsyncSession) -> None:
    assert isinstance(PostgresDocumentChunkRepository(db_session), DocumentChunkRepository)


async def test_create_then_get_round_trips_the_document(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)

    document = await _make_document(db_session, employer.id)
    fetched = await PostgresDocumentRepository(db_session).get(document.id)

    assert fetched is not None
    assert fetched.title == "SPD.pdf"
    assert fetched.policy_type == PolicyType.HEALTH
    assert fetched.status == DocumentStatus.PROCESSING
    assert fetched.version == 1


async def test_create_a_document_with_no_policy_type(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)

    document = await _make_document(db_session, employer.id, policy_type=None)
    fetched = await PostgresDocumentRepository(db_session).get(document.id)

    assert fetched is not None
    assert fetched.policy_type is None


async def test_list_by_employer_only_returns_that_employers_documents(
    db_session: AsyncSession,
) -> None:
    employer_a = await _make_employer(db_session)
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="Beta Corp"))
    await _make_document(db_session, employer_a.id, title="A.pdf")
    await _make_document(db_session, employer_b.id, title="B.pdf")

    result = await PostgresDocumentRepository(db_session).list_by_employer(employer_a.id)

    assert [d.title for d in result] == ["A.pdf"]


async def test_get_latest_version_returns_the_highest_version_for_that_title(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresDocumentRepository(db_session)
    await _make_document(db_session, employer.id, title="SPD.pdf", version=1)
    await _make_document(db_session, employer.id, title="SPD.pdf", version=2)
    await _make_document(db_session, employer.id, title="SPD.pdf", version=3)

    latest = await repo.get_latest_version(employer.id, "SPD.pdf")

    assert latest is not None
    assert latest.version == 3


async def test_get_latest_version_returns_none_when_no_document_matches(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)

    result = await PostgresDocumentRepository(db_session).get_latest_version(
        employer.id, "nonexistent.pdf"
    )

    assert result is None


async def test_list_all_with_no_filter_spans_every_employer(db_session: AsyncSession) -> None:
    employer_a = await _make_employer(db_session)
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="Other Co"))
    await _make_document(db_session, employer_a.id)
    await _make_document(db_session, employer_b.id)

    result = await PostgresDocumentRepository(db_session).list_all()

    assert len(result) == 2


async def test_list_all_filters_by_employer(db_session: AsyncSession) -> None:
    employer_a = await _make_employer(db_session)
    employer_b = await PostgresEmployerRepository(db_session).create(Employer(name="Other Co"))
    document_a = await _make_document(db_session, employer_a.id)
    await _make_document(db_session, employer_b.id)

    result = await PostgresDocumentRepository(db_session).list_all(employer_id=employer_a.id)

    assert [d.id for d in result] == [document_a.id]


async def test_mark_queried_sets_last_queried_at(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    document = await _make_document(db_session, employer.id)
    repo = PostgresDocumentRepository(db_session)
    assert document.last_queried_at is None

    await repo.mark_queried([document.id])

    fetched = await repo.get(document.id)
    assert fetched is not None
    assert fetched.last_queried_at is not None


async def test_mark_queried_with_an_empty_list_is_a_no_op(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    document = await _make_document(db_session, employer.id)
    repo = PostgresDocumentRepository(db_session)

    await repo.mark_queried([])

    fetched = await repo.get(document.id)
    assert fetched is not None
    assert fetched.last_queried_at is None


async def test_update_changes_status_and_error_message(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresDocumentRepository(db_session)
    document = await _make_document(db_session, employer.id)

    document.status = DocumentStatus.FAILED
    document.error_message = "extraction failed"
    updated = await repo.update(document)

    assert updated.status == DocumentStatus.FAILED
    assert updated.error_message == "extraction failed"


async def test_document_update_on_a_nonexistent_document_raises(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresDocumentRepository(db_session)
    ghost = Document(
        employer_id=employer.id, title="ghost.pdf", source_type="pdf", source_path="/x"
    )

    with pytest.raises(ValueError, match="does not exist"):
        await repo.update(ghost)


async def test_delete_removes_the_document(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    repo = PostgresDocumentRepository(db_session)
    document = await _make_document(db_session, employer.id)

    await repo.delete(document.id)

    assert await repo.get(document.id) is None


async def test_chunk_create_then_get_round_trips(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    document = await _make_document(db_session, employer.id)
    repo = PostgresDocumentChunkRepository(db_session)
    chunk = DocumentChunk(
        document_id=document.id,
        employer_id=employer.id,
        chunk_index=0,
        text="Your deductible is $500.",
        section_title="Deductibles",
        page_number=3,
    )

    await repo.create(chunk)
    fetched = await repo.get(chunk.id)

    assert fetched is not None
    assert fetched.text == "Your deductible is $500."
    assert fetched.is_active is True


async def test_chunk_update_changes_text_and_active_status(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    document = await _make_document(db_session, employer.id)
    repo = PostgresDocumentChunkRepository(db_session)
    chunk = await repo.create(
        DocumentChunk(
            document_id=document.id, employer_id=employer.id, chunk_index=0, text="original"
        )
    )

    chunk.text = "edited"
    chunk.is_active = False
    updated = await repo.update(chunk)

    assert updated.text == "edited"
    assert updated.is_active is False


async def test_chunk_update_on_a_nonexistent_chunk_raises(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    document = await _make_document(db_session, employer.id)
    repo = PostgresDocumentChunkRepository(db_session)
    ghost = DocumentChunk(
        document_id=document.id, employer_id=employer.id, chunk_index=0, text="ghost"
    )

    with pytest.raises(ValueError, match="does not exist"):
        await repo.update(ghost)


async def test_chunk_list_by_document(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    document = await _make_document(db_session, employer.id)
    repo = PostgresDocumentChunkRepository(db_session)
    await repo.create(
        DocumentChunk(
            document_id=document.id, employer_id=employer.id, chunk_index=0, text="chunk 0"
        )
    )
    await repo.create(
        DocumentChunk(
            document_id=document.id, employer_id=employer.id, chunk_index=1, text="chunk 1"
        )
    )

    result = await repo.list_by_document(document.id)

    assert {c.text for c in result} == {"chunk 0", "chunk 1"}


async def test_deactivate_by_document_marks_all_its_chunks_inactive(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    document = await _make_document(db_session, employer.id)
    repo = PostgresDocumentChunkRepository(db_session)
    chunk_a = await repo.create(
        DocumentChunk(
            document_id=document.id, employer_id=employer.id, chunk_index=0, text="chunk 0"
        )
    )
    chunk_b = await repo.create(
        DocumentChunk(
            document_id=document.id, employer_id=employer.id, chunk_index=1, text="chunk 1"
        )
    )

    await repo.deactivate_by_document(document.id)

    refetched_a = await repo.get(chunk_a.id)
    refetched_b = await repo.get(chunk_b.id)
    assert refetched_a is not None and refetched_a.is_active is False
    assert refetched_b is not None and refetched_b.is_active is False


async def test_deactivate_by_document_does_not_touch_other_documents_chunks(
    db_session: AsyncSession,
) -> None:
    employer = await _make_employer(db_session)
    document_a = await _make_document(db_session, employer.id, title="A.pdf")
    document_b = await _make_document(db_session, employer.id, title="B.pdf")
    repo = PostgresDocumentChunkRepository(db_session)
    chunk_b = await repo.create(
        DocumentChunk(
            document_id=document_b.id, employer_id=employer.id, chunk_index=0, text="b chunk"
        )
    )

    await repo.deactivate_by_document(document_a.id)

    refetched_b = await repo.get(chunk_b.id)
    assert refetched_b is not None
    assert refetched_b.is_active is True


async def test_chunk_delete_removes_it(db_session: AsyncSession) -> None:
    employer = await _make_employer(db_session)
    document = await _make_document(db_session, employer.id)
    repo = PostgresDocumentChunkRepository(db_session)
    chunk = await repo.create(
        DocumentChunk(document_id=document.id, employer_id=employer.id, chunk_index=0, text="temp")
    )

    await repo.delete(chunk.id)

    assert await repo.get(chunk.id) is None
