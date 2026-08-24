from pathlib import Path

import fitz
import pytest

from adapters.document_processors.pdf_processor import PDFProcessor
from core.ports.document_processor_port import DocumentProcessorPort


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "sample.pdf"
    document = fitz.open()
    try:
        document.set_metadata({"title": "Sample SPD", "author": "PolicyPal"})
        page = document.new_page()
        page.insert_text((72, 72), "Summary Plan Description")
        page.insert_text((72, 100), "Your annual deductible is $500.")
        document.new_page()
        document.save(path)
    finally:
        document.close()
    return path


def test_is_a_document_processor_port() -> None:
    assert isinstance(PDFProcessor(), DocumentProcessorPort)


def test_extract_text_returns_the_pages_text_content(sample_pdf: Path) -> None:
    text = PDFProcessor().extract_text(str(sample_pdf))

    assert "Summary Plan Description" in text
    assert "Your annual deductible is $500." in text


def test_extract_text_joins_non_empty_pages_with_a_form_feed(tmp_path: Path) -> None:
    path = tmp_path / "two-page.pdf"
    document = fitz.open()
    try:
        first_page = document.new_page()
        first_page.insert_text((72, 72), "Page one content")
        second_page = document.new_page()
        second_page.insert_text((72, 72), "Page two content")
        document.save(path)
    finally:
        document.close()

    text = PDFProcessor().extract_text(str(path))

    pages = text.split("\f")
    assert len(pages) == 2
    assert "Page one content" in pages[0]
    assert "Page two content" in pages[1]


def test_extract_metadata_returns_page_count_and_title(sample_pdf: Path) -> None:
    metadata = PDFProcessor().extract_metadata(str(sample_pdf))

    assert metadata["page_count"] == 2
    assert metadata["title"] == "Sample SPD"
    assert metadata["author"] == "PolicyPal"


def test_extract_metadata_returns_none_for_missing_title(tmp_path: Path) -> None:
    path = tmp_path / "untitled.pdf"
    document = fitz.open()
    try:
        document.new_page()
        document.save(path)
    finally:
        document.close()

    metadata = PDFProcessor().extract_metadata(str(path))

    assert metadata["title"] is None
