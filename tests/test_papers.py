"""End-to-end tests: run paper2md on real papers and check what we verified by hand.

Each paper is converted once per test run (see conftest.py). Skip these with -m "not slow".
"""

import re

import pytest
from PIL import Image

pytestmark = pytest.mark.slow

RESNET, ATTENTION, SCALING_LAWS, SAFETY = "1512.03385", "1706.03762", "2001.08361", "1606.06565"
FIGURE_COUNTS = {RESNET: 7, ATTENTION: 5, SCALING_LAWS: 24}


def markdown(folder):
    return (folder / "paper.md").read_text(encoding="utf-8")


# --- figures ----------------------------------------------------------------------------

@pytest.mark.parametrize("paper", FIGURE_COUNTS)
def test_every_figure_is_saved_and_linked_right_after_its_own_caption(convert, paper):
    folder = convert(paper)
    count = FIGURE_COUNTS[paper]
    assert sorted(p.name for p in (folder / "figures").iterdir()) == [f"figure-{n:02d}.png" for n in range(1, count + 1)]

    lines = [line for line in markdown(folder).splitlines() if line.strip()]
    for index, line in enumerate(lines):
        link = re.fullmatch(r"!\[Image\]\(figures/figure-(\d+)\.png\)", line)
        if link:
            caption = re.match(r"Figure (\d+)", lines[index - 1])
            assert caption and int(caption.group(1)) == int(link.group(1)), f"wrong caption before {line}"
    captions = re.findall(r"^Figure (\d+)[.:\s]", markdown(folder), flags=re.MULTILINE)
    assert sorted(map(int, captions)) == list(range(1, count + 1)), "each caption exactly once"


def test_axis_labels_do_not_leak_into_the_text(convert):
    assert "iter. (1e4)" not in markdown(convert(RESNET))


def test_partly_detected_chart_is_not_blank(convert):
    # Docling's default renderer drew Scaling Laws' Figure 2 almost blank; we crop from pdfium.
    # Share of darker-than-light-grey pixels: 9.5% for our crop, 1.1% for Docling's blank render.
    image = Image.open(convert(SCALING_LAWS) / "figures" / "figure-02.png").convert("L")
    ink = sum(image.histogram()[:200]) / (image.width * image.height)
    assert ink > 0.05, f"only {ink:.1%} of Figure 2 is drawn"


# --- tables -----------------------------------------------------------------------------

def test_tables_are_saved_by_number_with_correct_values(convert):
    tables = convert(RESNET) / "tables"
    names = sorted(p.name for p in tables.iterdir())
    assert names == [f"table-{n:02d}.csv" for n in range(1, 15)] + ["untitled-table-01.csv"]
    table_2 = (tables / "table-02.csv").read_text(encoding="utf-8")
    assert "27.94" in table_2 and "25.03" in table_2  # values checked against the PDF


def test_row_group_label_is_repeated_on_each_row_of_its_group(convert):
    lines = (convert(ATTENTION) / "tables" / "table-03.csv").read_text(encoding="utf-8").splitlines()
    first_column = [line.split(",")[0] for line in lines[1:]]
    assert first_column[:9] == ["base", "(A)", "(A)", "(A)", "(A)", "(B)", "(B)", "(C)", "(C)"]
    # Blanks in other columns mean "same as base" and must stay blank.
    assert lines[2].split(",")[1] == ""


def test_title_block_and_table_of_contents_are_not_tables(convert):
    assert not list((convert(SAFETY) / "tables").iterdir())  # only "table" was the author grid
    assert ". . . ." not in markdown(convert(SCALING_LAWS))  # list of figures/tables removed


# --- superscripts and subscripts --------------------------------------------------------

def test_superscripts_in_text_and_tables(convert):
    attention = convert(ATTENTION)
    assert "10^{-9}" in markdown(attention)
    header = (attention / "tables" / "table-03.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "d_{model}" in header and "×10^{6}" in header
    assert "8.8×10^{13}" in (convert(SCALING_LAWS) / "tables" / "table-05.csv").read_text(encoding="utf-8")
    assert "error^{3}" in markdown(convert(RESNET))  # footnote marker


def test_underscores_are_not_escaped(convert):
    assert "\\_" not in markdown(convert(ATTENTION))


# --- page markers -----------------------------------------------------------------------

@pytest.mark.parametrize("paper, pages", [(RESNET, 12), (SAFETY, 29)])
def test_every_page_is_marked_in_order(convert, paper, pages):
    found = [int(n) for n in re.findall(r"\[p\. (\d+)\]", markdown(convert(paper)))]
    first_seen = list(dict.fromkeys(found))  # each page's first marker, in order of appearance
    assert first_seen == list(range(1, pages + 1))
    assert all(a != b for a, b in zip(found, found[1:])), "no page marked twice in a row"


def test_footnote_read_after_the_next_page_keeps_its_own_page(convert):
    # Docling reads ResNet's page-7 footnote after page 8 has started.
    text = markdown(convert(RESNET))
    footnote = text.index("With an initial learning rate of 0.1")
    markers_before = re.findall(r"\[p\. (\d+)\]", text[:footnote])
    assert markers_before[-1] == "7"


# --- equations (the slowest test: loads the formula model) --------------------------------

def test_equations_become_latex(convert):
    text = markdown(convert(RESNET, formulas=True))
    assert text.count("$$") == 2 * 2  # ResNet's two display equations, each wrapped in $$...$$
    assert "formula-not-decoded" not in text
