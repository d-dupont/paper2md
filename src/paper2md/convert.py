"""Runs Docling on a PDF and writes the result as Markdown."""

from collections import Counter
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument, ImageRefMode


def convert_pdf(pdf: Path, ocr: bool = False, formulas: bool = False) -> DoclingDocument:
    """Run Docling's layout and table models on `pdf` and return the structured document."""
    options = PdfPipelineOptions(
        # arXiv PDFs contain real text, so OCR (reading text from page images) is off by default.
        do_ocr=ocr,
        # Run a vision-language model on each detected equation to turn it into LaTeX.
        do_formula_enrichment=formulas,
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    return converter.convert(pdf).document


def write_markdown(doc: DoclingDocument, paper_dir: Path) -> Path:
    """Write `paper_dir/paper.md`, linking figures to the files that figures.py saved."""
    path = paper_dir / "paper.md"
    # Don't escape "_" as "\\_": subscripts are written as x_{1}, and Claude reads plain text.
    markdown = doc.export_to_markdown(image_mode=ImageRefMode.REFERENCED, escape_underscores=False)
    path.write_text(markdown, encoding="utf-8")
    return path


def count_item_types(doc: DoclingDocument) -> Counter:
    """Count what the layout model detected: how many headings, paragraphs, tables, etc."""
    return Counter(item.label.value for item, _level in doc.iterate_items())
