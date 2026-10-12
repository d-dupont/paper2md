"""Restores superscripts and subscripts that Docling flattens (10⁻⁹ comes out as "10-9").

Docling keeps the characters but not their position, so "8.8×10¹³" becomes "8.8×1013".
We read every character's baseline and font size from the PDF with pdfium: a character
that is smaller than its neighbours and sits higher is a superscript, lower a subscript.
Each such run is then found in Docling's text by its surrounding characters and written
as ^{...} or _{...}, e.g. "10^{-9}" and "β_{1}". If a run's context can't be found exactly
once, it is left alone: a missing mark is better than a wrong one.
"""

import ctypes
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pypdfium2
import pypdfium2.raw as pdfium_c
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from paper2md.layout import Box, box_of

SMALLER = 1.15  # a neighbour this many times bigger sets the line's normal size
RAISED = 0.15  # baseline at least this fraction of the normal size higher -> superscript
LOWERED = 0.08  # ... this fraction lower -> subscript
NEIGHBOURS = 12  # how many characters to look at on each side for a normal-size one
CONTEXT = 6  # characters of context used to find a run in Docling's text
TOLERANCE = 2.0  # points: slack when testing whether a run lies inside an item's box


@dataclass
class Char:
    text: str
    baseline: float
    size: float
    center: tuple[float, float]  # top-left page coordinates, like Box


@dataclass
class Run:
    kind: str  # "^" for superscript, "_" for subscript
    text: str
    before: str
    after: str
    center: tuple[float, float]


def normalize(text: str) -> str:
    """Make pdfium's and Docling's text comparable: unify Unicode forms and minus signs, drop spaces."""
    text = unicodedata.normalize("NFKC", text).replace("−", "-")
    return "".join(text.split())


def read_chars(page: pypdfium2.PdfPage) -> list[Char]:
    textpage = page.get_textpage()
    height = page.get_height()
    chars = []
    for i in range(textpage.count_chars()):
        x, y = ctypes.c_double(), ctypes.c_double()
        pdfium_c.FPDFText_GetCharOrigin(textpage.raw, i, x, y)
        left, bottom, right, top = textpage.get_charbox(i)
        chars.append(Char(
            text=textpage.get_text_range(i, 1),
            baseline=y.value,
            size=pdfium_c.FPDFText_GetFontSize(textpage.raw, i),
            center=((left + right) / 2, height - (bottom + top) / 2),
        ))
    return chars


def classify(chars: list[Char]) -> list[str | None]:
    """Mark each character "^", "_" or None by comparing it with a nearby bigger character."""
    marks = []
    for i, char in enumerate(chars):
        mark = None
        if char.text.strip():
            # Look left and right alternately (i-1, i+1, i-2, ...) for the closest bigger
            # character that is really on the same line: horizontally near, baseline close.
            nearby = [j for d in range(1, NEIGHBOURS + 1) for j in (i - d, i + d) if 0 <= j < len(chars)]
            for j in nearby:
                other = chars[j]
                if (
                    other.text.strip()
                    and other.size >= SMALLER * char.size
                    and abs(other.baseline - char.baseline) < 0.6 * other.size
                    and abs(other.center[0] - char.center[0]) < 4 * other.size
                ):
                    if char.baseline - other.baseline > RAISED * other.size:
                        mark = "^"
                    elif other.baseline - char.baseline > LOWERED * other.size:
                        mark = "_"
                    break
        marks.append(mark)
    return marks


