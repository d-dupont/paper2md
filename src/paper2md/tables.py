"""Saves each data table as a CSV and makes sure every table is linked to its caption.

Not everything Docling detects as a table holds data. Tables of contents and lists of
figures are labelled `document_index`; they repeat the headings and captions, so we drop
them. An uncaptioned table before the abstract is the authors' title block: it stays in
the Markdown but gets no CSV.
"""

import re
from pathlib import Path

import pandas as pd
from docling_core.types.doc import DoclingDocument, TableItem, TextItem
from docling_core.types.doc.labels import DocItemLabel

from paper2md.layout import Box, attach_caption, box_of, continue_caption

TABLE_CAPTION = re.compile(r"^\s*table\s*(\d+)", re.IGNORECASE)
# A plain-text block only counts as a caption when the number is followed by ":" or "." (or
# nothing): "Table 5: SFT annotation ..." is a caption, "Table 5 shows ..." is a sentence.
TEXT_TABLE_CAPTION = re.compile(r"^\s*table\s*(\d+)\s*([:.]|$)", re.IGNORECASE)
FIRST_SECTION = re.compile(r"^\s*(abstract|1\.?\s|i\.?\s|introduction)", re.IGNORECASE)


def table_number(caption: TextItem | None) -> int | None:
    match = TABLE_CAPTION.match(caption.text) if caption is not None else None
    return int(match.group(1)) if match else None


def current_caption(doc: DoclingDocument, table: TableItem) -> TextItem | None:
    """The table's caption, if Docling linked one that really is a "Table N" caption."""
    for ref in table.captions:
        caption = ref.resolve(doc)
        if table_number(caption) is not None:
            return caption
    return None


def nearest_caption(table_box: Box, captions: list[tuple[TextItem, Box]]) -> TextItem | None:
    """The closest caption directly above or below the table (papers use either side)."""
    best, best_gap = None, float("inf")
    for caption, box in captions:
        if not (box.l < table_box.r and table_box.l < box.r):  # not in the same columns
            continue
        gap = box.t - table_box.b if box.t >= table_box.b else table_box.t - box.b
        if 0 <= gap < best_gap:
            best, best_gap = caption, gap
    return best


def caption_candidates(texts: list[TextItem]) -> list[TextItem]:
    """All "Table N" captions among `texts`.

    Docling sometimes labels a caption as plain text (11 tables in the Llama 2 paper). Such
    text is accepted only for table numbers that have no properly labelled caption, and only
    when it reads like a caption ("Table 5: ...", not "Table 5 shows ...").
    """
    labelled = [t for t in texts if t.label == DocItemLabel.CAPTION and t.prov and table_number(t) is not None]
    have_caption = {table_number(t) for t in labelled}
    unlabelled = [
        t for t in texts
        if t.label == DocItemLabel.TEXT and t.prov and TEXT_TABLE_CAPTION.match(t.text)
        and table_number(t) not in have_caption
    ]
    return labelled + unlabelled


def link_captions(doc: DoclingDocument, tables: list[TableItem]) -> None:
    """Give each table without a proper caption the nearest unclaimed "Table N" caption."""
    claimed = {c.self_ref for t in tables if (c := current_caption(doc, t)) is not None}
    free = [t for t in caption_candidates(doc.texts) if t.self_ref not in claimed]
    for table in tables:
        if current_caption(doc, table) is not None:
            continue
        page_no = table.prov[0].page_no
        candidates = [(c, box_of(c.prov[0], doc)) for c in free if c.prov[0].page_no == page_no]
        caption = nearest_caption(box_of(table.prov[0], doc), candidates)
        if caption is not None:
            attach_caption(doc, table, caption)
            continue_caption(doc, caption)
            free.remove(caption)


def is_title_block(doc: DoclingDocument, table: TableItem) -> bool:
    """True if this uncaptioned table comes before the abstract or first section."""
    if current_caption(doc, table) is not None:
        return False
    for item, _level in doc.iterate_items():
        if item is table:
            return True
        if item.label == DocItemLabel.SECTION_HEADER and FIRST_SECTION.match(item.text):
            return False
    return False


def save_tables(doc: DoclingDocument, paper_dir: Path) -> list[tuple[Path, str]]:
    """Save data tables as `paper_dir/tables/table-NN.csv`. Returns (path, caption) pairs.

    Tables without a caption are saved as untitled-table-NN.csv.
    """
    tables_dir = paper_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    # Remove tables from a previous run so a re-run never leaves stale files behind.
    for old in tables_dir.glob("*.csv"):
        old.unlink()

    indexes = [t for t in doc.tables if t.label == DocItemLabel.DOCUMENT_INDEX]
    if indexes:
        doc.delete_items(node_items=indexes)

    tables = [t for t in doc.tables if not is_title_block(doc, t)]
    link_captions(doc, tables)

    saved, used_names, untitled = [], set(), 0
    for table in tables:
        caption = current_caption(doc, table)
        number = table_number(caption)
        if number is not None:
            name = f"table-{number:02d}"
        else:
            untitled += 1
            name = f"untitled-table-{untitled:02d}"
        while name in used_names:  # e.g. a table continued on the next page
            name += "b"
        used_names.add(name)

        frame = table.export_to_dataframe(doc=doc)
        # Docling names the columns 0, 1, 2, ... when it found no header row.
        has_header = not isinstance(frame.columns, pd.RangeIndex)
        path = tables_dir / f"{name}.csv"
        frame.to_csv(path, index=False, header=has_header)
        saved.append((path, caption.text if caption else ""))
    return saved
