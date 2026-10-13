"""Command-line interface: reads the arguments, sets the output volume, hands off to pipeline.py."""

import argparse
import logging
import os
import signal
import warnings
from pathlib import Path

from paper2md.arxiv import download, parse_arxiv_id, pdf_path


def output_dir(value: str) -> Path:
    """Turn the --out argument into a path, expanding a leading `~` ourselves.

    bash and zsh replace `~` with the home directory before the program ever sees it, so this
    never came up on macOS. PowerShell passes it through unchanged, so `--out ~/papers` on
    Windows would create a folder named literally `~`. expanduser() leaves other paths alone.
    """
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper2md",
        description="Convert an academic PDF into Claude-friendly Markdown, figures and tables.",
    )
    parser.add_argument(
        "pdf",
        help="the PDF file to convert, or an arXiv ID or link (e.g. 2307.09288), which is downloaded",
    )
    parser.add_argument(
        "--out",
        type=output_dir,
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
        default=False,
        help="also convert equations to LaTeX text (slow: about 20 s per equation); "
        "without it, equations are saved as images",
    )
    parser.add_argument(
        "--bill",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="treat the PDF as a line-numbered bill (default: detected automatically); "
        "--no-bill forces the normal conversion",
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

    pdf = Path(args.pdf).expanduser()  # PowerShell leaves `~` for us to expand: see output_dir()
    if not pdf.is_file():
        arxiv_id = parse_arxiv_id(args.pdf)
        if arxiv_id is None:
            parser.error(f"file not found, and not an arXiv ID or link: {args.pdf}")
        pdf = pdf_path(arxiv_id, args.out)
        if not pdf.exists():  # downloaded before: reuse it
            print(f"Downloading arXiv {arxiv_id} ...", flush=True)
            try:
                download(arxiv_id, args.out)
            except OSError as error:
                parser.error(f"could not download arXiv {arxiv_id}: {error}")
    if pdf.suffix.lower() != ".pdf":
        parser.error(f"not a .pdf file: {pdf}")

    # Congressional bills: margin line numbers on most pages. Read them without Docling.
    from paper2md.bills import is_line_numbered, process_bill, read_pages

    if args.bill is not False:
        pages = read_pages(pdf)
        if args.bill or is_line_numbered(pages):
            print(f"Converting {pdf} (line-numbered bill) ...")
            process_bill(pdf, args.out / pdf.stem, pages)
            return

    if not args.verbose:
        silence_libraries()
    from paper2md.pipeline import process  # only now: see silence_libraries()

    # Each paper gets its own subfolder, named after the PDF (e.g. output/1512.03385/).
    process(pdf, args.out / pdf.stem, ocr=args.ocr, formulas=args.formulas, verbose=args.verbose)
