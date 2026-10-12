"""Command-line interface: reads the arguments and hands off to the converter."""

import argparse
from pathlib import Path


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

    print(f"Input:  {pdf}")
    print(f"Output: {paper_dir}/")
