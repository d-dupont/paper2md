"""Command-line interface: reads the arguments and hands off to the converter."""

import argparse
import time
from pathlib import Path

from paper2md.convert import convert_pdf, count_item_types, write_markdown
from paper2md.figures import save_figures
from paper2md.superscripts import restore_scripts
from paper2md.tables import save_tables


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper2md",
        description="Convert an academic PDF into Claude-friendly Markdown, figures and tables.",
    )
    parser.add_argument("pdf", type=Path, help="path to the PDF file to convert")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("output"),
        help="folder to write results into (default: output/)",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="read text from page images too (slower; for scanned PDFs)",
    )
    parser.add_argument(
        "--formulas",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="convert equations to LaTeX (default: on; about 35 s per equation)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    pdf: Path = args.pdf
    if not pdf.is_file():
        parser.error(f"file not found: {pdf}")
    if pdf.suffix.lower() != ".pdf":
        parser.error(f"not a .pdf file: {pdf}")

    # Each paper gets its own subfolder, named after the PDF (e.g. output/1512.03385/).
    paper_dir = args.out / pdf.stem

    print(f"Converting {pdf} ...")
    start = time.perf_counter()
    doc = convert_pdf(pdf, ocr=args.ocr, formulas=args.formulas)
    seconds = time.perf_counter() - start

    paper_dir.mkdir(parents=True, exist_ok=True)
    figures = save_figures(doc, pdf, paper_dir)
    # After figures.py, which cuts text by character position (^{...} would shift it), and
    # before save_tables(), so the CSV files get the marks too.
    marked, skipped = restore_scripts(doc, pdf)
    tables = save_tables(doc, paper_dir)
    markdown_path = write_markdown(doc, paper_dir)

    print(f"Done in {seconds:.1f}s: {doc.num_pages()} pages -> {markdown_path}")
    print(f"Saved {len(figures)} figures to {paper_dir / 'figures'}/")
    print(f"Saved {len(tables)} tables to {paper_dir / 'tables'}/")
    print(f"Marked {marked} superscripts/subscripts ({skipped} skipped: position in text unclear)")
    print("Detected:")
    for label, count in count_item_types(doc).most_common():
        print(f"  {label:<16}{count}")
