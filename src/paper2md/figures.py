"""Saves each figure Docling detected as a PNG and records it for the Markdown links."""

from pathlib import Path

from docling_core.types.doc import DoclingDocument


def save_figures(doc: DoclingDocument, paper_dir: Path) -> list[tuple[Path, str]]:
    """Save figures to `paper_dir/figures/figure-NN.png`. Returns (path, caption) pairs."""
    figures_dir = paper_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    # Remove figures from a previous run so a re-run never leaves stale files behind.
    for old in figures_dir.glob("figure-*.png"):
        old.unlink()

    saved = []
    for number, picture in enumerate(doc.pictures, start=1):
        image = picture.get_image(doc)
        if image is None or picture.image is None:
            continue
        relative = Path("figures") / f"figure-{number:02d}.png"
        image.save(paper_dir / relative)
        # export_to_markdown() writes ![Image](uri), so point the uri at our file.
        picture.image.uri = relative
        saved.append((paper_dir / relative, picture.caption_text(doc)))
    return saved
