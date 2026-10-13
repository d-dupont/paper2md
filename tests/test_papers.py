"""End-to-end tests: run paper2md on real papers and check what we verified by hand.

Each paper is converted once per test run (see conftest.py). Skip these with -m "not slow".
"""

import re

import pytest
from PIL import Image

from paper2md.arxiv import download, pdf_path
from paper2md.cli import run

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


def test_panel_titles_belong_to_the_figure_and_captions_are_whole(convert):
    text = markdown(convert(SCALING_LAWS))
    # Titles printed above Figure 2's panels are inside the image, not loose in the text.
    assert "Larger models require fewer samples" not in text
    assert "optimal model size grows smoothly" not in text
    # The caption's second line, split off by Docling, is joined back on.
    assert "ranging in size from 10^{3} to 10^{9} parameters (excluding embeddings)." in text


def test_partly_detected_chart_is_not_blank(convert):
    # Docling's default renderer drew Scaling Laws' Figure 2 almost blank; we crop from pdfium.
    # Share of darker-than-light-grey pixels: 9.5% for our crop, 1.1% for Docling's blank render.
    image = Image.open(convert(SCALING_LAWS) / "figures" / "figure-02.png").convert("L")
    ink = sum(image.histogram()[:200]) / (image.width * image.height)
    assert ink > 0.05, f"only {ink:.1%} of Figure 2 is drawn"


# --- reading order ----------------------------------------------------------------------

def test_two_column_first_page_reads_left_column_first(convert):
    text = markdown(convert(RESNET))
    assert text.index("## Abstract") < text.index("## 1. Introduction") < text.index("Figure 1. Training error")
    # Paragraphs Docling joined using its wrong order are joined correctly again.
    assert "tasks [8, 12, 7, 32, 27] have also greatly benefited from very deep models." in text
    assert "unable to find solutions that [p. 2] are comparably good" in text


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


def test_paper_starts_with_an_information_block(convert):
    text = markdown(convert(RESNET))
    assert text.startswith('---\ntitle: "Deep Residual Learning for Image Recognition"\n')
    assert 'source: "arXiv:1512.03385"' in text.split("\n---\n")[0]
    assert "pages: 12" in text.split("\n---\n")[0]


def test_less_than_and_ampersand_are_written_plainly(convert):
    text = markdown(convert(RESNET))
    assert "(<90% error)" in text
    assert "&lt;" not in text and "&amp;" not in text


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

def test_equations_are_saved_as_images_by_default(convert):
    folder = convert(RESNET)
    assert sorted(p.name for p in (folder / "equations").iterdir()) == ["equation-01.png", "equation-02.png"]
    text = markdown(folder)
    assert "![Equation](equations/equation-01.png)" in text
    assert "formula-not-decoded" not in text


def test_equations_become_latex_with_formulas(convert):
    text = markdown(convert(RESNET, formulas=True))
    assert text.count("$$") == 2 * 2  # ResNet's two display equations, each wrapped in $$...$$
    assert "formula-not-decoded" not in text
    # The image follows the LaTeX, to check it against (the model occasionally errs).
    latex_end = text.index("$$", text.index("$$") + 2)
    assert text.index("![Equation](equations/equation-01.png)") > latex_end


# --- arXiv download ---------------------------------------------------------------------------

def test_arxiv_paper_is_downloaded_next_to_its_conversion(tmp_path):
    try:
        path = download("1706.03762", tmp_path)
    except OSError as error:
        pytest.skip(f"no connection to arXiv: {error}")
    assert path == pdf_path("1706.03762", tmp_path) == tmp_path / "1706.03762" / "1706.03762.pdf"
    assert path.read_bytes()[:4] == b"%PDF"


# --- line-numbered bills ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bill(tmp_path_factory):
    from conftest import BILL, bill_sample

    out = tmp_path_factory.mktemp("bill")
    run([str(bill_sample()), "--out", str(out)])
    return (out / BILL / "paper.md").read_text(encoding="utf-8")


def test_bill_text_has_no_line_numbers_headers_or_stamps(bill):
    for garbled in ("non8", "Account5", "18019", "Representa1", "mathe14"):
        assert garbled not in bill
    for stamp in ("VerDate", "PROD with", "•S 3312", "Æ"):  # Æ: the end-of-bill ornament
        assert stamp not in bill
    # Quotes copied from the PDF, verified by eye against the printed pages:
    assert "during the most recent 180-day period, did not employ more than 500 employees;" in bill
    assert "a social network site, video sharing service, search engine, and content aggregation service." in bill
    assert "Artificial Intelligence Research, Innovation, and Accountability Act of 2023" in bill
    assert "high-impact artificial intelligence systems" in bill  # hyphen kept: it's part of the word
    assert "House of Representatives of the United States" in bill  # hyphen dropped: a line break
    assert "Mr. LUJÁN" in bill  # the PDF prints the accent after its letter: "LUJA´N"


