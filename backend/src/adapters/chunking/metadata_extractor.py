"""Parses a document processor's raw extracted text into page- and
heading-bounded blocks, so later chunking stages can enrich each chunk
with `section_title`/`page_number` (files/plan.md Step 4.1).

`document_title`, `policy_type`, and `employer_id` — the other three
per-chunk metadata fields plan.md lists — are not extracted here: they
already live on the `Document` domain object before any text is parsed,
so Step 4.3's `ChunkerPipeline` attaches them directly rather than this
class re-deriving them from text.
"""

import re
from dataclasses import dataclass

_HEADING_MAX_LENGTH = 80
_NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*[.)]?\s+\S")
_SHEET_MARKER = re.compile(r"^#\s+(.+)$")


@dataclass(frozen=True)
class ExtractedSection:
    """One structurally-bounded block of text: everything under a single
    detected heading, or the preamble before the first heading on a page.

    Attributes:
        section_title: The detected heading text, or `None` if this block
            precedes any detected heading.
        page_number: 1-indexed page number, or `None` when the source text
            carries no page boundaries (every format except `PDFProcessor`,
            which joins pages with a `\\f` form-feed marker).
        text: The block's body text, heading line excluded.
    """

    section_title: str | None
    page_number: int | None
    text: str


class MetadataExtractor:
    """Splits raw processor text into heading- and page-bounded sections.

    Detection is heuristic — numbered headings ("1.2 Eligibility"),
    all-caps lines, title-case lines, and `# `-prefixed markers (how
    `XLSXProcessor` denotes a sheet name) — not a real layout parser.
    plan.md originally paired PDF extraction with `unstructured` for
    that; Step 3.6 dropped it after a native crash, so this is the
    best available structure signal for chunk enrichment, not a
    guarantee of matching the source document's true outline.
    """

    def extract_sections(self, text: str) -> list[ExtractedSection]:
        """Split extracted text into per-page, per-heading sections.

        Args:
            text: Raw text from a `DocumentProcessorPort.extract_text()`
                call.

        Returns:
            Sections in document order. Empty or whitespace-only blocks
            are dropped.
        """
        sections: list[ExtractedSection] = []
        for page_number, page_text in self._split_pages(text):
            sections.extend(self._extract_page_sections(page_text, page_number))
        return sections

    def _split_pages(self, text: str) -> list[tuple[int | None, str]]:
        pages = text.split("\f")
        if len(pages) == 1:
            return [(None, pages[0])]
        return list(enumerate(pages, start=1))

    def _extract_page_sections(
        self, page_text: str, page_number: int | None
    ) -> list[ExtractedSection]:
        sections: list[ExtractedSection] = []
        current_title: str | None = None
        current_lines: list[str] = []

        def flush() -> None:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append(ExtractedSection(current_title, page_number, body))

        for line in page_text.splitlines():
            heading = self._detect_heading(line)
            if heading is not None:
                flush()
                current_title = heading
                current_lines = []
            elif line.strip():
                current_lines.append(line)
        flush()
        return sections

    def _detect_heading(self, line: str) -> str | None:
        stripped = line.strip()
        if not stripped or len(stripped) > _HEADING_MAX_LENGTH:
            return None

        sheet_match = _SHEET_MARKER.match(stripped)
        if sheet_match:
            return sheet_match.group(1).strip()

        if "|" in stripped:
            # Table rows (DOCXProcessor/XLSXProcessor join cells with " | ")
            # routinely start with capitalized cells and would otherwise
            # false-positive as a title-case heading.
            return None

        if _NUMBERED_HEADING.match(stripped):
            return stripped

        if stripped.endswith((".", ",", ";", ":")):
            return None

        if stripped.isupper() and any(char.isalpha() for char in stripped):
            return stripped

        if self._is_title_case(stripped):
            return stripped

        return None

    def _is_title_case(self, line: str) -> bool:
        words = [word for word in re.split(r"\s+", line) if word]
        significant = [word for word in words if word[0].isalpha()]
        if len(words) < 2 or not significant:
            return False
        return all(word[0].isupper() for word in significant)
