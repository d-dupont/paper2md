"""Saves each display equation as an image and links it where the equation was.

Converting equations to LaTeX takes the formula model about 20 s each, so it's optional
(--formulas). Without it Docling leaves only "<!-- formula-not-decoded -->". Instead we crop
every equation from the page and link it, so Claude can open the image when the math
matters (an equation image costs ~200-250 tokens, and only when it is opened). With
--formulas the LaTeX stays and the image link follows it, to check the LaTeX against.
"""

from pathlib import Path

import pypdfium2
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from paper2md.figures import PADDING, RENDER_SCALE
from paper2md.layout import box_of


def save_equations(doc: DoclingDocument, pdf: Path, paper_dir: Path) -> list[Path]:
    """Save equations as `paper_dir/equations/equation-NN.png` and link them. Returns the paths.

    Run after page markers: unconverted equations are replaced by a link without a page
    location, and the markers must see where each page starts.
    """
    equations_dir = paper_dir / "equations"
    equations_dir.mkdir(parents=True, exist_ok=True)
    for old in equations_dir.glob("equation-*.png"):  # leftovers from a previous run
        old.unlink()

    formulas = [item for item, _level in doc.iterate_items() if item.label == DocItemLabel.FORMULA and item.prov]
    pdf_document = pypdfium2.PdfDocument(pdf)
    page_images = {}  # page number -> rendered page, so each page is rendered only once
    saved, unconverted = [], []
    for number, formula in enumerate(formulas, start=1):
        prov = formula.prov[0]
        if prov.page_no not in page_images:
            page_images[prov.page_no] = pdf_document[prov.page_no - 1].render(scale=RENDER_SCALE).to_pil()
        box = box_of(prov, doc).grow(PADDING)
        image = page_images[prov.page_no].crop(tuple(round(v * RENDER_SCALE) for v in box))
        relative = Path("equations") / f"equation-{number:02d}.png"
        image.save(paper_dir / relative)
        saved.append(paper_dir / relative)

        doc.insert_text(sibling=formula, label=DocItemLabel.TEXT, text=f"![Equation]({relative.as_posix()})")
        if not formula.text.strip():  # not converted: the link takes the placeholder's place
            unconverted.append(formula)
    pdf_document.close()
    if unconverted:
        doc.delete_items(node_items=unconverted)
    return saved
