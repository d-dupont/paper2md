"""Groups Docling's detected pictures into whole figures, crops them, and links their captions.

Docling's own figure handling has three weaknesses on academic papers:
- a figure made of side-by-side panels is often split into several pictures,
- the caption link is sometimes missing or attached to the wrong item,
- the crop can cut off axis labels, which then leak into the body text.

So we redo that part ourselves with rules based on how papers are laid out:
captions start with "Figure N" and sit next to (usually right below) their figure.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2
from docling_core.types.doc import DoclingDocument, ImageRef, PictureItem, ProvenanceItem, TextItem
from docling_core.types.doc.labels import DocItemLabel

from paper2md.layout import Box, attach_caption, box_of

FIGURE_CAPTION = re.compile(r"^\s*(?:figure|fig\.)\s*(\d+)", re.IGNORECASE)
PADDING = 4.0  # points (1/72 inch) of margin added around each crop
MAX_LABEL_CHARS = 40  # text this short touching a figure is treated as part of it (axis labels)
LABEL_GAP = 8.0  # points: how close a label must be to the figure to count as touching it
# Pages are rendered at 3x (216 dpi) so small text in figures stays legible. We render them
# with pdfium ourselves: Docling's own page images can miss parts of some vector charts.
RENDER_SCALE = 3.0
DANGLING_PAGE_MARKER = re.compile(r"\s*\[p\. [^\]]+\]\s*$")


@dataclass
class Figure:
    page_no: int
    caption: TextItem | None
    pictures: list[PictureItem] = field(default_factory=list)
    # Pieces of text that belong to the figure (axis labels). Docling keeps one ProvenanceItem
    # per place a text item appears; a paragraph merged across a page break has several.
    fragments: list[tuple[TextItem, ProvenanceItem]] = field(default_factory=list)

    @property
    def number(self) -> int | None:
        if self.caption is None:
            return None
        match = FIGURE_CAPTION.match(self.caption.text)
        return int(match.group(1)) if match else None


def find_caption(picture_box: Box, captions: list[tuple[TextItem, Box]]) -> TextItem | None:
    """Pick the figure caption closest below or beside the picture; fall back to one above."""
    best, best_gap = None, float("inf")
    for caption, box in captions:
        same_columns = box.l < picture_box.r and picture_box.l < box.r
        same_rows = box.t < picture_box.b and picture_box.t < box.b
        if same_columns and box.t >= picture_box.b - PADDING:  # below
            gap = box.t - picture_box.b
        elif same_rows:  # beside
            gap = max(box.l - picture_box.r, picture_box.l - box.r)
        else:
            continue
        if gap < best_gap:
            best, best_gap = caption, gap
    if best is not None:
        return best
    above = [(picture_box.t - box.b, c) for c, box in captions if box.b <= picture_box.t + PADDING]
    return min(above, key=lambda pair: pair[0])[1] if above else None


def figure_captions(doc: DoclingDocument) -> list[TextItem]:
    """Every "Figure N ..." caption in the document.

    Docling sometimes labels a caption as plain text. We accept such text as a caption
    only for figure numbers that have no properly labelled caption, so that a body
    sentence like "Figure 3 shows ..." is not mistaken for Figure 3's caption.
    """
    def number(item: TextItem) -> int | None:
        match = FIGURE_CAPTION.match(item.text)
        return int(match.group(1)) if match and item.prov else None

    labelled = [t for t in doc.texts if t.label == DocItemLabel.CAPTION and number(t) is not None]
    have_caption = {number(t) for t in labelled}
    unlabelled = [
        t for t in doc.texts
        if t.label == DocItemLabel.TEXT and number(t) is not None and number(t) not in have_caption
    ]
    return labelled + unlabelled


def group_figures(doc: DoclingDocument) -> list[Figure]:
    """Assign every picture to a figure: pictures sharing a caption become one figure."""
    all_captions = [(item, box_of(item.prov[0], doc)) for item in figure_captions(doc)]
    figures: dict[int, Figure] = {}  # keyed by id() of the caption, or of the picture if uncaptioned
    for picture in doc.pictures:
        page_no = picture.prov[0].page_no
        captions = [(item, box) for item, box in all_captions if item.prov[0].page_no == page_no]
        caption = find_caption(box_of(picture.prov[0], doc), captions)
        key = id(caption) if caption is not None else id(picture)
        figures.setdefault(key, Figure(page_no, caption)).pictures.append(picture)
    return list(figures.values())


def crop_box(figure: Figure, doc: DoclingDocument) -> Box:
    """The area to cut out: all panels plus touching short labels, with a margin."""
    box = box_of(figure.pictures[0].prov[0], doc)
    for picture in figure.pictures[1:]:
        box = box.union(box_of(picture.prov[0], doc))
    panels = box

    caption_box = box_of(figure.caption.prov[0], doc) if figure.caption is not None else None
    caption_below = caption_box is not None and caption_box.t >= panels.b - PADDING
    if caption_below:
        # Everything between a figure and its caption belongs to the figure. This also
        # recovers charts that the layout model only partly detected.
        box = box._replace(b=max(box.b, caption_box.t - PADDING))

    # Short text touching the figure is part of it (axis labels, legends). Repeat until
    # nothing new is added, because absorbing one label can bring the next within reach.
    candidates = [
        (item, prov)
        for item in doc.texts
        if item.label == DocItemLabel.TEXT
        for prov in item.prov
        if prov.page_no == figure.page_no and prov.charspan[1] - prov.charspan[0] <= MAX_LABEL_CHARS
    ]
    added = True
    while added:
        added = False
        for item, prov in candidates:
            label_box = box_of(prov, doc)
            if any(p is prov for _, p in figure.fragments) or not label_box.overlaps(box.grow(LABEL_GAP)):
                continue
            if caption_below and label_box.t >= caption_box.t:
                continue  # text below the caption is not part of the figure
            figure.fragments.append((item, prov))
            box = box.union(label_box)
            added = True

    padded = box.grow(PADDING)
    if caption_box is not None:
        if caption_below:
            # Keep a margin's distance from a caption below: its letters rise slightly above
            # its box. But never cut into the figure's own content.
            padded = padded._replace(b=min(padded.b, max(box.b, caption_box.t - PADDING)))
    page = doc.pages[figure.page_no].size
    return Box(max(padded.l, 0), max(padded.t, 0), min(padded.r, page.width), min(padded.b, page.height))


def remove_fragments(doc: DoclingDocument, fragments: list[tuple[TextItem, ProvenanceItem]]) -> None:
    """Delete text items that lie wholly inside figures; cut partial pieces out of the rest."""
    by_item: dict[int, tuple[TextItem, list[ProvenanceItem]]] = {}
    for item, prov in fragments:
        provs = by_item.setdefault(id(item), (item, []))[1]
        if all(p is not prov for p in provs):
            provs.append(prov)

    to_delete = []
    for item, provs in by_item.values():
        if len(provs) == len(item.prov):
            to_delete.append(item)
            continue
        # Cut from the end backwards so earlier character positions stay valid.
        for prov in sorted(provs, key=lambda p: p.charspan[0], reverse=True):
            start, end = prov.charspan
            item.text = item.text[:start].rstrip() + item.text[end:]
        # If the cut piece was a paragraph's part on the next page (e.g. an axis label Docling
        # glued on), the page marker pages.py put before it now points at nothing.
        item.text = DANGLING_PAGE_MARKER.sub("", item.text)
        item.prov = [p for p in item.prov if all(p is not q for q in provs)]
    if to_delete:
        doc.delete_items(node_items=to_delete)


def save_figures(doc: DoclingDocument, pdf: Path, paper_dir: Path) -> list[tuple[Path, str]]:
    """Save each figure as a PNG and update `doc` so the Markdown links image and caption.

    Captioned figures are named after their number (figure-04.png is "Figure 4");
    pictures without a caption are saved as image-NN.png. Returns (path, caption) pairs.
    """
    figures_dir = paper_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    # Remove images from a previous run so a re-run never leaves stale files behind.
    for old in [*figures_dir.glob("figure-*.png"), *figures_dir.glob("image-*.png")]:
        old.unlink()

    figures = group_figures(doc)
    claimed = {figure.caption.self_ref for figure in figures if figure.caption is not None}
    saved, used_names, extra_panels, fragments = [], set(), [], []
    uncaptioned = 0
    pdf_document = pypdfium2.PdfDocument(pdf)
    page_images = {}  # page number -> rendered page, so each page is rendered only once

    for figure in figures:
        if figure.number is not None:
            name = f"figure-{figure.number:02d}"
        else:
            uncaptioned += 1
            name = f"image-{uncaptioned:02d}"
        while name in used_names:  # e.g. a figure continued on the next page
            name += "b"
        used_names.add(name)

        if figure.page_no not in page_images:
            page = pdf_document[figure.page_no - 1]  # pdfium counts pages from 0, Docling from 1
            page_images[figure.page_no] = page.render(scale=RENDER_SCALE).to_pil()
        box = crop_box(figure, doc)
        image = page_images[figure.page_no].crop(tuple(round(v * RENDER_SCALE) for v in box))

        relative = Path("figures") / f"{name}.png"
        image.save(paper_dir / relative)

        # The first panel stands for the whole figure in the Markdown; the others are removed.
        main, *others = figure.pictures
        main.image = ImageRef.from_pil(image, dpi=round(72 * RENDER_SCALE))
        main.image.uri = relative  # export_to_markdown() writes ![Image](uri)
        if figure.caption is not None:
            attach_caption(doc, main, figure.caption)
        else:
            # Keep Docling's own caption link only if no figure claimed that caption.
            main.captions = [c for c in main.captions if c.cref not in claimed]
        extra_panels += others
        fragments += figure.fragments
        saved.append((paper_dir / relative, figure.caption.text if figure.caption else ""))

    pdf_document.close()
    remove_fragments(doc, fragments)
    if extra_panels:
        doc.delete_items(node_items=extra_panels)
    return saved
