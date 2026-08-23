"""Abstraction over per-file-type document processors (Factory Pattern —
files/plan.md: adding a new format is one new class + one registration
line, zero changes elsewhere).

Deliberately synchronous: document parsing is CPU-bound and runs inside a
Celery task, not the async event loop (files/coding-standards.md section 9).
"""

from abc import ABC, abstractmethod
from typing import Any


class DocumentProcessorPort(ABC):
    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        """Extract raw text content from the file."""
        ...

    @abstractmethod
    def extract_metadata(self, file_path: str) -> dict[str, Any]:
        """Extract structural metadata (headings, sections, page count,
        sheet names — whatever the format supports) for chunk enrichment."""
        ...
