"""The information block at the top of paper.md: title, authors, source, pages, how it was made.

It lets Claude cite a paper properly ("He et al., arXiv:1512.03385, p. 6") without hunting for
the title, and tells it how to read the file even when it's uploaded without the read-paper
skill. For arXiv papers the title, authors and date come from arXiv's API, which is exact;
detecting authors on a PDF's title page isn't reliable, so other PDFs get only the title
Docling found.
"""

import json
import urllib.request
import xml.etree.ElementTree as ElementTree
from datetime import date
from importlib.metadata import version
from pathlib import Path

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from paper2md.arxiv import USER_AGENT, parse_arxiv_id

ATOM = "{http://www.w3.org/2005/Atom}"
READING_NOTES = (
    "[p. N] marks where page N starts. Figures, equations and tables are files in the "
    "figures/, equations/ and tables/ folders next to this file; open an image when the "
    "question depends on it. x^{2} and x_{i} are super- and subscripts."
)


def arxiv_id_for(pdf: Path) -> str | None:
    """The arXiv ID a PDF was saved under ("1512.03385.pdf", "hep-th_9901001.pdf"), if any."""
    return parse_arxiv_id(pdf.stem) or parse_arxiv_id(pdf.stem.replace("_", "/", 1))


def parse_arxiv_entry(atom_xml: bytes) -> dict | None:
    """Title, authors and publication date from an arXiv API response; None if it has no entry."""
    entry = ElementTree.fromstring(atom_xml).find(f"{ATOM}entry")
    if entry is None or entry.find(f"{ATOM}title") is None:
        return None
    return {
        "title": " ".join(entry.findtext(f"{ATOM}title", "").split()),  # titles contain line breaks
        "authors": [" ".join(a.findtext(f"{ATOM}name", "").split()) for a in entry.findall(f"{ATOM}author")],
        "published": entry.findtext(f"{ATOM}published", "")[:10],
    }


def fetch_arxiv_metadata(arxiv_id: str) -> dict | None:
    """Ask arXiv's API about the paper; None without internet or for an unknown ID."""
    request = urllib.request.Request(
        f"https://export.arxiv.org/api/query?id_list={arxiv_id}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return parse_arxiv_entry(response.read())
    except (OSError, ElementTree.ParseError):
        return None


def detected_title(doc: DoclingDocument) -> str | None:
    """The paper's title as Docling found it: an item labelled title, else the first heading."""
    for label in (DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER):
        for item, _level in doc.iterate_items():
            if item.label == label and item.text.strip():
                return item.text.strip()
    return None


def front_matter(fields: dict) -> str:
    """A YAML block ("front matter") for the top of a Markdown file. Values are written as JSON,
    which is also valid YAML and safely quotes titles with colons ("Llama 2: Open ...")."""
    lines = ["---"]
    lines += [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items() if value]
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def information_block(doc: DoclingDocument, pdf: Path, formulas: bool) -> str:
    arxiv_id = arxiv_id_for(pdf)
    arxiv = fetch_arxiv_metadata(arxiv_id) if arxiv_id else None
    fields = {
        "title": arxiv["title"] if arxiv else detected_title(doc),
        "authors": arxiv["authors"] if arxiv else None,
        "published": arxiv["published"] if arxiv else None,
        "source": f"arXiv:{arxiv_id}" if arxiv_id else pdf.name,
        "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None,
        "pages": doc.num_pages(),
        "converted": f"{date.today().isoformat()} with paper2md {version('paper2md')}",
        "equations": "LaTeX, with an image after each" if formulas else "images (equations/ folder)",
        "notes": READING_NOTES,
    }
    return front_matter(fields)
