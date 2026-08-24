"""XML document processor: lxml for structured field extraction
(files/plan.md Step 3.6)."""

from typing import Any

from lxml import etree

from core.ports.document_processor_port import DocumentProcessorPort


class XMLProcessor(DocumentProcessorPort):
    def extract_text(self, file_path: str) -> str:
        tree = etree.parse(file_path)
        texts = [text.strip() for text in tree.getroot().itertext() if text and text.strip()]
        return "\n".join(texts)

    def extract_metadata(self, file_path: str) -> dict[str, Any]:
        tree = etree.parse(file_path)
        root = tree.getroot()
        return {
            "root_tag": etree.QName(root).localname,
            "element_count": sum(1 for _ in root.iter()),
        }
