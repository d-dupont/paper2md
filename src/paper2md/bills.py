"""Congressional bills and resolutions as printed by the GPO.

Docling reads the margin line numbers (1-25 on every page) into the text ("non8 government",
"Account5 ability"), splits every printed line into its own list item and keeps the printing
office's stamps. Those PDFs are plain text in a fixed layout, so for them we skip Docling and
read each page's text with pdfium, which gives the lines in order with the line number first:

    17 (1) IN GENERAL.—Not later than 180 days
    18 after the date of the enactment of this Act, the

We drop the line numbers, the page header ("12", "•S 3312 IS"), the stamps ("VerDate ...",
"... PROD with BILLS" or "... PROD with $$_JOB") and the end-of-bill ornament, join accents
printed after their letter ("LUJA´N" -> "LUJÁN", see accents.py), rejoin words broken at line
ends, start a new paragraph at each section heading and each (a)/(1)/(A) paragraph, and add the
usual [p. N] markers (inside a paragraph when it runs onto the next page).

Resolutions number only the lines of their resolving clause; their Whereas clauses have none.
is_gpo_measure() recognizes them by the printed cover and the printing office's marks, and they
are read here too: Docling put page 10 of S. Con. Res. 7 under page 8 and left line numbers in
the Resolved clause ("con1", "2"). Each Whereas and Resolved clause starts a paragraph. GPO
documents that still reach Docling (no cover, e.g. a passed House resolution printed as an
attestation) lose their stamps through drop_stamps().

Words broken at a line end: pdfium marks the break with U+FFFE. Whether the hyphen belongs to
the word ("high-impact") or only marks the break ("Representa-tives") can't be told from the
page, so the hyphen is kept when the hyphenated form appears unbroken elsewhere in the bill.
A plain "-" at a line end ("180-" / "day") is always part of the word.

The back cover of a reported or passed version is printed turned 90 degrees. pdfium assembles
lines across the page, which slices through the turned lines and mixes their words up, so a page
whose text is mostly turned is rebuilt from its characters' positions (page_text()).
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pypdfium2
import pypdfium2.raw as pdfium_c

from paper2md.accents import join_accents_after

LINE_NUMBER = re.compile(r"^(\d{1,2}) (?=\S)")
SOFT_BREAK = "￾"
# The page header naming the measure and its version: "•S 3312 IS", "•HCON 9 EH", and in a
# reported Senate resolution without the bullet and with a longer code, "SRES 99 RS1S".
RUNNING_HEADER = re.compile(r"(?:•\s*)?(?:HR|HRES|HCON|HJRES|S|SRES|SCON|SJRES) \d+ [A-Z]{2,4}(?:\d[A-Z])?")
# Each pattern covers a whole stamp, start to end. Docling hands us paragraphs, not lines, and a
# paragraph that merely starts with "VerDate" might hold real text after it.
STAMPS = (
    # "VerDate Sep 11 2014 01:21 Nov 22, 2023 Jkt 049200 PO 00000 Frm 00011 Fmt 6652 Sfmt 6201
    # E:\BILLS\S3312.IS S3312"
    re.compile(r"VerDate .+ Jkt \S+ PO \S+ Frm \S+ Fmt \S+ Sfmt \S+ \S+ \S+"),
    # "dmwilson on DSKJM0X7X2PROD with BILLS", "kjohnson on DSK7ZCZBW3PROD with $$_JOB"
    re.compile(r"\S+ on \S+PROD with \S+"),
    RUNNING_HEADER,
    re.compile(r"Æ"),                                    # the end-of-bill ornament, read as "Æ"
)
PAGE_HEADER = re.compile(r"^(?:\d+|[IVX]{1,4})$")    # the page number, or the cover's "II"
HEADING = re.compile(r"^(?:SEC(?:TION)?\.? \d|TITLE [IVXLC]+\b|Subtitle [A-Z]\b|DIVISION [A-Z]\b)")
# A label is up to 5 letters ("(iv)", "(aa)") or up to 3 digits ("(405)"): a line that wraps to
# start with a year, "(2008), the Supreme Court ...", is not a new paragraph. Resolutions add
# their Whereas and Resolved clauses; passed versions end with "Passed the House ..." and "Attest:".
BODY_START = re.compile(r"(?:Be it enacted|Whereas\b|Resolved\b)")
PARAGRAPH_START = re.compile(
    r"^(?:[‘'\"“]{0,2}\((?:[A-Za-z]{1,5}|\d{1,3})\)|SEC(?:TION)?\.? \d|Sec\. \d|TITLE [IVXLC]+\b|"
    r"Subtitle [A-Z]\b|DIVISION [A-Z]\b|Be it enacted|Whereas\b|Resolved\b|"
    r"Passed the (?:House|Senate)\b|Attest:)")
DOCUMENT_TYPE = re.compile(r"A BILL|AN ACT|(?:CONCURRENT |JOINT )?RESOLUTION")
# The measure's number on the cover: "S. 3312", "H. R. 8812", "S. CON. RES. 7", "H. Res. 999".
MEASURE = re.compile(r"\b(H\.\s?CON\.\s?RES|S\.\s?CON\.\s?RES|H\.\s?J\.\s?RES|S\.\s?J\.\s?RES|H\.\s?RES|S\.\s?RES|"
                     r"H\.\s?R|S)\.\s?(\d+)\b", re.IGNORECASE)
MEASURE_LABELS = {"HR": "H.R.", "S": "S.", "HRES": "H. Res.", "SRES": "S. Res.", "HCONRES": "H. Con. Res.",
                  "SCONRES": "S. Con. Res.", "HJRES": "H.J. Res.", "SJRES": "S.J. Res."}
# A bill or resolution as the GPO prints it starts with this cover: "118TH CONGRESS" / "1ST SESSION".
COVER = re.compile(r"\b\d{2,3}(?:ST|ND|RD|TH|D) CONGRESS\b.*?\b\d(?:ST|ND|RD|TH|D) SESSION\b", re.S)
BILLS_STAMP = re.compile(r"VerDate .+ E:\\BILLS\\")
HYPHENATED = re.compile(r"\b[^\W\d_]+(?:-[^\W\d_]+)+\b")
SHORT_TITLE = re.compile(r"may be cited as the [‘'\"“]{1,2}(.+?)[’'\"”]{1,2}", re.S)
MIN_NUMBERED_LINES = 5  # a page with this many numbered lines counts as line-numbered


def is_stamp(text: str) -> bool:
    """Is `text` (a line, or a whole paragraph) nothing but a printing-office stamp?"""
    return any(stamp.fullmatch(text.strip()) for stamp in STAMPS)


def drop_stamps(doc) -> int:
    """Delete the paragraphs of a Docling document that are only a stamp. Returns how many.

    For GPO documents Docling reads (resolutions without line numbers); other PDFs have none.
    """
    stamps = [item for item in doc.texts if is_stamp(item.text)]
    if stamps:
        doc.delete_items(node_items=stamps)
    return len(stamps)


@dataclass
class Line:
    text: str
    numbered: bool


def page_lines(text: str) -> list[Line]:
    """One page's text from pdfium -> its lines, without header, stamps and line numbers."""
    text = join_accents_after(text)
    text = text.replace(SOFT_BREAK, SOFT_BREAK + "\n")  # pdfium drops the line break after it
    raw = [line.strip() for line in re.split(r"\r\n|\r|\n", text)]
    raw = [line for line in raw if line and not is_stamp(line)]
    if raw and PAGE_HEADER.match(raw[0]):
        raw = raw[1:]
    lines, counter = [], 0
    for line in raw:
        m = LINE_NUMBER.match(line)
        # The numbers run 1, 2, 3 ... down each page (the first may be any of 1-25, if the
        # page's first lines weren't read); allow one to be missing.
        if m and counter < int(m.group(1)) <= (25 if counter == 0 else counter + 2):
            counter = int(m.group(1))
            lines.append(Line(line[m.end():], True))
        else:
            lines.append(Line(line, False))
    return lines


