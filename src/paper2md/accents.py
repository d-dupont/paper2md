"""Joins accents that LaTeX-made PDFs store as separate characters: "M¨uller" -> "Müller".

LaTeX draws an accent as its own glyph placed over the letter, so the text layer holds a
spacing accent followed by the letter. We replace it with the matching combining accent
after the letter and let Unicode NFC merge the pair ("e" + U+0301 -> "é") where it can.
"""

import re
import unicodedata

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

# Spacing accent -> combining accent.
COMBINING = {
    "´": "́",  # acute
    "`": "̀",  # grave
    "¨": "̈",  # diaeresis / umlaut
    "ˆ": "̂",  # circumflex / hat
    "˜": "̃",  # tilde
    "¯": "̄",  # macron / bar
    "˘": "̆",  # breve
    "˙": "̇",  # dot above
    "˚": "̊",  # ring
    "˝": "̋",  # double acute
    "ˇ": "̌",  # caron
    "¸": "̧",  # cedilla
}
LETTER = r"[^\W\d_]"
# An accent before a letter, at most one space apart ("˜B", "ˆ ϵ"). The backtick is only an
# accent between two letters ("Mich`ele"); elsewhere it is code (```) or a quote mark.
SPACING_ACCENT = re.compile(rf"([´¨ˆ˜¯˘˙˚˝ˇ¸]) ?({LETTER})|(?<={LETTER})(`)({LETTER})")
# LaTeX puts accents on a dotless i or j (\'{\i}); the combined letter has the dot's place.
UNDOTTED = {"ı": "i", "ȷ": "j"}


def join_accents(text: str) -> str:
    def combine(match: re.Match) -> str:
        accent = match.group(1) or match.group(3)
        letter = match.group(2) or match.group(4)
        return unicodedata.normalize("NFC", UNDOTTED.get(letter, letter) + COMBINING[accent])

    return SPACING_ACCENT.sub(combine, text)


def fix_accents(doc: DoclingDocument) -> int:
    """Join accents in all text and table cells of `doc`. Returns how many items changed."""
    changed = 0
    targets = [t for t in doc.texts if t.label != DocItemLabel.FORMULA]  # LaTeX stays as is
    targets += [cell for table in doc.tables for cell in table.data.table_cells]
    for target in targets:
        fixed = join_accents(target.text)
        if fixed != target.text:
            target.text = fixed
            changed += 1
    return changed
