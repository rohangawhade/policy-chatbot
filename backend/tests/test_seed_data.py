"""Tests for scripts/seed_data.py (Step 11.3).

`test_seed_database_*` uses the real `db_session` fixture (a rolled-back
transaction, conftest.py) since `_seed_database` deliberately never
commits -- exactly the shape that fixture is for. Everything HTTP-facing
(`_login`/`_upload_document`/`_trigger_ingestion`) uses
`httpx.MockTransport`, no real network calls.
"""

import random
from pathlib import Path
from unittest import mock

import httpx
import pytest
import seed_data as script
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.policy_repo import PostgresEnrollmentRepository
from core.domain.employee import UserRole
from core.domain.policy import PolicyType


def test_slugify_strips_spaces_commas_and_apostrophes() -> None:
    assert script._slugify("Northwind Traders") == "northwindtraders"
    assert script._slugify("O'Brien, Inc.") == "obrieninc."


async def test_seed_database_creates_one_admin_five_employers_and_policies(
    db_session: AsyncSession,
) -> None:
    seeded = await script._seed_database(db_session, random.Random(1))

    assert len(seeded) == len(script._COMPANY_NAMES) == 5
    for entry in seeded:
        assert entry.employer.name in script._COMPANY_NAMES
        assert entry.employer_contact.role == UserRole.EMPLOYER
        assert entry.employer_contact.employer_id == entry.employer.id
        assert 10 <= len(entry.employees) <= 20
        assert {p.policy_type for p in entry.policies} == set(PolicyType)
        assert all(e.employer_id == entry.employer.id for e in entry.employees)


async def test_seed_database_enrolls_every_employee_in_one_to_three_policies(
    db_session: AsyncSession,
) -> None:
    seeded = await script._seed_database(db_session, random.Random(2))
    enrollment_repository = PostgresEnrollmentRepository(db_session)

    entry = seeded[0]
    for employee in entry.employees:
        enrollments = await enrollment_repository.list_by_employee(employee.id)
        assert 1 <= len(enrollments) <= 3
        enrolled_policy_ids = {e.policy_id for e in enrollments}
        assert enrolled_policy_ids <= {p.id for p in entry.policies}


# --- _discover_sample_documents ------------------------------------------


def test_discover_sample_documents_finds_files_under_both_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gov_dir = tmp_path / "gov_pdfs" / "opm" / "brochures"
    gov_dir.mkdir(parents=True)
    (gov_dir / "a.pdf").write_bytes(b"%PDF")
    synthetic_dir = tmp_path / "synthetic"
    synthetic_dir.mkdir()
    (synthetic_dir / "b.pdf").write_bytes(b"%PDF")

    monkeypatch.setattr(script, "_GOV_PDFS_DIR", tmp_path / "gov_pdfs")
    monkeypatch.setattr(script, "_SYNTHETIC_DIR", synthetic_dir)

    found = script._discover_sample_documents()

    assert {p.name for p in found} == {"a.pdf", "b.pdf"}


def test_discover_sample_documents_returns_empty_list_when_neither_dir_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "_GOV_PDFS_DIR", tmp_path / "does-not-exist-gov")
    monkeypatch.setattr(script, "_SYNTHETIC_DIR", tmp_path / "does-not-exist-synthetic")

    assert script._discover_sample_documents() == []


# --- _login / _upload_document / _trigger_ingestion -----------------------


async def test_login_posts_form_encoded_credentials_and_returns_the_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/auth/login"
        body = request.content.decode()
        assert "username=alice%40example.test" in body
        assert "password=hunter2" in body
        return httpx.Response(200, json={"access_token": "fake-token"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as client:
        token = await script._login(client, "alice@example.test", "hunter2")

    assert token == "fake-token"


async def test_upload_document_skips_an_unsupported_extension_without_a_request(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not upload an unsupported file type")

    unsupported = tmp_path / "notes.txt"
    unsupported.write_bytes(b"plain text, not a supported document type")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as client:
        await script._upload_document(client, "fake-token", unsupported)


@pytest.mark.parametrize(
    ("extension", "content_type"),
    [
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("xml", "application/xml"),
    ],
)
async def test_upload_document_uploads_every_format_the_api_accepts(
    tmp_path: Path, extension: str, content_type: str
) -> None:
    # Real bug, not a hypothetical: this previously only mapped "pdf",
    # silently skipping every Step 11.2 .docx synthetic document (half
    # of its 50 documents) -- must match
    # api/routes/document_routes.py's own `_ALLOWED_UPLOAD_CONTENT_TYPES`.
    document = tmp_path / f"summary.{extension}"
    document.write_bytes(b"fake content")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/documents/upload"
        assert content_type.encode() in request.content
        return httpx.Response(201, json={"id": "fake-document-id"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as client:
        await script._upload_document(client, "fake-token", document)


async def test_upload_document_posts_multipart_with_the_bearer_token(tmp_path: Path) -> None:
    pdf = tmp_path / "brochure.pdf"
    pdf.write_bytes(b"%PDF-fake")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/documents/upload"
        assert request.headers["authorization"] == "Bearer fake-token"
        assert b"brochure.pdf" in request.content
        return httpx.Response(202, json={"id": "11111111-1111-1111-1111-111111111111"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as client:
        await script._upload_document(client, "fake-token", pdf)


async def test_trigger_ingestion_warns_and_returns_early_with_no_sample_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "_GOV_PDFS_DIR", tmp_path / "no-gov-pdfs")
    monkeypatch.setattr(script, "_SYNTHETIC_DIR", tmp_path / "no-synthetic")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not attempt login/upload with zero documents discovered")

    real_client_cls = httpx.AsyncClient
    with mock.patch.object(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client_cls(transport=httpx.MockTransport(handler), **kwargs),
    ):
        await script._trigger_ingestion([], backend_url="http://example.test", docs_per_employer=3)
