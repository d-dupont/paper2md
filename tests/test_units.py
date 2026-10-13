"""Fast tests of single functions on small, hand-made inputs (no Docling run)."""

from pathlib import Path

import pytest
from docling_core.types.doc import BoundingBox, CoordOrigin, DoclingDocument, ProvenanceItem, Size
from docling_core.types.doc.labels import DocItemLabel

from paper2md.accents import join_accents, join_accents_after
from paper2md.arxiv import folder_name, parse_arxiv_id
from paper2md.bills import (Char, bill_blocks, bill_markdown, bill_number, bill_title, drop_stamps,
                            is_gpo_measure, is_line_numbered, is_stamp, page_lines, turned_lines)
from paper2md.cli import build_parser, run
from paper2md.convert import drop_invented_list_numbers, performance_cores
from paper2md.figures import find_caption
from paper2md.layout import Box
from paper2md.metadata import arxiv_id_for, front_matter, parse_arxiv_entry
from paper2md.reading_order import Entry, column_order
from paper2md.row_groups import find_groups
from paper2md.pages import mark_page_breaks_inside_text, page_name, printed_page_offset
from paper2md.superscripts import Run, locate, mark, normalize
from paper2md.tables import caption_candidates, column_names, nearest_caption, table_number


# --- layout.Box -----------------------------------------------------------------------

def test_box_union_grow_overlaps():
    a, b = Box(0, 0, 10, 10), Box(20, 5, 30, 15)
    assert a.union(b) == Box(0, 0, 30, 15)
    assert not a.overlaps(b)
    assert not a.grow(10).overlaps(b)  # touching edges is not overlapping
    assert a.grow(11).overlaps(b)


# --- figures: which caption belongs to a picture ----------------------------------------

def test_figure_takes_caption_below_not_the_one_further_down():
    # ResNet page 8: Figure 6 above its caption, Figure 7 below that, then Figure 7's caption.
    picture = Box(99, 72, 495, 171)
    captions = [("Figure 6", Box(50, 173, 545, 192)), ("Figure 7", Box(50, 329, 286, 370))]
    assert find_caption(picture, captions) == "Figure 6"


def test_figure_caption_beside_and_above_fallbacks():
    picture = Box(100, 100, 300, 200)
    assert find_caption(picture, [("side", Box(320, 120, 500, 180))]) == "side"
    assert find_caption(picture, [("above", Box(100, 50, 300, 90))]) == "above"
    assert find_caption(picture, []) is None


# --- tables -----------------------------------------------------------------------------

def test_table_caption_can_be_above_or_below():
    table = Box(100, 300, 400, 400)
    above = ("above", Box(100, 280, 400, 295))  # 5 points away
    below = ("below", Box(100, 420, 400, 440))  # 20 points away
    assert nearest_caption(table, [above, below]) == "above"
    assert nearest_caption(table, [below]) == "below"


def test_table_number_reads_only_real_table_captions():
    class Caption:
        def __init__(self, text):
            self.text = text

    assert table_number(Caption("Table 12. Results")) == 12
    assert table_number(Caption("Figure 4. Training")) is None
    assert table_number(None) is None


# --- superscripts: finding a run in Docling's text and marking it -------------------------

def test_normalize_unifies_minus_signs_and_spaces():
    assert normalize("10 −9") == normalize("10-9") == "10-9"


def test_superscript_and_subscript_are_marked():
    text = "Adam with β1 = 0.9 and ϵ = 10-9 . We varied"
    runs = [
        Run("_", "1", before="withβ", after="=0.9an", center=(0, 0)),
        Run("^", "−9", before="ϵ=10", after=".Wevar", center=(0, 0)),  # pdfium reports a real minus
    ]
    spans = [(*locate(text, r), r.kind) for r in runs]
    assert mark(text, spans) == "Adam with β_{1} = 0.9 and ϵ = 10^{-9} . We varied"