def test_bill_sections_paragraphs_and_pages(bill):
    assert "\n## SEC. 201. DEFINITIONS.\n" in bill
    assert "\n## TITLE I—ARTIFICIAL INTELLIGENCE RESEARCH AND INNOVATION\n" in bill
    assert "\n(4) COVERED INTERNET PLATFORM.—\n" in bill
    assert re.findall(r"\[p\. (\d+)\]", bill) == [str(n) for n in range(1, 59)]
    assert 'title: "Artificial Intelligence Research, Innovation, and Accountability Act of 2023"' in bill
    assert 'bill: "S. 3312, 118th Congress"' in bill


def test_turned_back_cover_reads_line_by_line():
    # S. Con. Res. 7 (reported, 118th Congress): its back cover is printed turned 90 degrees.
    from conftest import bill_sample
    from paper2md.bills import read_pages

    cover = [line.text for line in read_pages(bill_sample("BILLS-118sconres7rs"))[-1]]
    assert cover[:4] == ["Calendar No. 52", "118TH CONGRESS", "1ST SESSION S. CON. RES. 7", "CONCURRENT RESOLUTION"]
    # The title is what came out scrambled ("... arbitrary detenin Russia. racy, the rule ...").
    assert cover[4:9] == ["Condemning Russia’s unjust and arbitrary deten￾",
                          "tion of Russian opposition leader Vladimir Kara￾",
                          "Murza who has stood up in defense of democ￾",
                          "racy, the rule of law, and free and fair elections",
                          "in Russia."]
    assert cover[-2:] == ["Reported with an amendment and an amendment to the", "preamble"]


def convert_resolution(tmp_path_factory, package: str) -> str:
    from conftest import bill_sample

    out = tmp_path_factory.mktemp(package)
    run([str(bill_sample(package)), "--out", str(out)])
    return (out / package / "paper.md").read_text(encoding="utf-8")


def test_resolution_is_read_as_printed(tmp_path_factory):
    # H. Res. 684 numbers only the lines of its Resolved clause, so it used to go to Docling,
    # which kept those numbers ("con1", "demns ... 2"), split "self-defense" at the page break
    # into two list items, and titled it "1ST SESSION H. RES. 684".
    from conftest import RESOLUTION

    text = convert_resolution(tmp_path_factory, RESOLUTION)
    for stamp in ("VerDate", "PROD with", "Æ", "HRES 684 IH"):
        assert stamp not in text
    assert 'title: "Condemning the actions of Governor of New Mexico, Michelle Lujan Grisham, for' in text
    assert 'bill: "H. Res. 684, 118th Congress"' in text
    # Quotes copied from the PDF: each clause its own paragraph, the page break inside one.
    assert "\n\nWhereas the Second Amendment to the Constitution states that the citizens right to bear arms " \
           "shall not be infringed;\n\n" in text
    assert "the Supreme Court reaffirmed that ‘‘[s]elf-defense [p. 3] is a basic right" in text
    assert "\n\nResolved, That the House of Representatives condemns the actions of Governor Michelle Lujan " in text
    assert re.findall(r"\[p\. (\d+)\]", text) == ["1", "2", "3"]


def test_reported_resolution_keeps_its_pages_in_order(tmp_path_factory):
    # S. Con. Res. 7 (reported): Docling put page 10's text under the marker for page 8.
    text = convert_resolution(tmp_path_factory, "BILLS-118sconres7rs")
    assert "Mr. Kara-Murza’s defiant stance in [p. 10] front of the Arizona House of Representatives" in text
    assert re.findall(r"\[p\. (\d+)\]", text) == [str(n) for n in range(1, 13)]
    assert "has worked to further.\n\n[p. 11]\n\n[p. 12]\n\nCalendar No. 52\n\n" in text  # 11 is blank
    assert 'bill: "S. Con. Res. 7, 118th Congress"' in text


@pytest.mark.parametrize("paper", [RESNET, SAFETY, "1706.03762", "2001.08361", "1412.6980"])
def test_papers_are_not_mistaken_for_bills(paper):
    from conftest import sample
    from paper2md.bills import is_line_numbered, read_pages

    assert not is_line_numbered(read_pages(sample(paper)))