def is_line_numbered(pages: list[list[Line]]) -> bool:
    """Most pages carry margin line numbers."""
    numbered = sum(1 for lines in pages if sum(line.numbered for line in lines) >= MIN_NUMBERED_LINES)
    return bool(pages) and numbered * 2 >= len(pages)


def page_texts(pdf: Path) -> list[str]:
    document = pypdfium2.PdfDocument(pdf)
    try:
        return [page_text(document[i]) for i in range(len(document))]
    finally:
        document.close()


def read_pages(pdf: Path) -> list[list[Line]]:
    return [page_lines(text) for text in page_texts(pdf)]


def is_gpo_measure(texts: list[str]) -> bool:
    """A bill or resolution as the GPO prints it, whether or not its pages have line numbers.

    Resolutions number only the lines of their resolving clause, so is_line_numbered() misses
    them. They have the printed cover ("118TH CONGRESS" / "1ST SESSION") and the printing
    office's marks: a stamp naming its BILLS folder, or the running header "•HR 684 IH". The
    Federal Register has the same kind of stamp, but naming E:\\FR\\, and no such cover.
    """
    if not texts or not COVER.search(texts[0][:600]):
        return False
    lines = (line.strip() for text in texts for line in re.split(r"\r\n|\r|\n", text))
    return any(BILLS_STAMP.match(line) or RUNNING_HEADER.fullmatch(line) for line in lines)


