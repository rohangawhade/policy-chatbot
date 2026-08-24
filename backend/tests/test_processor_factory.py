import pytest

from adapters.document_processors.docx_processor import DOCXProcessor
from adapters.document_processors.pdf_processor import PDFProcessor
from adapters.document_processors.processor_factory import ProcessorFactory
from adapters.document_processors.xlsx_processor import XLSXProcessor
from adapters.document_processors.xml_processor import XMLProcessor
from core.domain.errors import UnsupportedFormatError


@pytest.mark.parametrize(
    ("extension", "expected_type"),
    [
        ("pdf", PDFProcessor),
        ("docx", DOCXProcessor),
        ("xlsx", XLSXProcessor),
        ("xml", XMLProcessor),
    ],
)
def test_get_returns_the_registered_processor_for_each_built_in_extension(
    extension: str, expected_type: type
) -> None:
    processor = ProcessorFactory.get(extension)

    assert isinstance(processor, expected_type)


def test_get_is_case_insensitive() -> None:
    assert isinstance(ProcessorFactory.get("PDF"), PDFProcessor)


def test_get_accepts_an_extension_with_a_leading_dot() -> None:
    assert isinstance(ProcessorFactory.get(".pdf"), PDFProcessor)


def test_get_returns_a_new_instance_each_call() -> None:
    first = ProcessorFactory.get("pdf")
    second = ProcessorFactory.get("pdf")

    assert first is not second


def test_get_raises_unsupported_format_error_for_an_unregistered_extension() -> None:
    with pytest.raises(UnsupportedFormatError) as exc_info:
        ProcessorFactory.get("csv")

    assert exc_info.value.extension == "csv"
    assert exc_info.value.code == "unsupported_format"


def test_register_adds_a_new_extension_without_affecting_existing_ones() -> None:
    class _FakeProcessor(PDFProcessor):
        pass

    try:
        ProcessorFactory.register("fake", _FakeProcessor)

        assert isinstance(ProcessorFactory.get("fake"), _FakeProcessor)
        assert isinstance(ProcessorFactory.get("pdf"), PDFProcessor)
    finally:
        del ProcessorFactory._processors["fake"]