def test_ambiguous_run_is_left_alone():
    # "2" after "x" appears twice and there is no other context: better no mark than a wrong one.
    assert locate("x2 and x2", Run("^", "2", before="x", after="", center=(0, 0))) is None


def test_short_table_cell_matches_with_shorter_context():
    # Context from pdfium spills into the neighbouring cells; the cell is just "dmodel".
    run_ = Run("_", "model", before="ies.Nd", after="dffhdk", center=(0, 0))
    assert mark("dmodel", [(*locate("dmodel", run_), "_")]) == "d_{model}"


# --- pages: markers inside paragraphs that cross a page break ----------------------------

def two_page_paragraph(text: str, split: int) -> DoclingDocument:
    doc = DoclingDocument(name="test")
    for page_no in (1, 2):
        doc.add_page(page_no=page_no, size=Size(width=612, height=792))
    box = BoundingBox(l=50, t=700, r=300, b=650, coord_origin=CoordOrigin.BOTTOMLEFT)
    item = doc.add_text(
        label=DocItemLabel.TEXT, text=text,
        prov=ProvenanceItem(page_no=1, bbox=box, charspan=(0, split)),
    )
    item.prov.append(ProvenanceItem(page_no=2, bbox=box, charspan=(split, len(text))))
    return doc


def test_page_marker_inside_paragraph_and_positions_shifted():
    doc = two_page_paragraph("the plain net has higher error", split=18)
    assert mark_page_breaks_inside_text(doc, {1: "1", 2: "2"}) == 1
    item = doc.texts[0]
    assert item.text == "the plain net has [p. 2] higher error"
    # figures.py cuts text by these positions, so page 2's part must still point at its text.
    start, end = item.prov[1].charspan
    assert item.text[start:end].strip() == "higher error"


def test_page_marker_never_splits_a_word():
    # Docling's positions drift after rejoining "high-" + "way"; the marker moves to the next space.
    doc = two_page_paragraph("in addition highway networks", split=18)
    mark_page_breaks_inside_text(doc, {1: "2", 2: "3"})
    item = doc.texts[0]
    assert item.text == "in addition highway [p. 3] networks"
    start, end = item.prov[1].charspan
    assert item.text[start:end] == "networks"


def test_page_name_keeps_printed_label_and_position_when_they_differ():
    assert page_name("4567", 3) == "4567 | pdf 3"
    assert page_name("iv", 4) == "iv | pdf 4"
    assert page_name("3", 3) == "3"  # same number: no need to say it twice
    assert page_name(None, 5) == "5"  # no printed labels: position only
    assert page_name("  ", 6) == "6"


# --- command line -------------------------------------------------------------------------

def test_missing_file_is_a_clear_error(capsys):
    with pytest.raises(SystemExit) as stop:
        run(["no-such-paper.pdf"])
    assert stop.value.code == 2
    assert "file not found, and not an arXiv ID" in capsys.readouterr().err


def test_out_expands_a_leading_tilde():
    # PowerShell hands `~` to the program unchanged, where bash would already have replaced it.
    assert build_parser().parse_args(["p.pdf", "--out", "~/papers"]).out == Path.home() / "papers"


def test_input_path_expands_a_leading_tilde(tmp_path, monkeypatch, capsys):
    # Home is a temporary folder holding a non-PDF. Found via `~` -> "not a .pdf file";
    # not found (the bug) -> "file not found". Either way it stops before converting anything.
    monkeypatch.setenv("HOME", str(tmp_path))  # read by expanduser() on macOS and Linux
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # read by expanduser() on Windows
    (tmp_path / "notes.txt").write_text("not a paper")
    with pytest.raises(SystemExit):
        run(["~/notes.txt"])
    assert "not a .pdf file" in capsys.readouterr().err


def test_out_leaves_other_paths_alone():
    assert build_parser().parse_args(["p.pdf", "--out", "papers"]).out == Path("papers")


