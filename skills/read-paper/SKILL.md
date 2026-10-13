---
name: read-paper
description: Read, summarize or analyze an academic paper or a U.S. congressional bill or resolution that the user points to as a PDF file, an arXiv ID (e.g. 2307.09288), an arXiv link, or a link to a bill's PDF (e.g. GovInfo or congress.gov). Converts it with the user's local paper2md tool into Markdown with page markers (papers also get figure and equation images and table CSVs), then works from that. Use whenever the user asks about a specific research paper by file, arXiv ID or arXiv URL, or a specific bill or resolution by PDF, link or number (e.g. S. 3312, H.R. 815, H. Res. 684, S. Con. Res. 7).
---

# Reading a paper or bill with paper2md

paper2md is the user's own tool (project: `/Users/da/Desktop/Claude code first project python PDF tool`).
It turns a paper or a congressional bill into text that is cheaper and more precise to work with
than the PDF itself.

## 1. Find or make the conversion

Converted documents live in `~/papers/<id>/`, where `<id>` is the arXiv ID (old-style IDs with a
slash use an underscore: `hep-th/9901001` → `hep-th_9901001`) or the PDF's file name without `.pdf`
(for bills from GovInfo, e.g. `BILLS-118s3312is`).

- If `~/papers/<id>/paper.md` exists, use it; don't convert again unless the user asks.
- Otherwise convert. Use the full command: the `paper2md` alias only exists in interactive shells.

  ```bash
  uv run --project "/Users/da/Desktop/Claude code first project python PDF tool" paper2md "<PDF path, arXiv ID or arXiv link>" --out ~/papers
  ```

  A paper takes about 10–70 seconds and ends with a summary (`Done in …`, counts of figures,
  equations, tables, page markers). arXiv papers are downloaded to `~/papers/<id>/<id>.pdf` first.
  If it fails, show the user the error message rather than guessing.

- **Bills and resolutions** are recognized automatically (by their margin line numbers, or by the
  GPO's printed cover and stamps) and convert in about a second. The tool only reads local PDFs,
  so one given as a link has to be downloaded first: save it as `~/papers/<name>/<name>.pdf`, then
  convert that file. Given only a number, GovInfo serves
  `https://www.govinfo.gov/content/pkg/BILLS-<congress><type><number><version>/pdf/` + the same
  name + `.pdf`, e.g. `BILLS-118s3312is` (118th Congress, S. 3312, introduced in the Senate).
  Types: `hr`, `s`, `hres`, `sres`, `hconres`, `sconres`, `hjres`, `sjres`. Common versions:
  `ih`/`is` introduced, `rh`/`rs` reported, `eh`/`es` passed one chamber, `enr` passed both.
  Different versions have different text, so tell the user which version you fetched. If the
  download isn't a PDF, that version doesn't exist.

## 2. Read `paper.md`

Read only what the question needs: for long documents, read in parts and start with the relevant
sections. Don't paste large parts of the document into replies.

What the format means:

- **The block at the top** (between `---` lines) gives the title, authors and publication date
  (exact for arXiv papers; other PDFs have only the detected title), the source, the page count,
  and how the file was made. Use it for citations, e.g. "He et al. (2015), arXiv:1512.03385, p. 6".
  For a bill or resolution it gives the short title (or the official title when there is none)
  and the number instead, e.g. `bill: "S. Con. Res. 7, 118th Congress"`; sponsors are in the
  text on page 1.
- **`[p. N]`** marks where page N starts (the PDF's printed page number if it has one). Cite pages for
  claims, e.g. "(p. 7)". A marker inside a paragraph means the paragraph continues on that page.
  When the printed number differs from the page's position in the PDF, both are given:
  `[p. 4567 | pdf 3]`. Cite the printed number (4567); "pdf 3" is only for finding the page in a viewer.
- **Figures**: a caption line followed by `![Image](figures/figure-NN.png)`; NN is the paper's own
  figure number. Open the image only when the answer depends on what the figure shows.
- **Equations**: `![Equation](equations/equation-NN.png)`, numbered in reading order (not the paper's
  equation numbers, which are visible inside the image). Open the image when the math matters.
  If the user needs the equations as text (quoting, derivations, many math questions), offer to
  reconvert with `--formulas`: it adds LaTeX but takes about 20 seconds per equation (the tool
  prints an estimate first), so ask before running it on equation-heavy papers.
- **Tables**: inline as Markdown, and as `tables/table-NN.csv` (the paper's table number;
  `untitled-table-NN.csv` when no caption was found).
- **Sub- and superscripts** are written `10^{-9}`, `d_{model}`, `β_{1}`; `^{∗}`/`^{†}` after
  author names or words are footnote markers.

### Bills

A bill has no figures, tables or equations. Titles and sections are `##` headings
(`## TITLE I—…`, `## SEC. 201. DEFINITIONS.`), and every `(a)`, `(1)`, `(A)`, `(i)` starts its own
paragraph. Those paragraphs are all at the same level: the nesting is not shown, so work it out
from the labels before citing. Federal bills nest section → `(a)` subsection → `(1)` paragraph →
`(A)` subparagraph → `(i)` clause → `(I)` subclause, so "(A)" after "(2)" under SEC. 201 is
"sec. 201(2)(A)". `(i)` is ambiguous: after `(h)` it is a subsection, under an `(A)` it is a
clause. Cite bills by section and page, e.g. "S. 3312, sec. 201(2)(A), p. 11". Bills often
repeat a definition word for word in several titles, so find the section before quoting it.

A resolution has a preamble of Whereas clauses, each its own paragraph, which explain but don't
decide anything; what the resolution actually does is in the Resolved clause after them
("Resolved, That the House of Representatives condemns ..."), often with its own `(1)`, `(2)`.
Keep the two apart when summarizing.

## 3. Known weak spots

- Small fractions or sums written inside a sentence come out garbled: `1 √_{dk}` is 1/√d_k and
  `∑_{dk}_{i=1}` is a sum from i=1 to d_k. Check the context or the page in the PDF when it matters,
  and say so when unsure.
- With `--formulas`, the LaTeX is occasionally wrong; the equation image right after it is the
  reference.
- A few tables can be untitled or missing (e.g. example boxes read as normal text); their content
  is still in `paper.md`.
- **Bills and resolutions:** the margin line numbers are removed, so a "page 12, line 4"
  reference (common in amendments) can't be found in `paper.md`; check the PDF. A hyphen at a
  line end is kept only if the hyphenated word appears unbroken elsewhere in the document, so a
  rare compound can lose its hyphen (`non-`/`government` → `nongovernment`).
- **Reported versions** (`rh`/`rs`) print the text a committee strikes out and the text it
  inserts in italics; the conversion keeps both as plain text, unmarked. S. Con. Res. 7
  (reported) has its `(1)`–`(5)` twice: the struck original, then the committee's version. Say
  so when it matters, and check the PDF before quoting either as the resolution's text.

If something looks wrong in the conversion (missing section, figure with the wrong caption),
tell the user: it's how the tool gets improved.
