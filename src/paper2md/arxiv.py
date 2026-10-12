"""Accepts an arXiv ID or link instead of a PDF path, and downloads the PDF.

All of these name the same paper: "2307.09288", "arXiv:2307.09288", "2307.09288v2" (a
specific version), "https://arxiv.org/abs/2307.09288", "https://arxiv.org/pdf/2307.09288".
Papers from before 2007 have IDs like "hep-th/9901001".
"""

import re
import urllib.error
import urllib.request
from pathlib import Path

ARXIV_ID = re.compile(
    r"^(?:arxiv:)?"
    r"(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf|html)/)?"
    r"(?P<id>\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)"
    r"(?:\.pdf)?/?$",
    re.IGNORECASE,
)
# arXiv asks automated clients to identify themselves.
USER_AGENT = "paper2md (personal research tool; https://github.com/d-dupont/paper2md)"


def parse_arxiv_id(text: str) -> str | None:
    """The arXiv ID in `text`, or None if it isn't an arXiv ID or link."""
    match = ARXIV_ID.match(text.strip())
    return match.group("id") if match else None


def folder_name(arxiv_id: str) -> str:
    """A file-safe name: old-style IDs contain a slash ("hep-th/9901001" -> "hep-th_9901001")."""
    return arxiv_id.replace("/", "_")


def pdf_path(arxiv_id: str, out: Path) -> Path:
    """Where the paper's PDF is stored: `out/<id>/<id>.pdf`, next to its conversion."""
    name = folder_name(arxiv_id)
    return out / name / f"{name}.pdf"


def download(arxiv_id: str, out: Path) -> Path:
    """Download the paper to pdf_path() and return that path.

    Raises OSError (e.g. no internet, or no such paper) with a readable message.
    """
    request = urllib.request.Request(f"https://arxiv.org/pdf/{arxiv_id}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise OSError("no such paper on arXiv") from error
        raise
    if not data.startswith(b"%PDF"):
        raise OSError("arXiv did not return a PDF")
    path = pdf_path(arxiv_id, out)
    path.parent.mkdir(parents=True, exist_ok=True)  # only now, so a failed download leaves no folder
    path.write_bytes(data)
    return path
