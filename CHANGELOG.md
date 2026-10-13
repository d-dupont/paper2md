# Changelog

What changed in each version, newest first.

## 0.3.0 (2026-10-12)

### New
- **Congressional bills**: PDFs with margin line numbers (GPO bills) are recognized
  automatically (or with `--bill`) and read straight from the PDF: line numbers, page headers
  and printing-office stamps are removed, words broken at line ends are rejoined, each `SEC.`
  heading and `(a)`/`(1)`/`(A)` paragraph gets its own paragraph, and the information block
  names the bill and its short title. Previously the line numbers were glued into the words
  (`non8 government`).
- **Printed page numbers from headers and footers**: for PDFs without page labels, the page
  numbers printed on the pages are used when they run consistently, e.g. the Federal Register's
  `[p. 75196 | pdf 6]`, or reports with an unnumbered cover.
- **Both page numbers in markers**: when the printed page differs from the position in the
  file, markers read `[p. 4567 | pdf 3]`.

## 0.2.0 (2026-10-12)

### New
- Information block at the top of `paper.md`: title, authors and date (from arXiv's API for
  arXiv papers), source, link, page count, how the file was converted, and how to read it.

### Improved
- Plain `<` and `&` instead of `&lt;` and `&amp;`.
- Readable multi-row table headers in the CSVs (`COCO train / COCO val`).
- Windows: a leading `~` in the PDF path or `--out` is expanded.
- Test badge; unit tests run on Linux and Windows on every push.

## 0.1.0 (2026-10-12)

The first release.
- Markdown in correct reading order (including two-column pages) with `[p. N]` page markers.
- Figures saved as images linked to their captions; tables as CSV; equations as images
  (`--formulas` adds LaTeX).
- Superscripts, subscripts and accents restored; arXiv IDs and links downloaded and converted.
- The `read-paper` Claude Code skill.