def find_runs(chars: list[Char]) -> list[Run]:
    marks = classify(chars)
    runs, i = [], 0
    while i < len(chars):
        if marks[i] is None:
            i += 1
            continue
        j = i
        while j < len(chars) and marks[j] == marks[i]:
            j += 1
        before = normalize("".join(c.text for c in chars[max(i - 3 * CONTEXT, 0):i]))[-CONTEXT:]
        after = normalize("".join(c.text for c in chars[j:j + 3 * CONTEXT]))[:CONTEXT]
        middle = chars[(i + j) // 2]
        runs.append(Run(marks[i], "".join(c.text for c in chars[i:j]), before, after, middle.center))
        i = j
    return runs


def locate(text: str, run: Run) -> tuple[int, int] | None:
    """Find the run in `text` by its context; return its (start, end) in `text`, or None."""
    positions, normalized = [], []
    for index, char in enumerate(text):
        for n in normalize(char):
            positions.append(index)
            normalized.append(n)
    haystack = "".join(normalized)
    needle = normalize(run.text)
    if not needle:
        return None
    # Try the longest context first, then shorter ones: a run can end a paragraph, and a
    # table cell is often shorter than the full context.
    lengths = sorted(
        ((b, a) for b in range(CONTEXT + 1) for a in range(CONTEXT + 1) if a + b > 0),
        key=lambda pair: -sum(pair),
    )
    for b, a in lengths:
        before, after = run.before[len(run.before) - b:] if b else "", run.after[:a]
        if len(before) < b or len(after) < a:
            continue
        pattern = before + needle + after
        if haystack.count(pattern) != 1:
            continue
        start = haystack.index(pattern) + len(before)
        end = start + len(needle)
        return positions[start], positions[end - 1] + 1
    return None


def mark(text: str, spans: list[tuple[int, int, str]]) -> str:
    """Wrap each (start, end, kind) span of `text` as ^{...} or _{...}, working backwards."""
    for start, end, kind in sorted(set(spans), reverse=True):
        while start > 0 and text[start - 1] == " ":  # "10 -9" -> "10^{-9}"
            start -= 1
        inner = text[start:end].strip().replace("−", "-")
        text = text[:start] + f"{kind}{{{inner}}}" + text[end:]
    return text


def contains(box: Box, point: tuple[float, float]) -> bool:
    x, y = point
    return box.l - TOLERANCE <= x <= box.r + TOLERANCE and box.t - TOLERANCE <= y <= box.b + TOLERANCE


def restore_scripts(doc: DoclingDocument, pdf: Path) -> tuple[int, int]:
    """Mark superscripts and subscripts in `doc`'s text and table cells.

    Returns (marked, skipped): runs written into the text, and runs found inside a text
    item or table cell whose context could not be matched exactly once.
    """
    pdf_document = pypdfium2.PdfDocument(pdf)
    marked = skipped = 0
    for page_no in doc.pages:
        runs = find_runs(read_chars(pdf_document[page_no - 1]))
        if not runs:
            continue
        height = doc.pages[page_no].size.height
        # Everything on this page that holds text: (box, object with a .text, pending spans).
        targets = []
        for item in doc.texts:
            if item.label == DocItemLabel.FORMULA:
                continue  # equations are handled by the formula model
            for prov in item.prov:
                if prov.page_no == page_no:
                    targets.append((box_of(prov, doc), item, []))
        for table in doc.tables:
            if table.prov and table.prov[0].page_no == page_no:
                for cell in table.data.table_cells:
                    if cell.bbox is not None:
                        b = cell.bbox.to_top_left_origin(height)
                        targets.append((Box(b.l, b.t, b.r, b.b), cell, []))

        for run in runs:
            target = next((t for t in targets if contains(t[0], run.center)), None)
            if target is None:
                continue  # e.g. inside a figure or an equation
            span = locate(target[1].text, run)
            if span is None:
                skipped += 1
            else:
                target[2].append((*span, run.kind))
                marked += 1

        # A text item spanning two pages appears in `targets` once per page; collect per object.
        pending: dict[int, tuple[object, list]] = {}
        for _box, obj, spans in targets:
            pending.setdefault(id(obj), (obj, []))[1].extend(spans)
        for obj, spans in pending.values():
            if spans:
                obj.text = mark(obj.text, spans)
    pdf_document.close()
    return marked, skipped
