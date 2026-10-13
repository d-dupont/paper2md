# paper2md

[![tests](https://github.com/d-dupont/paper2md/actions/workflows/tests.yml/badge.svg)](https://github.com/d-dupont/paper2md/actions/workflows/tests.yml)

Convert an academic PDF (or an arXiv ID) into clean Markdown, figure images, equation images
and table CSVs that Claude can read cheaply and cite precisely.

```bash
paper2md 1512.03385
```

```
Downloading arXiv 1512.03385 ...
Converting ~/papers/1512.03385/1512.03385.pdf ...
Done in 17s: 12 pages -> ~/papers/1512.03385/paper.md
  7 figures, 2 equations, 15 tables, 18 page markers
```

## Why

Sending a PDF to Claude costs 1,500–3,000 tokens of text per page, plus an image of every page.
The converted `paper.md` is typically 2–4× smaller than the text alone, and figures, equations
and tables are separate files that Claude opens only when a question needs them. Page markers
keep every claim citable.

## What you get

```
~/papers/1512.03385/
├── 1512.03385.pdf        the original (arXiv downloads only)
├── paper.md              the paper as Markdown, with [p. N] page markers
├── figures/figure-04.png named by the paper's figure numbers
├── equations/equation-01.png
└── tables/table-02.csv   named by the paper's table numbers
```

An excerpt of `paper.md`:

```markdown
---
title: "Deep Residual Learning for Image Recognition"
authors: ["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"]
published: "2015-12-10"
source: "arXiv:1512.03385"
pages: 12
---

Figure 4. Training on ImageNet. Thin curves denote training error, and bold curves denote ...

![Image](figures/figure-04.png)

... compared to its plain counterpart, the 34-layer [p. 6] ResNet reduces the top-1 error ...

The function F(x, {W_{i}}) represents the residual mapping to be learned ...
```

- **Reading order** is correct across two-column layouts, including pages the layout model
  reads right-column-first.
- **Figures**, including vector charts, are cropped whole: split panels are merged, axis labels and
  panel titles are kept inside the image, and each figure is linked right after its own caption.
- **Equations** are saved as images by default; `--formulas` also converts them to LaTeX
  (slower: about 20 s per equation on a laptop CPU).
- **Tables** are saved as CSV, linked to their captions, with row-group labels repeated on every
  row they cover.
- **Sub- and superscripts** that PDF text extraction flattens are restored (`10^{-9}`, `d_{model}`),
  in the text and in the CSVs, and accents are fixed (`M¨uller` → `Müller`).
- **An information block** at the top of `paper.md` gives the title, authors and date (from arXiv's
  API for arXiv papers), the source and page count, so Claude can cite the paper properly.
- **Page markers** `[p. N]` use the PDF's printed page numbers, including inside paragraphs that
  cross a page break and for footnotes.

## Install

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and all dependencies for you).

```bash
git clone https://github.com/d-dupont/paper2md.git
cd paper2md
uv sync
```

The first conversion downloads Docling's layout models (about 1 GB, once).

Page markers use the page number printed on the page: the PDF's own page labels if it has them,
otherwise the numbers in its headers or footers when they run consistently (the Federal Register's
75191, 75192, …). When that differs from the page's position in the file, both are given:
`[p. 75196 | pdf 6]`.

## Usage

```bash
uv run paper2md paper.pdf                    # writes output/paper/
uv run paper2md 2307.09288 --out ~/papers    # arXiv ID or link: downloads the PDF, then converts
uv run paper2md paper.pdf --formulas         # also convert equations to LaTeX (slow)
uv run paper2md scan.pdf --ocr               # scanned PDFs without a text layer
uv run paper2md paper.pdf --verbose          # show the libraries' progress and details
uv run paper2md bill.pdf                     # congressional bills are detected automatically
uv run paper2md doc.pdf --bill / --no-bill   # force or switch off bill mode
```

**Bills.** Congressional bills printed by the GPO have line numbers (1–25) in the margin, which
a layout model mixes into the words (`non8 government`). When most pages carry such numbers,
paper2md reads the text directly from the PDF instead: it drops the line numbers, page headers
and printing-office stamps, joins accents the GPO prints after their letter (`LUJA´N` → `LUJÁN`),
rejoins words broken at line ends, gives each `SEC.` heading and
each `(a)`/`(1)`/`(A)` paragraph its own paragraph, and keeps the `[p. N]` markers. The
information block names the bill (`S. 3312, 118th Congress`) and its short title. One thing
can't be read off the page: whether a hyphen at a line end belongs to the word. It is kept when
the hyphenated word appears unbroken elsewhere in the bill (`high-impact`), and dropped
otherwise (`non-`/`government` → `nongovernment`).

Before a `--formulas` run the tool prints how many equations it found and how long they will take;
Ctrl+C stops it.

To run it from any folder, add an alias to your shell configuration (e.g. `~/.zshrc`):

```bash
alias paper2md='uv run --project "/path/to/paper2md" paper2md --out ~/papers'
```

## Using it with Claude

- **Claude Code:** `skills/read-paper/SKILL.md` is a skill that converts a paper on request
  ("summarize arXiv 1512.03385 with page citations"), reuses earlier conversions in `~/papers/`,
  and explains the output format to Claude. Link it into `~/.claude/skills/read-paper` and update
  the project path inside it.
- **claude.ai:** convert locally, then upload `paper.md` plus any figures or tables you ask about.

## How it works

[Docling](https://github.com/docling-project/docling) does the heavy lifting: a layout model finds
text, headings, figures, tables and equations, and a table model reads table structure. paper2md
then repairs what Docling gets wrong on academic papers, using the PDF's own character positions,
font sizes and drawn lines (read with [pypdfium2](https://github.com/pypdfium2-team/pypdfium2)):
reading order, figure grouping and captions, page markers, superscripts, accents and table row
groups. Each step is a module in `src/paper2md/`, run in order by `pipeline.py`.

## Known limitations

- Small fractions or sums written inside a sentence come out garbled (`1 √_{dk}` for 1/√d_k).
- With `--formulas` the LaTeX is occasionally wrong; the equation image next to it is the reference.
- A few tables stay untitled or are read as text (e.g. example boxes); their content is still in `paper.md`.
- Time estimates are calibrated on an Apple M1 Max.

## Development

```bash
uv run pytest                 # everything (~2 min: converts sample arXiv papers)
uv run pytest -m "not slow"   # unit tests only
```

The end-to-end tests download a few arXiv papers into `samples/` on first run; the PDFs are not
part of the repository.

This project was built step by step as a learning project, with
[Claude Code](https://claude.com/claude-code). `CLAUDE.md` documents the design decisions.

## License

[MIT](LICENSE)
