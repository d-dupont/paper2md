"""Command-line interface: reads the arguments and hands off to the converter."""

import argparse
import os
import signal
import time
from pathlib import Path

from paper2md.convert import FORMULA_MODEL_STARTUP_SECONDS, SECONDS_PER_FORMULA, convert_pdf, count_item_types, write_markdown
from paper2md.figures import save_figures
from paper2md.pages import add_page_markers
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


def stop_now(_signum, _frame) -> None:
    """Ctrl+C handler. Docling's equation step swallows the usual KeyboardInterrupt and keeps
    going, so exit immediately instead. Safe: no output files are written until conversion ends."""
    print("\nStopped.", flush=True)
    os._exit(130)


def main() -> None:
    signal.signal(signal.SIGINT, stop_now)
    run()


def convert_with_estimate(pdf: Path, ocr: bool, formulas: bool):
    """Convert `pdf`; when converting equations, first say how many there are and how long it will take.

    Docling only knows how many equations a paper has after its layout model has run, so we
    do a quick pass without equations (about 10 s), report, and then the slow pass.
    """
    doc = convert_pdf(pdf, ocr=ocr, formulas=False)
    count = count_item_types(doc)["formula"]
    if not formulas or count == 0:
        return doc
    minutes = (FORMULA_MODEL_STARTUP_SECONDS + count * SECONDS_PER_FORMULA) / 60
    estimate = f"about {max(round(minutes), 1)} min"
    print(f"Found {count} equations. Converting them to LaTeX takes {estimate}.")
    print("Press Ctrl+C to stop, or rerun with --no-formulas to skip equations.")
    return convert_pdf(pdf, ocr=ocr, formulas=True)


def run(argv: list[str] | None = None) -> None:
    """The whole conversion. `argv` defaults to the command line; tests pass a list."""
    parser = build_parser()
    args = parser.parse_args(argv)

    pdf: Path = args.pdf
    if not pdf.is_file():
        parser.error(f"file not found: {pdf}")
    if pdf.suffix.lower() != ".pdf":
        parser.error(f"not a .pdf file: {pdf}")

    # Each paper gets its own subfolder, named after the PDF (e.g. output/1512.03385/).
    paper_dir = args.out / pdf.stem

    print(f"Converting {pdf} ...")
    start = time.perf_counter()
    doc = convert_with_estimate(pdf, ocr=args.ocr, formulas=args.formulas)
    seconds = time.perf_counter() - start

    paper_dir.mkdir(parents=True, exist_ok=True)
    # First: inserting markers shifts character positions, which add_page_markers corrects for
    # the steps after it.
    pages = add_page_markers(doc, pdf)
    figures = save_figures(doc, pdf, paper_dir)
    # After figures.py, which cuts text by character position (^{...} would shift it), and
    # before save_tables(), so the CSV files get the marks too.
    marked, skipped = restore_scripts(doc, pdf)
    tables = save_tables(doc, paper_dir)
    markdown_path = write_markdown(doc, paper_dir)

    print(f"Done in {seconds:.1f}s: {doc.num_pages()} pages -> {markdown_path}")
    print(f"Added {pages} page markers")
    print(f"Saved {len(figures)} figures to {paper_dir / 'figures'}/")
    print(f"Saved {len(tables)} tables to {paper_dir / 'tables'}/")
    print(f"Marked {marked} superscripts/subscripts ({skipped} skipped: position in text unclear)")
    print("Detected:")
    for label, count in count_item_types(doc).most_common():
        print(f"  {label:<16}{count}")