@dataclass
class Char:
    """A character placed in its own line's frame, whichever way the page prints it."""
    text: str
    angle: int     # 0, 90, 180 or 270: how far the text is turned, clockwise
    start: float   # where it starts and ends along its line, in reading direction
    end: float
    across: float  # its middle across the lines: larger is a later line
    size: float    # the font's height


def page_text(page) -> str:
    """A page's text, line by line. Mostly-turned pages are rebuilt from character positions."""
    textpage = page.get_textpage()
    # Decide on every 7th character first: placing them all costs ten times the plain reading.
    sample = [_angle(textpage, i) for i in range(0, textpage.count_chars(), 7)
              if textpage.get_text_range(i, 1).strip()]
    if not sample or sample.count(0) * 2 >= len(sample):
        return textpage.get_text_range()
    chars = _chars(textpage)
    angles = Counter(char.angle for char in chars)
    lines = []
    for angle, _count in angles.most_common():  # the turned text first, then e.g. the stamps
        lines += turned_lines([char for char in chars if char.angle == angle])
    return "\r\n".join(lines)


def _angle(textpage, i: int) -> int:
    return round(math.degrees(pdfium_c.FPDFText_GetCharAngle(textpage.raw, i)) / 90) % 4 * 90


def _chars(textpage) -> list[Char]:
    chars = []
    for i in range(textpage.count_chars()):
        text = textpage.get_text_range(i, 1)
        if not text.strip():  # pdfium's own spaces and line breaks: rebuilt from the gaps
            continue
        angle = _angle(textpage, i)
        sin, cos = math.sin(math.radians(angle)), math.cos(math.radians(angle))
        # The loose box spans the font's full height, the same for every letter of a line; a
        # tight box is taller for "l" than for "a", which would split the line.
        left, bottom, right, top = textpage.get_charbox(i, loose=True)
        along = [x * cos - y * sin for x in (left, right) for y in (bottom, top)]
        across = [-x * sin - y * cos for x in (left, right) for y in (bottom, top)]
        chars.append(Char(text, angle, min(along), max(along), sum(across) / 4, max(across) - min(across)))
    return chars


def turned_lines(chars: list[Char]) -> list[str]:
    """Characters of one angle -> their lines in reading order, with spaces where the gaps are."""
    groups: list[list[Char]] = []
    for char in sorted(chars, key=lambda c: c.across):
        first = groups[-1][0] if groups else None
        if first and abs(char.across - first.across) <= 0.5 * min(char.size, first.size):
            groups[-1].append(char)
        else:
            groups.append([char])
    lines = []
    for group in groups:
        group.sort(key=lambda c: c.start)
        text = group[0].text
        for before, char in zip(group, group[1:]):
            text += (" " if char.start - before.end > 0.15 * min(char.size, before.size) else "") + char.text
        lines.append(text)
    # pdfium marks a word broken at a line end with U+FFFE on upright pages, not always on turned
    # ones ("democ-" / "racy"): a hyphen after a letter, before a lowercase line, is such a break.
    for k in range(len(lines) - 1):
        if len(lines[k]) > 1 and lines[k][-1] == "-" and lines[k][-2].isalpha() and lines[k + 1][:1].islower():
            lines[k] = lines[k][:-1] + SOFT_BREAK
    return lines


def _join(left: str, right: str, hyphenated: set[str]) -> str:
    """Join a line to the text before it, rejoining a word broken at the line end."""
    if left.endswith(SOFT_BREAK):
        left = left[:-1]
        before = re.search(r"[^\W\d_]+$", left)
        after = re.match(r"[^\W\d_]+", right)
        keep = before and after and f"{before.group()}-{after.group()}".lower() in hyphenated
        return left + ("-" if keep else "") + right
    if len(left) > 1 and left.endswith("-") and left[-2].isalnum():
        return left + right  # "180-" + "day"
    return left + " " + right


def _is_caps(text: str) -> bool:
    return any(c.isalpha() for c in text) and not any(c.islower() for c in text)


@dataclass
class Block:
    text: str
    heading: bool = False
    marker: bool = False  # a [p. N] line