def test_performance_cores_is_a_positive_number():
    assert performance_cores() >= 1


# --- accents ------------------------------------------------------------------------------

@pytest.mark.parametrize("broken, fixed", [
    ("K.-R. M¨uller", "K.-R. Müller"),
    ("Javier Garc´ıa", "Javier García"),  # LaTeX's accent on a dotless i
    ("Tamer Ba¸sar", "Tamer Başar"),  # cedilla
    ("Mich`ele Basseville", "Michèle Basseville"),  # grave stored as a backtick
    ("batch size ˜B (L)", "batch size B̃ (L)"),  # math accent without a precomposed letter
    ("(√v_{t} + ˆ ϵ)", "(√v_{t} + ϵ̂)"),  # one space between accent and letter
    ("```\ncode\n```", "```\ncode\n```"),  # real backticks are left alone
    ("a ` quote", "a ` quote"),
])
def test_accents_are_joined_to_their_letter(broken, fixed):
    assert join_accents(broken) == fixed


# Bills print the accent after its letter. All from GovInfo PDFs (118th Congress).
@pytest.mark.parametrize("broken, fixed", [
    ("Mr. LUJA´N", "Mr. LUJÁN"),  # S. 3312: on "A", not "N" (join_accents would say LUJAŃ)
    ("Ms. VELA´ZQUEZ", "Ms. VELÁZQUEZ"),
    ("Don˜a Ana County", "Doña Ana County"),  # lowercase, tilde
    ("Rı´o Grande", "Río Grande"),  # accent on a dotless i
    ("HANAPE¯PE¯ RIVER", "HANAPĒPĒ RIVER"),  # macron, twice in a word
    ("Honoko¯wai", "Honokōwai"),
    ("a plain sentence.", "a plain sentence."),
])
def test_bill_accents_are_joined_to_the_letter_before(broken, fixed):
    assert join_accents_after(broken) == fixed


# --- row groups in tables -------------------------------------------------------------------

def test_group_label_spans_the_rows_between_two_lines():
    # Attention's Table 3, measured: lines between groups, row centres, first-column labels.
    rules = [129.9, 153.9, 166.5, 211.9, 235.4, 313.5]
    centers = {0: 142.4, 1: 160.8, 2: 173.5, 3: 184.4, 4: 194.4, 5: 206.2, 6: 218.9, 7: 228.7}
    labels = {1: "base", 4: "(A)", 7: "(B)"}
    assert find_groups(centers, rules, labels) == [(4, 2, 5), (7, 6, 7)]


def test_band_with_two_labels_is_not_a_group():
    rules = [0, 10, 50, 60]
    assert find_groups({1: 15, 2: 25, 3: 35}, rules, {1: "RPN", 3: "RPN+RCNN"}) == []


# --- reading order --------------------------------------------------------------------------

def test_column_order_reads_full_width_then_left_then_right_then_footnotes():
    class Item:
        def __init__(self, name, label=DocItemLabel.TEXT):
            self.name, self.label = name, label

    def entry(name, column, top, label=DocItemLabel.TEXT):
        return Entry(0, Item(name, label), Box(0, top, 0, top + 10), column)

    # Docling's order on ResNet's page 1, simplified: right column before left column.
    docling_order = [
        entry("title", "full", 107), entry("figure 1", "right", 224), entry("right text", "right", 378),
        entry("abstract", "left", 226), entry("intro", "left", 557),
        entry("footnote", "left", 696, DocItemLabel.FOOTNOTE),
    ]
    assert [e.item.name for e in column_order(docling_order)] == [
        "title", "abstract", "intro", "figure 1", "right text", "footnote",
    ]


