"""Runs Docling on a PDF and writes the result as Markdown."""

from collections import Counter
from pathlib import Path

from docling.document_converter import DocumentConverter
from docling_core.types.doc import DoclingDocument


def convert_pdf(pdf: Path, paper_dir: Path) -> DoclingDocument:
    """Convert `pdf` and write `paper_dir/paper.md`. Returns the Docling document."""
    converter = DocumentConverter()
    result = converter.convert(pdf)
    doc = result.document

    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "paper.md").write_text(doc.export_to_markdown(), encoding="utf-8")
    return doc


def count_item_types(doc: DoclingDocument) -> Counter:
    """Count what the layout model detected: how many headings, paragraphs, tables, etc."""
    return Counter(item.label.value for item, _level in doc.iterate_items())
