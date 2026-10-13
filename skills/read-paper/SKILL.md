---
name: read-paper
description: Read, summarize or analyze an academic paper that the user points to as a PDF file, an arXiv ID (e.g. 2307.09288) or an arXiv link. Converts it with the user's local paper2md tool into Markdown with page markers, figure and equation images and table CSVs, then works from that. Use whenever the user asks about a specific research paper by file, arXiv ID or arXiv URL.
---

# Reading a paper with paper2md

paper2md is the user's own tool (project: `/Users/da/Desktop/Claude code first project python PDF tool`).
It turns a paper into text that is cheaper and more precise to work with than the PDF itself.

## 1. Find or make the conversion

Converted papers live in `~/papers/<id>/`, where `<id>` is the arXiv ID (old-style IDs with a slash
use an underscore: `hep-th/9901001` → `hep-th_9901001`) or the PDF's file name without `.pdf`.

- If `~/papers/<id>/paper.md` exists, use it; don't convert again unless the user asks.
- Otherwise convert. Use the full command: the `paper2md` alias only exists in interactive shells.

  ```bash
  uv run --project "/Users/da/Desktop/Claude code first project python PDF tool" paper2md "<PDF path, arXiv ID or arXiv link>" --out ~/papers
  ```

  It takes about 10–70 seconds and ends with a summary (`Done in …`, counts of figures, equations,
  tables, page markers). arXiv papers are downloaded to `~/papers/<id>/<id>.pdf` first.
  If it fails, show the user the error message rather than guessing.

## 2. Read `paper.md`

Read only what the question needs: for long papers, read in parts and start with the relevant
sections. Don't paste large parts of the paper into replies.

What the format means:

- **The block at the top** (between `---` lines) gives the title, authors and publication date
  (exact for arXiv papers; other PDFs have only the detected title), the source, the page count,
  and how the file was made. Use it for citations, e.g. "He et al. (2015), arXiv:1512.03385, p. 6".
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

## 3. Known weak spots

- Small fractions or sums written inside a sentence come out garbled: `1 √_{dk}` is 1/√d_k and
  `∑_{dk}_{i=1}` is a sum from i=1 to d_k. Check the context or the page in the PDF when it matters,
  and say so when unsure.
- With `--formulas`, the LaTeX is occasionally wrong; the equation image right after it is the
  reference.
- A few tables can be untitled or missing (e.g. example boxes read as normal text); their content
  is still in `paper.md`.

If something looks wrong in the conversion (missing section, figure with the wrong caption),
tell the user: it's how the tool gets improved.
