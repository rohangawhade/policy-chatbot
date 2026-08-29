"""Tests for scripts/generate_synthetic_docs.py (Step 11.2). No real LLM
calls -- `LiteLLMAdapter.generate` is monkeypatched to return canned text.
`_OUTPUT_ROOT`/`_MANIFEST_PATH` are monkeypatched per test to an isolated
`tmp_path` so nothing touches the real `data/synthetic/`.
"""

import asyncio
import hashlib
from pathlib import Path
from unittest import mock

import fitz
import generate_synthetic_docs as script
import pytest
from docx import Document as DocxDocument


@pytest.fixture(autouse=True)
def _no_real_pacing_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


@pytest.fixture(autouse=True)
def _isolated_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_root = tmp_path / "synthetic"
    monkeypatch.setattr(script, "_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(script, "_MANIFEST_PATH", output_root / "manifest.json")


_CANNED_RESPONSE = (
    "## First Section\nBody text for the first section.\n\n"
    "## Second Section\nBody text for the second section."
)


@pytest.fixture
def _mock_llm(monkeypatch: pytest.MonkeyPatch) -> mock.AsyncMock:
    generate = mock.AsyncMock(return_value=_CANNED_RESPONSE)
    monkeypatch.setattr(script.LiteLLMAdapter, "generate", generate)
    return generate


# --- Unicode punctuation sanitization ------------------------------------


def test_to_ascii_punctuation_replaces_curly_quotes_and_dashes() -> None:
    text = "X‑rays cost $50–100, that’s the employee’s share."
    assert script._to_ascii_punctuation(text) == (
        "X-rays cost $50-100, that's the employee's share."
    )


def test_to_ascii_punctuation_replaces_space_variants() -> None:
    text = "100 % covered fully"
    assert script._to_ascii_punctuation(text) == "100 % covered fully"


# --- _parse_sections ------------------------------------------------------


def test_parse_sections_splits_on_heading_markers() -> None:
    sections = script._parse_sections(_CANNED_RESPONSE)

    assert [s.heading for s in sections] == ["First Section", "Second Section"]
    assert sections[0].body == "Body text for the first section."


def test_parse_sections_falls_back_to_overview_when_format_not_followed() -> None:
    sections = script._parse_sections("Just plain text with no headings at all.")

    assert len(sections) == 1
    assert sections[0].heading == "Overview"
    assert sections[0].body == "Just plain text with no headings at all."


# --- _normalize_heading ----------------------------------------------------


def test_normalize_heading_strips_trailing_punctuation() -> None:
    assert script._normalize_heading("Coverage Details:") == "Coverage Details"


def test_normalize_heading_truncates_to_max_length() -> None:
    long_heading = "A" * 100
    normalized = script._normalize_heading(long_heading)
    assert len(normalized) == script._HEADING_MAX_LENGTH


# --- Manifest ---------------------------------------------------------------


def test_manifest_load_returns_empty_when_no_file_exists() -> None:
    manifest = script.Manifest.load()
    assert manifest.entries == {}
    assert manifest.has("acme/health_plan_summary.docx") is False


def test_manifest_record_save_and_reload_round_trips() -> None:
    manifest = script.Manifest.load()
    manifest.record("acme/health_plan_summary.docx", model="groq/openai/gpt-oss-20b", content=b"hi")
    manifest.save()

    reloaded = script.Manifest.load()
    assert reloaded.has("acme/health_plan_summary.docx") is True
    entry = reloaded.entries["acme/health_plan_summary.docx"]
    assert entry["model"] == "groq/openai/gpt-oss-20b"
    assert entry["size_bytes"] == 2
    assert entry["sha256"] == hashlib.sha256(b"hi").hexdigest()


# --- rendering --------------------------------------------------------------


def test_render_docx_produces_a_readable_document() -> None:
    sections = [script.GeneratedSection("A Section", "Some body text.")]
    content = script._render_docx("A Title", sections)

    import io

    document = DocxDocument(io.BytesIO(content))
    paragraphs = [p.text for p in document.paragraphs]
    assert "A Title" in paragraphs
    assert "A Section" in paragraphs
    assert "Some body text." in paragraphs


def test_render_pdf_produces_a_readable_document_with_no_broken_glyphs() -> None:
    sections = [
        script.GeneratedSection(
            "Costs", "X-rays cost $50-100 and that's 100 % of the employee's share."
        )
    ]
    content = script._render_pdf("A Title", sections)

    with fitz.open(stream=content, filetype="pdf") as document:
        text = document[0].get_text()
    assert "?" not in text
    assert "A Title" in text
    assert "Costs" in text


# --- _generate_all ------------------------------------------------------


async def test_generate_all_writes_files_and_records_the_manifest(
    _mock_llm: mock.AsyncMock,
) -> None:
    generated, skipped, failed = await script._generate_all(
        dry_run=False,
        force=False,
        employer_filter="northwind-traders",
        doc_type_filter="dental_plan_summary",
        limit=None,
    )

    assert (generated, skipped, failed) == (1, 0, 0)
    written = script._OUTPUT_ROOT / "northwind-traders" / "dental_plan_summary.pdf"
    assert written.exists()
    assert script.Manifest.load().has("northwind-traders/dental_plan_summary.pdf")


async def test_generate_all_dry_run_does_not_call_the_llm_or_write_anything(
    _mock_llm: mock.AsyncMock,
) -> None:
    generated, skipped, failed = await script._generate_all(
        dry_run=True,
        force=False,
        employer_filter="northwind-traders",
        doc_type_filter="dental_plan_summary",
        limit=None,
    )

    assert (generated, skipped, failed) == (1, 0, 0)
    _mock_llm.assert_not_called()
    assert not script._OUTPUT_ROOT.exists()


async def test_generate_all_skips_a_document_already_in_the_manifest(
    _mock_llm: mock.AsyncMock,
) -> None:
    destination = script._OUTPUT_ROOT / "northwind-traders" / "dental_plan_summary.pdf"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"already here")
    manifest = script.Manifest.load()
    manifest.record(
        "northwind-traders/dental_plan_summary.pdf",
        model="groq/openai/gpt-oss-20b",
        content=b"already here",
    )
    manifest.save()

    generated, skipped, failed = await script._generate_all(
        dry_run=False,
        force=False,
        employer_filter="northwind-traders",
        doc_type_filter="dental_plan_summary",
        limit=None,
    )

    assert (generated, skipped, failed) == (0, 1, 0)
    _mock_llm.assert_not_called()