def test_plain_text_table_caption_is_accepted_only_when_it_reads_like_one():
    class Text:
        def __init__(self, text, label=DocItemLabel.TEXT):
            self.text, self.label, self.prov = text, label, ["somewhere"]

    proper = Text("Table 1: Results.", DocItemLabel.CAPTION)
    unlabelled = Text("Table 5: SFT annotation example.")  # Llama 2: labelled as plain text
    sentence = Text("Table 8 shows that the reward model is accurate.")
    duplicate = Text("Table 1. Also looks like a caption.")  # Table 1 already has a real one
    found = caption_candidates([proper, unlabelled, sentence, duplicate])
    assert found == [proper, unlabelled]


# --- arXiv IDs ------------------------------------------------------------------------------

@pytest.mark.parametrize("text, arxiv_id", [
    ("2307.09288", "2307.09288"),
    ("2307.09288v2", "2307.09288v2"),
    ("arXiv:2307.09288", "2307.09288"),
    ("https://arxiv.org/abs/2307.09288", "2307.09288"),
    ("https://arxiv.org/pdf/2307.09288v3.pdf", "2307.09288v3"),
    ("http://www.arxiv.org/abs/1412.6980/", "1412.6980"),
    ("hep-th/9901001", "hep-th/9901001"),
    ("https://arxiv.org/abs/math.GT/0309136", "math.GT/0309136"),
    ("paper.pdf", None),
    ("https://example.com/2307.09288", None),
    ("12345", None),
])
def test_arxiv_ids_and_links_are_recognised(text, arxiv_id):
    assert parse_arxiv_id(text) == arxiv_id


def test_old_style_ids_become_safe_folder_names():
    assert folder_name("hep-th/9901001") == "hep-th_9901001"


def test_multi_row_headers_are_joined_with_a_slash():
    class Cell:
        def __init__(self, text, row, header=True):
            self.text, self.start_row_offset_idx, self.column_header = text, row, header

    # ResNet's Table 9: three header rows; "@[.5, .95]" itself contains dots.
    train, val = Cell("COCO train", 0), Cell("COCO val", 1)
    method = Cell("method", 0)  # one cell spanning two header rows: appears twice in the grid
    grid = [
        [method, train, train],
        [method, val, val],
        [Cell("", 2), Cell("@.5", 2), Cell("@[.5, .95]", 2)],
        [Cell("ResNet", 3, header=False), Cell("48.4", 3, header=False), Cell("27.2", 3, header=False)],
    ]
    assert column_names(grid) == ["method", "COCO train / COCO val / @.5", "COCO train / COCO val / @[.5, .95]"]
    assert column_names([[Cell("1", 0, header=False)]]) is None


# --- information block ----------------------------------------------------------------------

