"""PDF document processor: PyMuPDF for both text and structural metadata
extraction (files/plan.md Step 3.6).

Originally paired with `unstructured` for layout-aware extraction per
plan.md, but `unstructured[pdf]`'s import chain (torch, transformers,
onnxruntime, opencv, effdet) crashes natively on import in this
environment (Windows/Python 3.12) — see IMPLEMENTATION_STATUS.md's
Step 3.6 entry. Falls back to PyMuPDF alone: still real, working text
extraction, just without unstructured's title/table/paragraph element
typing.
"""

from typing import Any

import fitz

from core.ports.document_processor_port import DocumentProcessorPort


class PDFProcessor(DocumentProcessorPort):
    def extract_text(self, file_path: str) -> str:
        # Pages joined with "\f" (form feed) — the same page-break convention
        # `pdftotext` uses. Step 4.1's MetadataExtractor splits on it to
        # recover page numbers for chunk metadata; no other format's raw
        # text needs a page concept, so this stays PDF-specific.
        with fitz.open(file_path) as document:
            pages = [page.get_text().strip() for page in document]
            return "\f".join(page for page in pages if page)

    def extract_metadata(self, file_path: str) -> dict[str, Any]:
        with fitz.open(file_path) as document:
            metadata: dict[str, str] = document.metadata
            return {
                "page_count": document.page_count,
                "title": metadata.get("title") or None,
                "author": metadata.get("author") or None,
            }
