"""Command-line interface: reads the arguments and hands off to the converter."""

import argparse
import time
from pathlib import Path

from paper2md.convert import convert_pdf, count_item_types


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
    doc = convert_pdf(pdf, paper_dir)
    seconds = time.perf_counter() - start

    print(f"Done in {seconds:.1f}s: {doc.num_pages()} pages -> {paper_dir / 'paper.md'}")
    print("Detected:")
    for label, count in count_item_types(doc).most_common():
        print(f"  {label:<16}{count}")
