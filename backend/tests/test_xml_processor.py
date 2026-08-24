from pathlib import Path

import pytest

from adapters.document_processors.xml_processor import XMLProcessor
from core.ports.document_processor_port import DocumentProcessorPort

_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<policy>
    <plan>
        <name>Dental PPO</name>
        <deductible>500</deductible>
    </plan>
    <plan>
        <name>Vision Basic</name>
        <deductible>0</deductible>
    </plan>
</policy>
"""


@pytest.fixture
def sample_xml(tmp_path: Path) -> Path:
    path = tmp_path / "sample.xml"
    path.write_text(_SAMPLE_XML, encoding="utf-8")
    return path


def test_is_a_document_processor_port() -> None:
    assert isinstance(XMLProcessor(), DocumentProcessorPort)


def test_extract_text_returns_every_elements_text(sample_xml: Path) -> None:
    text = XMLProcessor().extract_text(str(sample_xml))

    assert "Dental PPO" in text
    assert "500" in text
    assert "Vision Basic" in text
    assert "0" in text


def test_extract_metadata_returns_root_tag_and_element_count(sample_xml: Path) -> None:
    metadata = XMLProcessor().extract_metadata(str(sample_xml))

    assert metadata["root_tag"] == "policy"
    # root + 2 plan + 2 name + 2 deductible = 7
    assert metadata["element_count"] == 7
