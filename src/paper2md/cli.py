"""Command-line interface: reads the arguments and hands off to the converter."""

import argparse
import time
from pathlib import Path

from paper2md.convert import convert_pdf, count_item_types, write_markdown
from paper2md.figures import save_figures


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
    doc = convert_pdf(pdf, ocr=args.ocr)
    seconds = time.perf_counter() - start

    paper_dir.mkdir(parents=True, exist_ok=True)
    figures = save_figures(doc, paper_dir)
    markdown_path = write_markdown(doc, paper_dir)

    print(f"Done in {seconds:.1f}s: {doc.num_pages()} pages -> {markdown_path}")
    print(f"Saved {len(figures)} figures to {paper_dir / 'figures'}/")
    print("Detected:")
    for label, count in count_item_types(doc).most_common():
        print(f"  {label:<16}{count}")
