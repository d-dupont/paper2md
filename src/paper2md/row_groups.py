"""Spreads a row-group label over all rows of its group ("(A)" in Attention's Table 3).

Results tables often label a group of rows once, in the first column, centred vertically,
with horizontal lines between the groups. Docling records such a label as an ordinary cell
on one row, and doesn't record the lines, so the CSV shows the label on one row and blanks
on the others. We read the lines from the PDF with pdfium: within a band between two lines,
if the first column holds exactly one label and is otherwise empty, the label spans the band.

Only the first column is touched: blanks elsewhere often mean "same as above" or "same as
the baseline" (as in that same Table 3), and filling them would change the table's meaning.
"""

from pathlib import Path

import pypdfium2
import pypdfium2.raw as pdfium_c
from docling_core.types.doc import DoclingDocument, TableItem

from paper2md.layout import box_of

MAX_LINE_THICKNESS = 2.0  # points: a horizontal rule is a path at most this tall...
MIN_LINE_WIDTH = 0.5  # ...spanning at least this share of the table's width
# A group label is one line of text. A taller first-column cell is usually several row labels
# that Docling merged into one ("VGG's [41] RPN RPN" in ResNet's Table 13): don't spread it.
MAX_LABEL_HEIGHT = 1.5  # times the table's typical cell height


def find_groups(row_centers: dict[int, float], rules: list[float], labels: dict[int, str]) -> list[tuple[int, int, int]]:
    """Decide which first-column labels span several rows.

    `row_centers`: row index -> vertical centre; `rules`: y of each horizontal line;
    `labels`: row index -> first-column text, for rows that have one.
    Returns (label row, first row, last row) for each label that should span its band.
    """
    rules = sorted(rules)
    bands: dict[int, list[int]] = {}
    for row, y in row_centers.items():
        bands.setdefault(sum(1 for rule in rules if rule < y), []).append(row)
    groups = []
    for band, rows in bands.items():
        if band == 0 or band == len(rules) or len(rows) < 2:
            continue  # above the first line or below the last one: not between two lines
        labelled = [row for row in rows if labels.get(row, "").strip()]
        if len(labelled) == 1:
            groups.append((labelled[0], min(rows), max(rows)))
    return groups


def horizontal_rules(page: pypdfium2.PdfPage, table: TableItem, doc: DoclingDocument) -> list[float]:
    """y positions (top-left coordinates) of horizontal lines drawn across the table."""
    box = box_of(table.prov[0], doc)
    height = page.get_height()
    rules = []
    for path in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH], max_depth=5):
        left, bottom, right, top = path.get_bounds()
        y = height - (top + bottom) / 2
        if (
            top - bottom <= MAX_LINE_THICKNESS
            and right - left >= MIN_LINE_WIDTH * (box.r - box.l)
            and box.t - MAX_LINE_THICKNESS * 2 <= y <= box.b + MAX_LINE_THICKNESS * 2
        ):
            rules.append(y)
    return rules


def fill_row_groups(doc: DoclingDocument, pdf: Path) -> int:
    """Make first-column group labels span their whole group. Returns how many were spread."""
    pdf_document = pypdfium2.PdfDocument(pdf)
    spread = 0
    for table in doc.tables:
        if not table.prov:
            continue
        page_no = table.prov[0].page_no
        rules = horizontal_rules(pdf_document[page_no - 1], table, doc)
        if len(rules) < 3:
            continue
        height = doc.pages[page_no].size.height
        centers: dict[int, list[float]] = {}
        for cell in table.data.table_cells:
            if cell.bbox is not None and cell.row_span == 1:
                box = cell.bbox.to_top_left_origin(height)
                centers.setdefault(cell.start_row_offset_idx, []).append((box.t + box.b) / 2)
        row_centers = {row: sum(ys) / len(ys) for row, ys in centers.items()}
        first_column = {
            cell.start_row_offset_idx: cell
            for cell in table.data.table_cells
            if cell.start_col_offset_idx == 0 and cell.col_span == 1 and not cell.column_header
        }
        heights = sorted(
            c.bbox.to_top_left_origin(height).b - c.bbox.to_top_left_origin(height).t
            for c in table.data.table_cells if c.bbox is not None
        )
        typical = heights[len(heights) // 2] if heights else 0
        labels = {
            row: cell.text for row, cell in first_column.items()
            if cell.bbox is not None
            and cell.bbox.to_top_left_origin(height).b - cell.bbox.to_top_left_origin(height).t <= MAX_LABEL_HEIGHT * typical
        }
        for label_row, first, last in find_groups(row_centers, rules, labels):
            cell = first_column[label_row]
            # Empty first-column cells in the group would overlap the spanning cell.
            empty = [first_column[r] for r in range(first, last + 1) if r != label_row and r in first_column]
            table.data.table_cells = [c for c in table.data.table_cells if all(c is not e for e in empty)]
            cell.start_row_offset_idx, cell.end_row_offset_idx = first, last + 1
            cell.row_span = last - first + 1
            spread += 1
    pdf_document.close()
    return spread
