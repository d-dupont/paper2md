"""Shared test setup: sample PDFs and a once-per-run conversion of each paper."""

import urllib.request
from pathlib import Path

import pytest

from paper2md.cli import run

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def sample(arxiv_id: str) -> Path:
    """Path to samples/<id>.pdf, downloading it from arXiv the first time.

    The PDFs are not committed (they are other people's papers), so a fresh checkout
    fetches them on demand. Without internet the test is skipped, not failed.
    """
    path = SAMPLES / f"{arxiv_id}.pdf"
    if not path.exists():
        SAMPLES.mkdir(exist_ok=True)
        try:
            urllib.request.urlretrieve(f"https://arxiv.org/pdf/{arxiv_id}", path)
        except OSError as error:
            path.unlink(missing_ok=True)
            pytest.skip(f"could not download sample {arxiv_id}: {error}")
    return path


BILL = "BILLS-118s3312is"  # S. 3312 (118th Congress), a line-numbered bill from GovInfo
RESOLUTION = "BILLS-118hres684ih"  # H. Res. 684 (118th Congress): no line numbers, read by Docling


def bill_sample(package: str = BILL) -> Path:
    """samples/<package>.pdf, downloaded from GovInfo the first time (skipped offline)."""
    path = SAMPLES / f"{package}.pdf"
    if not path.exists():
        SAMPLES.mkdir(exist_ok=True)
        try:
            urllib.request.urlretrieve(f"https://www.govinfo.gov/content/pkg/{package}/pdf/{package}.pdf", path)
        except OSError as error:
            path.unlink(missing_ok=True)
            pytest.skip(f"could not download {package}: {error}")
    return path


@pytest.fixture(scope="session")
def convert(tmp_path_factory):
    """convert("1512.03385") runs paper2md once per test run and returns the paper's output folder.

    Equations are skipped unless formulas=True, because the formula model takes minutes.
    """
    done: dict[tuple[str, bool], Path] = {}

    def _convert(arxiv_id: str, formulas: bool = False) -> Path:
        key = (arxiv_id, formulas)
        if key not in done:
            out = tmp_path_factory.mktemp(f"{arxiv_id}-{'formulas' if formulas else 'text'}")
            run([str(sample(arxiv_id)), "--out", str(out), "--formulas" if formulas else "--no-formulas"])
            done[key] = out / arxiv_id
        return done[key]

    return _convert
