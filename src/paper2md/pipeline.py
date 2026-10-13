"""The conversion steps, in order. Imported by cli.py only after it has set the output volume,
because the libraries read their logging settings when they are first imported."""

import time
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from paper2md.accents import fix_accents
from paper2md.convert import FORMULA_MODEL_STARTUP_SECONDS, SECONDS_PER_FORMULA, convert_pdf, count_item_types, write_markdown
from paper2md.equations import save_equations
from paper2md.figures import save_figures
from paper2md.metadata import information_block
from paper2md.pages import mark_page_breaks_inside_text, mark_page_starts, page_names
from paper2md.reading_order import fix_reading_order
from paper2md.row_groups import fill_row_groups
from paper2md.superscripts import restore_scripts
from paper2md.tables import save_tables


def convert_with_estimate(pdf: Path, ocr: bool, formulas: bool) -> DoclingDocument:
    """Convert `pdf`; when converting equations, first say how many there are and how long it will take.

    Docling only knows how many equations a paper has after its layout model has run, so we
    do a quick pass without equations (about 10 s), report, and then the slow pass.
    """
    doc = convert_pdf(pdf, ocr=ocr, formulas=False)
    count = count_item_types(doc)["formula"]
    if not formulas or count == 0:
        return doc
    minutes = (FORMULA_MODEL_STARTUP_SECONDS + count * SECONDS_PER_FORMULA) / 60
    print(f"Found {count} equations. Converting them to LaTeX takes about {max(round(minutes), 1)} min.")
    print("Press Ctrl+C to stop, or rerun with --no-formulas to skip equations.")
    return convert_pdf(pdf, ocr=ocr, formulas=True)


def process(pdf: Path, paper_dir: Path, ocr: bool, formulas: bool, verbose: bool) -> None:
    """Convert `pdf` and write paper.md, figures/ and tables/ into `paper_dir`."""
    print(f"Converting {pdf} ...")
    start = time.perf_counter()
    doc = convert_with_estimate(pdf, ocr=ocr, formulas=formulas)

    paper_dir.mkdir(parents=True, exist_ok=True)
    # Before anything else: the steps below depend on reading order and character positions.
    fix_reading_order(doc)
    names = page_names(pdf)
    # First: inserting markers into paragraphs shifts character positions (pages.py corrects
    # the stored ones), and figures.py cuts text by those positions.
    pages = mark_page_breaks_inside_text(doc, names)
    figures = save_figures(doc, pdf, paper_dir)
    pages += mark_page_starts(doc, names)
    # After the page markers: unconverted equations are replaced by a link without a location.
    equations = save_equations(doc, pdf, paper_dir)
    # After figures.py, which cuts text by character position (^{...} would shift it), and
    # before save_tables(), so the CSV files get the marks too.
    marked, skipped = restore_scripts(doc, pdf)
    fix_accents(doc)
    fill_row_groups(doc, pdf)
    tables = save_tables(doc, paper_dir)
    markdown_path = write_markdown(doc, paper_dir, information_block(doc, pdf, formulas))

    seconds = time.perf_counter() - start
    print(f"Done in {seconds:.0f}s: {doc.num_pages()} pages -> {markdown_path}")
    print(f"  {len(figures)} figures, {len(equations)} equations, {len(tables)} tables, {pages} page markers")
    if equations and not formulas:
        print("  Equations are saved as images; add --formulas to also get them as LaTeX text (slow).")
    if verbose:
        print(f"  {marked} superscripts/subscripts marked ({skipped} skipped: position in text unclear)")
        print("  Detected:")
        for label, count in count_item_types(doc).most_common():
            print(f"    {label:<16}{count}")
