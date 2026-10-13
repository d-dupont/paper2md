"""Adds page markers like [p. 12] so text can be cited by page.

A marker goes before each item that starts on a different page than the previous one ended
on. A paragraph that runs over a page break gets its marker inside the text, at the exact
character where the new page starts (Docling records which characters came from which
page). The page name is the PDF's own printed page label when it has one (journals often
start at e.g. 4567); without labels, the number printed in the page's header or footer when
those run consistently (the Federal Register's 75191, 75192, ...); else 1, 2, 3, ... When the
printed number differs from the page's position in the file, both are kept:
[p. 4567 | pdf 3], so a citation can be checked against either.
"""

import re
from collections import Counter
from pathlib import Path

import pypdfium2
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel


def page_name(label: str | None, position: int) -> str:
    """What goes after "p. " in a marker: the printed label, plus the position in the file
    ("4567 | pdf 3") when the two differ. No label: just the position."""
    label = (label or "").strip()
    if not label or label == str(position):
        return str(position)
    return f"{label} | pdf {position}"


def printed_page_offset(page_texts: list[str]) -> int | None:
    """For a PDF without page labels: the page numbers printed in its headers or footers, as an
    offset (printed number = position + offset), or None if there is no consistent one.

    The Federal Register prints "75196 Federal Register / Vol. 88 ..." at the top of a page
    that is the PDF's 6th; journals print their page range. A number counts when it starts or
    ends one of a page's first or last three lines, and the same offset must hold on at least
    half the pages (so a year or a volume number, which doesn't go up by one per page, never wins).
    """
    votes: Counter = Counter()
    for position, text in enumerate(page_texts, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        numbers = set()
        for line in lines[:3] + lines[-3:]:
            for m in re.finditer(r"^\d{1,6}(?=\s|$)|(?<=\s)\d{1,6}$", line):
                numbers.add(int(m.group()))
        for number in numbers:
            votes[number - position] += 1
    if not votes:
        return None
    offset, count = votes.most_common(1)[0]
    return offset if count >= 2 and count * 2 >= len(page_texts) else None


def page_names(pdf: Path) -> dict[int, str]:
    """Docling page number (1-based) -> the page's name for its marker (see page_name)."""
    document = pypdfium2.PdfDocument(pdf)
    labels = [document.get_page_label(i) for i in range(len(document))]
    if not any((label or "").strip() for label in labels):
        # No labels in the file: use the numbers printed on the pages, if they run consistently.
        offset = printed_page_offset([document[i].get_textpage().get_text_range() for i in range(len(document))])
        if offset:
            labels = [str(i + 1 + offset) if i + 1 + offset >= 1 else None for i in range(len(document))]
    document.close()
    return {i + 1: page_name(label, i + 1) for i, label in enumerate(labels)}


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


def mark_page_starts(doc: DoclingDocument, names: dict[int, str]) -> int:
    """Insert a "[p. N]" line before each item that starts on a different page than the previous
    item ended on. Returns how many.

    Usually that is the next page, but Docling reads each page's footnotes after the start of
    the following page, so a footnote gets its own marker and the text after it gets the
    following page's marker again. Run this after figures.py: a piece it cuts out (an axis label
    glued onto a paragraph) must not count as the start of a page.
    """
    starts, current = [], 0
    for item, _level in doc.iterate_items():
        provs = sorted(getattr(item, "prov", []), key=lambda p: p.charspan[0])
        if not provs:
            continue
        if provs[0].page_no != current:
            starts.append((item, provs[0].page_no))
        current = provs[-1].page_no
    for item, page_no in starts:
        doc.insert_text(sibling=item, label=DocItemLabel.TEXT, text=f"[p. {names[page_no]}]", after=False)
    return len(starts)
