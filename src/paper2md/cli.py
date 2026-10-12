"""Command-line interface: reads the arguments, sets the output volume, hands off to pipeline.py."""

import argparse
import logging
import os
import signal
import warnings
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
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="read text from page images too (slower; for scanned PDFs)",
    )
    parser.add_argument(
        "--formulas",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="convert equations to LaTeX (default: on; about 20 s per equation)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show the libraries' progress bars and notes, and more detail at the end",
    )
    return parser


def silence_libraries() -> None:
    """Hide progress bars, notes and warnings from Docling and the libraries it uses.

    Must run before those libraries are imported: they read these settings at import time.
    """
    os.environ.setdefault("TQDM_DISABLE", "1")  # "Loading weights: 100%|█████|" progress bars
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")  # "[transformers] Model config: ..."
    # Inherited by helper processes too, such as the one that reports "leaked semaphore"
    # objects after Ctrl+C ends the program without its usual clean-up.
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    warnings.filterwarnings("ignore")  # deprecation notes about Docling's own settings
    logging.getLogger().setLevel(logging.ERROR)  # e.g. RapidOCR's model download messages


def stop_now(_signum, _frame) -> None:
    """Ctrl+C handler. Docling's equation step swallows the usual KeyboardInterrupt and keeps
    going, so exit immediately instead. Safe: no output files are written until conversion ends."""
    print("\nStopped.", flush=True)
    os._exit(130)


def main() -> None:
    signal.signal(signal.SIGINT, stop_now)
    run()


def run(argv: list[str] | None = None) -> None:
    """The whole conversion. `argv` defaults to the command line; tests pass a list."""
    parser = build_parser()
    args = parser.parse_args(argv)

    pdf: Path = args.pdf
    if not pdf.is_file():
        parser.error(f"file not found: {pdf}")
    if pdf.suffix.lower() != ".pdf":
        parser.error(f"not a .pdf file: {pdf}")

    if not args.verbose:
        silence_libraries()
    from paper2md.pipeline import process  # only now: see silence_libraries()

    # Each paper gets its own subfolder, named after the PDF (e.g. output/1512.03385/).
    process(pdf, args.out / pdf.stem, ocr=args.ocr, formulas=args.formulas, verbose=args.verbose)
