"""Repairs pages where Docling reads the right column before the left one.

On ResNet's first page Docling read the right column (Figure 1 and the rest of the
introduction) before the left one (Abstract, start of the introduction). It then also joined
paragraphs using that wrong order: page 2's first words were glued onto the left column's
last paragraph, and "...have also" was cut off from its continuation "greatly benefited...".

We only touch two-column pages where a right-column paragraph is read before a left-column
one. There we reorder: full-width blocks (title, wide figures) by height, and between them
the left column top to bottom, then the right column, then footnotes. Then we repair the
joins: a paragraph continuing onto the next page is the last one in the right column, and a
paragraph split at the column break (no sentence end, next part starts lowercase) is joined.
"""

from dataclasses import dataclass

from docling_core.types.doc import DocItem, DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel

from paper2md.layout import Box, box_of, ends_sentence, move_parts

SKIP = {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
PARAGRAPH = 100  # characters: shorter text doesn't count as evidence of a column layout
GUTTER = 20  # points: how far past the page's middle a column item may reach


@dataclass
class Entry:
    slot: int  # position in doc.body.children
    item: DocItem
    box: Box  # where the item starts on this page
    column: str  # "full", "left" or "right"


def page_entries(doc: DoclingDocument, page_no: int) -> list[Entry]:
    """Top-level items that start on this page, with their column."""
    width = doc.pages[page_no].size.width
    entries = []
    for slot, ref in enumerate(doc.body.children):
        item = ref.resolve(doc)
        prov = first_prov_of(doc, item)
        if prov is None or prov.page_no != page_no or item.label in SKIP:
            continue
        box = box_of(prov, doc)
        if box.l < width / 2 - GUTTER and box.r > width / 2 + GUTTER:
            column = "full"
        else:
            column = "left" if box.r <= width / 2 + GUTTER else "right"
        entries.append(Entry(slot, item, box, column))
    return entries


def first_prov_of(doc: DoclingDocument, item) -> ProvenanceItem | None:
    """The item's first location; for a group (e.g. a list), its first child's."""
    provs = list(getattr(item, "prov", []))
    if not provs:
        for child in getattr(item, "children", []):
            provs += getattr(child.resolve(doc), "prov", [])
    return min(provs, key=lambda p: (p.page_no, p.charspan[0])) if provs else None


def is_paragraph(entry: Entry) -> bool:
    return entry.item.label == DocItemLabel.TEXT and len(getattr(entry.item, "text", "")) >= PARAGRAPH


def needs_fixing(entries: list[Entry]) -> bool:
    """Two-column page on which a right-column paragraph is read before a left-column one."""
    paragraphs = [e for e in entries if is_paragraph(e)]
    left = [i for i, e in enumerate(paragraphs) if e.column == "left"]
    right = [i for i, e in enumerate(paragraphs) if e.column == "right"]
    return len(left) >= 2 and len(right) >= 2 and min(right) < max(left)


def column_order(entries: list[Entry]) -> list[Entry]:
    full_tops = sorted(e.box.t for e in entries if e.column == "full")

    def key(entry: Entry):
        if entry.column == "full":
            return (full_tops.index(entry.box.t) + 1, 0, entry.box.t)
        section = sum(1 for top in full_tops if top <= entry.box.t)
        rank = 3 if entry.item.label == DocItemLabel.FOOTNOTE else (1 if entry.column == "left" else 2)
        return (section, rank, entry.box.t)

    return sorted(entries, key=key)


def fix_reading_order(doc: DoclingDocument) -> list[int]:
    """Reorder two-column pages that Docling read right-before-left. Returns the pages fixed."""
    fixed = []
    for page_no in sorted(doc.pages):
        entries = page_entries(doc, page_no)
        if not needs_fixing(entries):
            continue
        ordered = column_order(entries)
        slots = sorted(e.slot for e in entries)
        refs = {e.slot: doc.body.children[e.slot] for e in entries}
        for slot, entry in zip(slots, ordered):
            doc.body.children[slot] = refs[entry.slot]
        fixed.append(page_no)

        texts = [e for e in ordered if e.item.label == DocItemLabel.TEXT]
        # 1. The paragraph that continues onto the next page is the page's last one.
        if texts:
            last = texts[-1].item
            for entry in texts[:-1]:
                later = [p for p in entry.item.prov if p.page_no > page_no]
                if later and not any(p.page_no > page_no for p in last.prov):
                    move_parts(entry.item, last, later)
        # 2. Rejoin a paragraph split at the column break.
        left = [e for e in texts if e.column == "left"]
        right = [e for e in texts if e.column == "right"]
        if left and right:
            end, start = left[-1].item, right[0].item
            if not ends_sentence(end.text) and start.text[:1].islower() and all(p.page_no == page_no for p in end.prov):
                move_parts(start, end, list(start.prov))
                doc.delete_items(node_items=[start])
    return fixed