async def test_generate_all_records_a_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate = mock.AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(script.LiteLLMAdapter, "generate", generate)

    generated, skipped, failed = await script._generate_all(
        dry_run=False,
        force=False,
        employer_filter="northwind-traders",
        doc_type_filter="dental_plan_summary",
        limit=None,
    )

    assert (generated, skipped, failed) == (0, 0, 1)
    assert not (script._OUTPUT_ROOT / "northwind-traders" / "dental_plan_summary.pdf").exists()


async def test_generate_all_force_regenerates_an_existing_manifest_entry(
    _mock_llm: mock.AsyncMock,
) -> None:
    destination = script._OUTPUT_ROOT / "northwind-traders" / "dental_plan_summary.pdf"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"old content")
    manifest = script.Manifest.load()
    manifest.record(
        "northwind-traders/dental_plan_summary.pdf",
        model="groq/openai/gpt-oss-20b",
        content=b"old content",
    )
    manifest.save()

    generated, skipped, failed = await script._generate_all(
        dry_run=False,
        force=True,
        employer_filter="northwind-traders",
        doc_type_filter="dental_plan_summary",
        limit=None,
    )

    assert (generated, skipped, failed) == (1, 0, 0)
    _mock_llm.assert_called_once()
    assert destination.read_bytes() != b"old content"