def bill_blocks(pages: list[list[Line]], names: dict[int, str]) -> list[Block]:
    """Paragraphs, headings and page markers, in reading order."""
    all_text = " ".join(line.text for lines in pages for line in lines)
    hyphenated = {w.lower() for w in HYPHENATED.findall(all_text)}
    blocks: list[Block] = []
    current: Block | None = None
    for number, lines in enumerate(pages, start=1):
        pending = f"[p. {names[number]}]"
        for line in lines:
            text = line.text
            continues = current is not None and (
                current.text.endswith(SOFT_BREAK)
                or (current.text.endswith("-") and current.text[-2:-1].isalnum())
                or not _starts_block(current, line))
            if continues:
                joined = _join(current.text, text, hyphenated)
                if pending:  # the paragraph runs onto this page: marker at the next space
                    cut = joined.find(" ", len(current.text.rstrip(SOFT_BREAK + "-")))
                    cut = len(joined) if cut < 0 else cut
                    joined = f"{joined[:cut]} {pending}{joined[cut:]}"
                    pending = None
                current.text = joined
                continue
            if pending:
                blocks.append(Block(pending, marker=True))
                pending = None
            current = Block(text, heading=bool(HEADING.match(text)))
            blocks.append(current)
        if pending:  # a page with no text
            blocks.append(Block(pending, marker=True))
            current = None  # nothing continues across it: text after the marker is new
    for block in blocks:
        block.text = block.text.replace(SOFT_BREAK, "-")
    return blocks


def _starts_block(current: Block, line: Line) -> bool:
    """Does `line` start a new paragraph after the paragraph `current`?"""
    text = line.text
    if PARAGRAPH_START.match(text):
        return True
    if current.heading:
        # A heading continues on the next line only while it is in capitals and unfinished:
        # "TITLE I—ARTIFICIAL INTELLIGENCE RESEARCH AND" / "INNOVATION"
        return current.text.endswith(".") or not _is_caps(text)
    if not line.numbered:
        # The cover and the table of contents: lines in capitals stand alone
        # ("IN THE SENATE OF THE UNITED STATES", "A BILL").
        return _is_caps(text) or _is_caps(current.text)
    return False


def bill_markdown(blocks: list[Block]) -> str:
    parts = []
    for block in blocks:
        parts.append(("## " if block.heading else "") + block.text)
    return "\n\n".join(parts) + "\n"


def bill_title(blocks: list[Block]) -> str | None:
    """The Act's short title ("This Act may be cited as the 'X Act of 2023'"), else the official title."""
    text = " ".join(b.text for b in blocks if not b.marker)
    m = SHORT_TITLE.search(text)
    return " ".join(m.group(1).split()).rstrip(".,") if m else official_title(blocks)


def official_title(blocks: list[Block]) -> str | None:
    """The long title printed after "A BILL", "AN ACT" or "RESOLUTION": "Condemning the actions of ...".

    A passed version may have none on its front, where the Whereas clauses follow directly; the
    back cover repeats it.
    """
    for block, after in zip(blocks, blocks[1:]):
        if DOCUMENT_TYPE.fullmatch(block.text.strip()) and not after.marker and not BODY_START.match(after.text):
            return " ".join(after.text.split())
    return None


def bill_number(pages: list[list[Line]]) -> str | None:
    """"S. 3312, 118th Congress" or "S. Con. Res. 7, 118th Congress" from the cover page."""
    cover = " ".join(line.text for line in pages[0]) if pages else ""
    congress = re.search(r"\b(\d+(?:TH|ST|ND|RD|D)) CONGRESS\b", cover)
    measure = MEASURE.search(cover)
    if not measure:
        return None
    label = f"{MEASURE_LABELS[re.sub(r'[^A-Z]', '', measure.group(1).upper())]} {measure.group(2)}"
    return f"{label}, {congress.group(1).lower()} Congress" if congress else label


def process_bill(pdf: Path, paper_dir: Path, pages: list[list[Line]]) -> None:
    """Write paper.md for a bill or resolution (no figures, tables or equations)."""
    import time
    from datetime import date
    from importlib.metadata import version

    from paper2md.metadata import front_matter
    from paper2md.pages import page_names

    start = time.perf_counter()
    blocks = bill_blocks(pages, page_names(pdf))
    fields = {
        "title": bill_title(blocks),
        "bill": bill_number(pages),
        "source": pdf.name,
        "pages": len(pages),
        "converted": f"{date.today().isoformat()} with paper2md {version('paper2md')}",
        "layout": "bill or resolution as printed by the GPO: margin line numbers, page headers and "
                  "printing-office stamps removed",
        "notes": "[p. N] marks where page N starts. Section headings start with ##; each (a)/(1)/(A) "
                 "paragraph and each Whereas or Resolved clause starts a new paragraph.",
    }
    paper_dir.mkdir(parents=True, exist_ok=True)
    path = paper_dir / "paper.md"
    path.write_text(front_matter(fields) + bill_markdown(blocks), encoding="utf-8")
    markers = sum(b.text.count("[p. ") for b in blocks)
    print(f"Done in {time.perf_counter() - start:.0f}s: {len(pages)} pages -> {path}")
    print(f"  Bill or resolution: line numbers, page headers and stamps removed; {markers} page markers")
