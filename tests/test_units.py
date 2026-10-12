"""Fast tests of single functions on small, hand-made inputs (no Docling run)."""

import pytest
from docling_core.types.doc import BoundingBox, CoordOrigin, DoclingDocument, ProvenanceItem, Size
from docling_core.types.doc.labels import DocItemLabel

from paper2md.accents import join_accents
from paper2md.arxiv import folder_name, parse_arxiv_id
from paper2md.cli import run
from paper2md.convert import performance_cores
from paper2md.figures import find_caption
from paper2md.layout import Box
from paper2md.reading_order import Entry, column_order
from paper2md.row_groups import find_groups
from paper2md.pages import mark_page_breaks_inside_text
from paper2md.superscripts import Run, locate, mark, normalize
from paper2md.tables import caption_candidates, nearest_caption, table_number


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


# --- command line -------------------------------------------------------------------------

def test_missing_file_is_a_clear_error(capsys):
    with pytest.raises(SystemExit) as stop:
        run(["no-such-paper.pdf"])
    assert stop.value.code == 2
    assert "file not found, and not an arXiv ID" in capsys.readouterr().err


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
