"""Page geometry, document-tree and text-moving helpers shared by several modules."""

from typing import NamedTuple

from docling_core.types.doc import DoclingDocument, FloatingItem, ProvenanceItem, TextItem
from docling_core.types.doc.labels import DocItemLabel


class Box(NamedTuple):
    """A rectangle in PDF points, measured from the top-left corner of the page."""

    l: float
    t: float
    r: float
    b: float

    def union(self, other: "Box") -> "Box":
        return Box(min(self.l, other.l), min(self.t, other.t), max(self.r, other.r), max(self.b, other.b))

    def grow(self, margin: float) -> "Box":
        return Box(self.l - margin, self.t - margin, self.r + margin, self.b + margin)

    def overlaps(self, other: "Box") -> bool:
        return self.l < other.r and other.l < self.r and self.t < other.b and other.t < self.b


def box_of(prov: ProvenanceItem, doc: DoclingDocument) -> Box:
    bbox = prov.bbox.to_top_left_origin(doc.pages[prov.page_no].size.height)
    return Box(bbox.l, bbox.t, bbox.r, bbox.b)


def attach_caption(doc: DoclingDocument, owner: FloatingItem, caption: TextItem) -> None:
    """Make `caption` belong to `owner` (a figure or table) only, detaching it from wherever Docling put it.

    The Markdown export prints a caption together with the item it belongs to, and prints
    it again as ordinary text if it is also left in the body, so it must have one owner.
    """
    ref = caption.get_ref()
    old_parent = caption.parent.resolve(doc)
    old_parent.children = [c for c in old_parent.children if c.cref != ref.cref]
    for item in [*doc.pictures, *doc.tables]:
        item.captions = [c for c in item.captions if c.cref != ref.cref]
    caption.parent = owner.get_ref()
    caption.label = DocItemLabel.CAPTION  # it may have been labelled as plain text
    owner.children.append(ref)
    owner.captions = [ref]


def move_parts(source: TextItem, target: TextItem, parts: list[ProvenanceItem]) -> None:
    """Move the text of `parts` (locations of `source`) to the end of `target`."""
    pieces = []
    for prov in sorted(parts, key=lambda p: p.charspan[0], reverse=True):
        start, end = prov.charspan
        pieces.insert(0, (source.text[start:end].strip(), prov))
        source.text = (source.text[:start].rstrip() + " " + source.text[end:].lstrip()).strip()
    source.prov = [p for p in source.prov if all(p is not q for q in parts)]
    for text, prov in pieces:
        start = len(target.text) + 1
        target.text = f"{target.text} {text}"
        prov.charspan = (start, start + len(text))
        target.prov.append(prov)


def ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "?", "!", ":"))


CAPTION_GAP = 6.0  # points between a caption and a continuation line below it


def continue_caption(doc: DoclingDocument, caption: TextItem) -> bool:
    """Join a caption's continuation that Docling split off as a separate text block.

    Scaling Laws' Figure 2 caption ends "...from 10^3 to 10^9" and its next line,
    "parameters (excluding embeddings).", came out as a paragraph of its own. A block counts
    as the continuation when it starts right under the caption at the same left edge, the
    caption doesn't end a sentence, and the block starts lowercase.
    """
    if ends_sentence(caption.text) or not caption.prov:
        return False
    below = box_of(max(caption.prov, key=lambda p: p.charspan[1]), doc)
    page_no = max(caption.prov, key=lambda p: p.charspan[1]).page_no
    for item in doc.texts:
        if item.label != DocItemLabel.TEXT or len(item.prov) != 1 or item.prov[0].page_no != page_no:
            continue
        box = box_of(item.prov[0], doc)
        if 0 <= box.t - below.b <= CAPTION_GAP and abs(box.l - below.l) <= 2 and item.text[:1].islower():
            move_parts(item, caption, list(item.prov))
            doc.delete_items(node_items=[item])
            return True
    return False
