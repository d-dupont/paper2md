"""Adds page markers like [p. 12] so text can be cited by page.

A marker goes before the first item on each new page. A paragraph that runs over a page
break gets its marker inside the text, at the exact character where the new page starts
(Docling records which characters came from which page). The page name is the PDF's own
printed page label when it has one (journals often start at e.g. 4567), else 1, 2, 3, ...
"""

from pathlib import Path

import pypdfium2
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel


def page_names(pdf: Path) -> dict[int, str]:
    """Docling page number (1-based) -> the page's printed label, or its position in the file."""
    document = pypdfium2.PdfDocument(pdf)
    names = {i + 1: (document.get_page_label(i) or "").strip() or str(i + 1) for i in range(len(document))}
    document.close()
    return names


def mark_page_breaks_inside_text(doc: DoclingDocument, names: dict[int, str]) -> int:
    """Insert " [p. N] " where a text item continues onto a new page. Returns how many."""
    count = 0
    for item in doc.texts:
        provs = sorted(item.prov, key=lambda p: p.charspan[0])
        for index in range(1, len(provs)):
            previous, current = provs[index - 1], provs[index]
            if current.page_no == previous.page_no:
                continue
            start = min(current.charspan[0], len(item.text))
            # Docling's positions can drift by a character or two after it rejoins a word
            # hyphenated across the break ("high-" + "way"), so never split a word: move
            # forward to the next space.
            while 0 < start < len(item.text) and not item.text[start - 1].isspace() and not item.text[start].isspace():
                start += 1
            before, after = item.text[:start].rstrip(), item.text[start:].lstrip()
            new_text = f"{before} [p. {names[current.page_no]}] {after}"
            # Later code (figures.py) cuts text by these character positions, so shift every
            # part after the insertion point. This page's part now starts right after the marker.
            delta = len(new_text) - len(item.text)
            for later in provs[index:]:
                later.charspan = (later.charspan[0] + delta, later.charspan[1] + delta)
            current.charspan = (len(new_text) - len(after), current.charspan[1])
            item.text = new_text
            count += 1
    return count


def add_page_markers(doc: DoclingDocument, pdf: Path) -> int:
    """Add [p. N] markers to `doc`. Must run before anything that cuts text by position.

    Returns the number of markers added.
    """
    names = page_names(pdf)
    count = mark_page_breaks_inside_text(doc, names)

    # In reading order, find the first item that starts on a page later than everything so far.
    starts, last_page = [], 0
    for item, _level in doc.iterate_items():
        pages = [p.page_no for p in getattr(item, "prov", [])]
        if not pages:
            continue
        if pages[0] > last_page:
            starts.append((item, pages[0]))
        last_page = max(last_page, *pages)
    for item, page_no in starts:
        doc.insert_text(sibling=item, label=DocItemLabel.TEXT, text=f"[p. {names[page_no]}]", after=False)
    return count + len(starts)