def test_arxiv_metadata_is_read_from_the_api_response():
    # Shortened from https://export.arxiv.org/api/query?id_list=1512.03385
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <id>http://arxiv.org/abs/1512.03385v1</id>
        <published>2015-12-10T19:51:55Z</published>
        <title>Deep Residual Learning for Image
          Recognition</title>
        <author><name>Kaiming He</name></author><author><name>Xiangyu Zhang</name></author>
    </entry></feed>"""
    assert parse_arxiv_entry(atom) == {
        "title": "Deep Residual Learning for Image Recognition",
        "authors": ["Kaiming He", "Xiangyu Zhang"],
        "published": "2015-12-10",
    }
    assert parse_arxiv_entry(b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>') is None  # unknown ID


def test_front_matter_quotes_titles_and_skips_empty_fields():
    block = front_matter({"title": "Llama 2: Open Models", "authors": ["A", "B"], "url": None, "pages": 77})
    assert block == '---\ntitle: "Llama 2: Open Models"\nauthors: ["A", "B"]\npages: 77\n---\n\n'


def test_arxiv_id_is_recognised_from_the_saved_file_name():
    assert arxiv_id_for(Path("~/papers/1512.03385/1512.03385.pdf")) == "1512.03385"
    assert arxiv_id_for(Path("hep-th_9901001.pdf")) == "hep-th/9901001"
    assert arxiv_id_for(Path("safety paper.pdf")) is None


# --- bills: line-numbered pages ----------------------------------------------------------------

# Two pages as pdfium returns them (abridged from S. 3312): page number and bill ID on top,
# line numbers first on each line, U+FFFE where a word breaks at a line end (pdfium leaves out
# the line break after it), printing-office stamps at the bottom.
BILL_PAGE_1 = (
    "11 \r\n•S 3312 IS\r\n"
    "1 (5) CRITICAL-IMPACT AI ORGANIZATION.—The \r\n"
    "2 term ‘‘critical-impact AI organization’’ means a non\ufffe3 government organization that serves as the deployer \r\n"
    "4 of a critical-impact artificial intelligence system. \r\n"
    "5 (6) HIGH-IMPACT SYSTEM.—The term ‘‘high\ufffe6 impact system’’ means a system \r\n"
    "7 used during the most recent 180- \r\n"
    "8 day period by a high-impact \r\n"
    "VerDate Sep 11 2014 01:21 Nov 22, 2023 Jkt 049200 PO 00000 Frm 00011 Fmt 6652 Sfmt 6201 E:\\BILLS\\S3312.IS S3312\r\n"
    "dmwilson on DSKJM0X7X2PROD with BILLS"
)
BILL_PAGE_2 = (
    "12 \r\n•S 3312 IS\r\n"
    "1 developer that has 500 employees. \r\n"
    "2 SEC. 202. GENERATIVE ARTIFICIAL INTELLIGENCE \r\n"
    "3 TRANSPARENCY. \r\n"
    "4 (a) IN GENERAL.—Each developer shall report. \r\n"
)


def test_bill_page_lines_drop_numbers_header_and_stamps():
    lines = page_lines(BILL_PAGE_1)
    assert all(line.numbered for line in lines)
    assert lines[0].text == "(5) CRITICAL-IMPACT AI ORGANIZATION.—The"
    assert lines[2].text == "government organization that serves as the deployer"  # its "3" removed
    assert not any("VerDate" in line.text or "PROD with" in line.text for line in lines)
    # A line starting with a number keeps it: only the line number goes.
    assert page_lines("1 500 employees; \r\n2 and")[0].text == "500 employees;"
    # Accents printed after their letter are joined to it.
    assert page_lines("1 Mr. WICKER, Mr. LUJA´N, and \r\n")[0].text == "Mr. WICKER, Mr. LUJÁN, and"


# The last page of H.R. 10243 (118th Congress), verbatim: the end-of-bill ornament comes out
# as "Æ", and this printing job signs its stamp "PROD with $$_JOB" instead of "... BILLS".
BILL_LAST_PAGE = (
    "3 \r\n•HR 10243 IH\r\n"
    "1 ‘‘(D) TERRITORY DEFINED.—In this para\ufffe2 graph, the term ‘territory’ means American \r\n"
    "3 Samoa, Guam, the Commonwealth of Puerto \r\n"
    "4 Rico, the Northern Mariana Islands, or the \r\n"
    "5 United States Virgin Islands.’’. \r\n"
    "Æ \r\n"
    "VerDate Sep 11 2014 01:10 Dec 28, 2024 Jkt 059200 PO 00000 Frm 00003 Fmt 6652 Sfmt 6301 "
    "E:\\BILLS\\H10243.IH H10243\r\n"
    "kjohnson on DSK7ZCZBW3PROD with $$_JOB"
)


def test_bill_end_mark_and_every_stamp_form_are_dropped():
    lines = [line.text for line in page_lines(BILL_LAST_PAGE)]
    assert lines[-1] == "United States Virgin Islands.’’."  # the bill's last words end the page
    assert not any("Æ" in line or "PROD with" in line or "VerDate" in line for line in lines)


HRES_684_STAMP = ("VerDate Sep 11 2014 22:13 Oct 05, 2023 Jkt 049200 PO 00000 Frm 00001 Fmt 6652 "
                  "Sfmt 6652 E:\\BILLS\\HR684.IH HR684")


def test_a_paragraph_is_a_stamp_only_if_all_of_it_is_one():
    # Whole stamps, as Docling gives them for H. Res. 684 (118th Congress):
    assert is_stamp(HRES_684_STAMP)
    assert is_stamp("kjohnson on DSK7ZCZBW3PROD with $$_JOB")
    assert is_stamp("•HR 684 IH") and is_stamp("Æ")
    # A stamp merged with real text is not one: deleting it would delete the text too.
    assert not is_stamp(HRES_684_STAMP + " Whereas the Second Amendment to the Constitution")
    assert not is_stamp("The Senate shall consider the stamp PROD with BILLS")
    assert not is_stamp("ÆSIR")


def test_drop_stamps_deletes_only_the_stamp_paragraphs():
    doc = DoclingDocument(name="test")
    for text in ("kjohnson on DSK7ZCZBW3PROD with $$_JOB", "Whereas the Second Amendment states;",
                 HRES_684_STAMP, "Æ"):
        doc.add_text(label=DocItemLabel.TEXT, text=text)
    assert drop_stamps(doc) == 3
    assert [item.text for item in doc.texts] == ["Whereas the Second Amendment states;"]


def test_bill_paragraphs_hyphens_and_page_markers():
    pages = [page_lines(BILL_PAGE_1), page_lines(BILL_PAGE_2)]
    text = bill_markdown(bill_blocks(pages, {1: "11", 2: "12"}))
    assert text.startswith("[p. 11]\n\n(5) CRITICAL-IMPACT AI ORGANIZATION.—The term")
    assert "means a nongovernment organization" in text   # break hyphen dropped
    assert "‘‘high-impact system’’" in text              # kept: "high-impact" occurs unbroken too
    assert "the most recent 180-day period" in text      # a real hyphen at a line end
    assert "\n\n(6) HIGH-IMPACT SYSTEM" in text          # each (a)/(1) starts a paragraph
    # The paragraph runs onto page 12, so the marker goes inside it; the heading on two
    # lines becomes one; (a) starts a new paragraph after it.
    assert "by a high-impact [p. 12] developer that has 500 employees." in text
    assert "\n\n## SEC. 202. GENERATIVE ARTIFICIAL INTELLIGENCE TRANSPARENCY.\n\n(a) IN GENERAL." in text


def test_a_year_in_brackets_starting_a_line_is_not_a_paragraph_label():
    # H. Res. 684: the case citation wraps so that a line starts with "(2008)".
    pages = [page_lines("1 Whereas in District of Columbia v. Heller, 554 U.S. 570, 595 \r\n"
                        "2 (2008), the Supreme Court confirmed that the right \r\n"
                        "3 (1) is individual. \r\n")]
    text = bill_markdown(bill_blocks(pages, {1: "2"}))
    assert "554 U.S. 570, 595 (2008), the Supreme Court confirmed" in text
    assert "\n\n(1) is individual." in text  # a real label still starts a paragraph


def test_no_space_is_added_after_a_dash_or_slash_ending_a_line():
    # H.R. 10520 and H. Res. 99 (118th Congress): the GPO prints neither with a space after it.
    pages = [page_lines("18 ‘‘(2) COORDINATION WITH STAKEHOLDERS.— \r\n19 The education and outreach program \r\n"
                        "20 (10) supports appropriate funding for HIV/ \r\n21 AIDS prevention, care, treatment \r\n")]
    text = bill_markdown(bill_blocks(pages, {1: "4"}))
    assert "‘‘(2) COORDINATION WITH STAKEHOLDERS.—The education and outreach program" in text
    assert "supports appropriate funding for HIV/AIDS prevention, care, treatment" in text


def test_text_after_a_blank_page_does_not_join_the_paragraph_before_it():
    # S. Con. Res. 7 (reported): page 11 is blank, page 12 is the back cover.
    pages = [page_lines("1 (5) calls on the President to work for \r\n2 a free Russia. \r\n"),
             [],
             page_lines("Calendar No. 52 \r\n118TH CONGRESS \r\n")]
    text = bill_markdown(bill_blocks(pages, {1: "10", 2: "11", 3: "12"}))
    assert "a free Russia.\n\n[p. 11]\n\n[p. 12]\n\nCalendar No. 52" in text


def turned(word: str, start: float, across: float) -> list[Char]:
    """`word` as characters of a turned line: 5 points per letter, font 10 points high."""
    return [Char(c, 90, start + 5 * k, start + 5 * (k + 1), across, 10.0) for k, c in enumerate(word)]


def test_turned_lines_follow_the_text_not_the_page():
    # Lines handed over out of order (pdfium's order on a turned page is scrambled).
    chars = turned("tion", 0, 20) + turned("Condemning", 0, 8) + turned("deten-", 55, 8)
    assert turned_lines(chars) == ["Condemning deten￾", "tion"]  # the break is marked
    # A hyphen after a digit stays: "180-day".
    assert turned_lines(turned("within", 0, 8) + turned("180-", 35, 8) + turned("day", 0, 20)) == [
        "within 180-", "day"]


COVER_684 = "118TH CONGRESS \r\n1ST SESSION H. RES. 684 \r\nCondemning the actions of Governor of New Mexico \r\n"


def test_gpo_bills_and_resolutions_are_recognized_by_cover_and_printing_marks():
    assert is_gpo_measure([COVER_684, "2 \r\n•HRES 684 IH\r\nWhereas, on September 8, 2023 \r\n"])
    assert is_gpo_measure([COVER_684, "Whereas ... \r\n" + HRES_684_STAMP])
    assert is_gpo_measure([COVER_684, "3 \r\nSRES 99 RS1S \r\nflict’’, and there are"])  # header, no bullet
    # The cover alone, or the marks alone, are not enough.
    assert not is_gpo_measure([COVER_684, "2 \r\nWhereas nothing printed here marks it"])
    assert not is_gpo_measure(["Abstract \r\nWe study 3 models.", "2 \r\n•HRES 684 IH\r\ntext"])
    # The Federal Register has the same kind of stamp, naming E:\FR\, and no such cover.
    assert not is_gpo_measure(["Presidential Documents \r\n75191 \r\nVerDate Sep 11 2014 18:29 Oct 31, 2023 "
                               "Jkt 262001 PO 00000 Frm 00001 Fmt 4705 Sfmt 4790 E:\\FR\\FM\\01NOD0.SGM 01NOD0"])


# A concurrent resolution, abridged from S. Con. Res. 7 (118th Congress): no line numbers until the
# Resolved clause, and the end of a passed version.
RESOLUTION_PAGE = (
    "118TH CONGRESS \r\n1ST SESSION S. CON. RES. 7 \r\nCONCURRENT RESOLUTION \r\n"
    "Condemning Russia’s unjust and arbitrary deten\ufffetion of Vladimir Kara-Murza. \r\n"
    "Whereas Vladimir Kara-Murza is a Russian opposition \r\n"
    "leader; and \r\n"
    "Whereas he remains in detention: Now, therefore, be it \r\n"
    "1 Resolved by the Senate (the House of Representatives \r\n"
    "2 concurring), That Congress condemns his detention. \r\n"
    "Passed the Senate May 4, 2023. \r\nAttest: \r\nSecretary. \r\n"
)


def test_resolution_clauses_title_and_number():
    pages = [page_lines(RESOLUTION_PAGE)]
    blocks = bill_blocks(pages, {1: "1"})
    text = bill_markdown(blocks)
    assert ("\n\nWhereas Vladimir Kara-Murza is a Russian opposition leader; and\n\n"
            "Whereas he remains in detention: Now, therefore, be it\n\n"
            "Resolved by the Senate (the House of Representatives concurring), That Congress condemns his detention."
            "\n\nPassed the Senate May 4, 2023.\n\nAttest: Secretary.\n") in text
    assert bill_number(pages) == "S. Con. Res. 7, 118th Congress"
    # No short title ("may be cited as"): the official title after "CONCURRENT RESOLUTION".
    assert bill_title(blocks) == "Condemning Russia’s unjust and arbitrary detention of Vladimir Kara-Murza."
    # A passed version can lack the title on its front; the back cover repeats it.
    passed = page_lines("CONCURRENT RESOLUTION \r\nWhereas socialism has failed; \r\n"
                        "CONCURRENT RESOLUTION \r\nDenouncing the horrors of socialism. \r\n")
    assert bill_title(bill_blocks([passed], {1: "1"})) == "Denouncing the horrors of socialism."


@pytest.mark.parametrize("cover, number", [
    ("1ST SESSION H. R. 8812", "H.R. 8812"), ("1ST SESSION S. 3312", "S. 3312"),
    ("1ST SESSION H. RES. 684", "H. Res. 684"), ("H. Res. 999 In the House of Representatives", "H. Res. 999"),
    ("1ST SESSION H. CON. RES. 9", "H. Con. Res. 9"), ("1ST SESSION S. J. RES. 3", "S.J. Res. 3"),
])
def test_measure_numbers_in_citation_form(cover, number):
    assert bill_number([page_lines(cover)]) == number


def test_bill_detection_title_and_number():
    pages = [page_lines(BILL_PAGE_1), page_lines(BILL_PAGE_2)]
    assert is_line_numbered(pages[:1])
    assert not is_line_numbered([page_lines("Abstract\nWe study 3 models.\n1 Introduction\nText.")])
    cover = page_lines("II \r\n118TH CONGRESS \r\n1ST SESSION S. 3312 \r\n"
                       "4 This Act may be cited as the ‘‘Frontier \r\n5 AI Act of 2023’’. \r\n")
    assert bill_number([cover]) == "S. 3312, 118th Congress"
    assert bill_title(bill_blocks([cover], {1: "1"})) == "Frontier AI Act of 2023"


def test_printed_page_numbers_found_in_headers_when_the_pdf_has_no_labels():
    # Federal Register: the first page has the number on its own line, later ones in the header.
    federal_register = ["Presidential Documents\n75191 \nFederal Register \nVol. 88, No. 210",
                        "75192 Federal Register / Vol. 88, No. 210 / Wednesday, November 1, 2023\ntext",
                        "75193 Federal Register / Vol. 88, No. 210 / Wednesday, November 1, 2023\ntext"]
    assert printed_page_offset(federal_register) == 75190
    # A footer "2", "3" ... from the second page on: same as the positions.
    assert printed_page_offset(["Title\ntext", "text\n2", "text\n3", "text\n4"]) == 0
    # The same year on every page is not a page number.
    assert printed_page_offset(["Report 2023\ntext", "Report 2023\ntext", "Report 2023\ntext"]) is None
    assert printed_page_offset(["no numbers", "here"]) is None



def test_list_numbers_docling_invents_before_a_label_are_dropped():
    # EU AI Act, Article 5: the PDF has "(a) the placing ...", Docling wrote "2. (a) the placing ...".
    markdown = "1. The following AI practices shall be prohibited:\n2. (a) the placing on the market\n3. (b) the use\n"
    assert drop_invented_list_numbers(markdown) == (
        "1. The following AI practices shall be prohibited:\n- (a) the placing on the market\n- (b) the use\n")
    # A real paragraph number followed by text stays; so does a number before a year in brackets.
    assert drop_invented_list_numbers("3. ( 57 ) Directive (EU) 2016/943\n") == "- ( 57 ) Directive (EU) 2016/943\n"
    assert drop_invented_list_numbers("2. Paragraph 1 shall not apply.\n3. (2024) was a year.\n") == (
        "2. Paragraph 1 shall not apply.\n3. (2024) was a year.\n")
