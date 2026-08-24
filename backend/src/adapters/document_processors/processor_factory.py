"""Routes a file extension to the correct `DocumentProcessorPort`
implementation (Factory Pattern — files/coding-standards.md section 1's
Open/Closed example: adding a new format is one new processor class plus
one `register()` call below, zero changes to existing code or callers).
"""

from adapters.document_processors.docx_processor import DOCXProcessor
from adapters.document_processors.pdf_processor import PDFProcessor
from adapters.document_processors.xlsx_processor import XLSXProcessor
from adapters.document_processors.xml_processor import XMLProcessor
from core.domain.errors import UnsupportedFormatError
from core.ports.document_processor_port import DocumentProcessorPort


class ProcessorFactory:
    _processors: dict[str, type[DocumentProcessorPort]] = {}

    @classmethod
    def register(cls, extension: str, processor: type[DocumentProcessorPort]) -> None:
        cls._processors[extension.lower().lstrip(".")] = processor

    @classmethod
    def get(cls, extension: str) -> DocumentProcessorPort:
        processor_cls = cls._processors.get(extension.lower().lstrip("."))
        if processor_cls is None:
            raise UnsupportedFormatError(extension)
        return processor_cls()


ProcessorFactory.register("pdf", PDFProcessor)
ProcessorFactory.register("docx", DOCXProcessor)
ProcessorFactory.register("xlsx", XLSXProcessor)
ProcessorFactory.register("xml", XMLProcessor)
