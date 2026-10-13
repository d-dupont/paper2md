"""Runs Docling on a PDF and writes the result as Markdown."""

import os
import subprocess
from collections import Counter
from pathlib import Path

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument, ImageRefMode


# Measured on an M1 Max with 8 threads (ResNet and Attention). Used only for the time estimate.
FORMULA_MODEL_STARTUP_SECONDS = 30
SECONDS_PER_FORMULA = 20


def performance_cores() -> int:
    """How many fast CPU cores to use for the models.

    Apple Silicon also has slower "efficiency" cores; using them as well made the formula
    model no faster (80.6 s with 10 threads vs 76.9 s with 8). Docling's default is 4 threads,
    which took 132.7 s on the same pages.
    """
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.perflevel0.physicalcpu"], capture_output=True, text=True, check=True
        )
        return int(result.stdout)
    except (OSError, ValueError, subprocess.CalledProcessError):  # not macOS
        return os.cpu_count() or 4


def convert_pdf(pdf: Path, ocr: bool = False, formulas: bool = False) -> DoclingDocument:
    """Run Docling's layout and table models on `pdf` and return the structured document."""
    options = PdfPipelineOptions(
        # arXiv PDFs contain real text, so OCR (reading text from page images) is off by default.
        do_ocr=ocr,
        # Run a vision-language model on each detected equation to turn it into LaTeX.
        do_formula_enrichment=formulas,
        accelerator_options=AcceleratorOptions(num_threads=performance_cores()),
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    return converter.convert(pdf).document


def write_markdown(doc: DoclingDocument, paper_dir: Path) -> Path:
    """Write `paper_dir/paper.md`, linking figures to the files that figures.py saved."""
    path = paper_dir / "paper.md"
    # Write text as it is, for Claude rather than for a Markdown viewer: no "\\_" (subscripts
    # are written x_{1}) and no "&lt;" / "&amp;" ("|∆| < α", "Hinton & Salakhutdinov").
    markdown = doc.export_to_markdown(
        image_mode=ImageRefMode.REFERENCED, escape_underscores=False, escape_html=False
    )
    path.write_text(markdown, encoding="utf-8")
    return path


def count_item_types(doc: DoclingDocument) -> Counter:
    """Count what the layout model detected: how many headings, paragraphs, tables, etc."""
    return Counter(item.label.value for item, _level in doc.iterate_items())
