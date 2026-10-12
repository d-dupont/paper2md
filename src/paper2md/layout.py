"""Page geometry and document-tree helpers shared by figures.py and tables.py."""

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
