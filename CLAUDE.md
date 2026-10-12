# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`paper2md` is a Python CLI that converts an academic PDF (e.g. an arXiv paper) into output that is cheap and easy for Claude to work with: clean Markdown in correct reading order (including two-column layouts), figures (including vector charts) saved as images linked to their captions, and tables extracted as CSV. The chosen conversion library is **Docling** (MIT license; ML layout model, figure-caption links, strong tables, optional formula-to-LaTeX).

The owner is new to software development and is building this to learn. Explain the reasoning and any new concepts as you go, build in small testable steps, and pause after each step rather than doing several at once.

## Commands

Everything runs through **uv**. Python 3.12 is pinned in `.python-version`. Don't use pip or activate the venv by hand.

```bash
uv run paper2md samples/1512.03385.pdf            # writes to output/1512.03385/
uv run paper2md samples/1512.03385.pdf --out DIR  # custom output root
uv run paper2md samples/1512.03385.pdf --ocr      # also OCR page images (only needed for scanned PDFs)
uv run paper2md samples/1706.03762.pdf --no-formulas  # skip equation->LaTeX (on by default; ~20 s per equation + ~30 s model load)
uv add <pkg>        # add a runtime dependency (updates pyproject.toml + uv.lock)
uv add --dev <pkg>  # add a dev-only dependency
```

Tests:

```bash
uv run pytest                    # everything (~2 min: converts 4 sample papers, one with equations)
uv run pytest -m "not slow"      # unit tests only (<1 s), for quick checks while editing
uv run pytest -k page_marker     # tests whose name contains "page_marker"
uv run pytest tests/test_units.py::test_ambiguous_run_is_left_alone   # one test
```

`tests/test_units.py` checks single functions on hand-made inputs. `tests/test_papers.py` (marked `slow`) runs the real command on sample papers and checks what was verified by hand: figure/caption links, table CSVs, superscripts, page markers, equations. `conftest.py` downloads missing samples from arXiv (the PDFs aren't committed) and converts each paper only once per test run. When fixing a bug, add a test that fails without the fix.

## Architecture

- `pyproject.toml` maps the `paper2md` command to `paper2md.cli:main` (src layout, `uv_build` backend).
- `src/paper2md/cli.py` only parses and validates arguments. Conversion logic belongs in separate modules that `cli.py` calls.
- `convert.py` runs Docling (OCR off by default: identical output on arXiv PDFs at half the time). `figures.py` then post-processes Docling's pictures, because Docling alone splits multi-panel figures, mislinks or drops captions, and crops off axis labels. It groups pictures by their nearest "Figure N" caption (below or beside), extends each crop down to its caption, absorbs short touching text (axis labels) into the figure and removes it from the body, re-parents the caption under the figure (otherwise the Markdown prints it twice), and names files by figure number.
- `tables.py` drops `document_index` tables (tables of contents, lists of figures: redundant with headings and captions), skips CSV export for an uncaptioned table before the abstract (the authors' title block), links tables lacking a "Table N" caption to the nearest unclaimed one above or below, and writes `table-NN.csv` / `untitled-table-NN.csv`. It runs after `figures.py`, which may detach a figure caption Docling had wrongly attached to a table.
- `pages.py` adds `[p. N]` markers (the PDF's printed page label if it has one, else the page's position): a line before the first item on each new page, and inside paragraphs that cross a page break at the character where the new page starts (from the item's per-page `prov.charspan`, snapped forward to a space because Docling's positions drift after rejoining hyphenated words). It runs first and shifts the charspans it moves, so `figures.py` still cuts at the right place. Checked against the PDF text: 92/101 markers verified; the rest are mostly check artifacts. Known quirk: Docling sometimes orders a footnote after the next page's marker.
- `superscripts.py` restores the sub/superscripts Docling flattens (`10-9` → `10^{-9}`, `β1` → `β_{1}`): it reads each character's baseline and font size with pdfium, marks runs smaller and raised/lowered than a nearby same-line character, and finds each run in Docling's text (or table cell) by its surrounding characters, longest unique context first; ambiguous runs are skipped. Order in `cli.py` matters: page markers → figures → superscripts → accents → tables. `figures.py` cuts text by character position, which inserted `^{...}` would shift, and the CSV files must be written after the marks. Known gap: stacked inline math (fractions, ∑ limits) comes out garbled.
- Equations: `cli.convert_with_estimate` does a quick pass without the formula model to count equations, prints a time estimate, then reconverts with it. The formula model (CodeFormulaV2) is CPU-only on Macs; `convert.performance_cores()` sets Docling's threads to the performance-core count (8 threads: 77 s vs Docling's default 4: 133 s; adding efficiency cores didn't help). Docling swallows `KeyboardInterrupt` during the formula step, so `cli.stop_now` handles Ctrl+C with `os._exit(130)`; nothing is written before conversion finishes.
- `accents.py` joins spacing accents that LaTeX PDFs store before their letter (`M¨uller` → `Müller`, `Garc´ıa` → `García`, `˜B` → `B̃`); a backtick counts as a grave accent only between two letters, so code fences stay intact.
- `write_markdown` passes `escape_underscores=False` so `x_{1}` isn't written as `x\_{1}`.
- `layout.py` holds what both share: `Box` (page rectangles in points, top-left origin), `box_of`, and `attach_caption`.
- Figure images are cropped from our own pypdfium2 render, not Docling's page images: Docling's default `docling-parse` backend renders some vector charts mostly blank (Scaling Laws, Figure 2). Don't switch Docling's backend to pypdfium2 to fix this: its text extraction adds spaces before punctuation (`[1 ,`).
- Output layout per paper: `<out>/<pdf stem>/paper.md`, plus `figures/figure-NN.png` and `tables/table-NN.csv`.
- `samples/` (test PDFs downloaded from arXiv) and `output/` are gitignored.

## Roadmap

Commit once at the end of each step.

- [x] Step 0: scaffold (uv package, git)
- [x] Step 1: argparse CLI with input validation
- [x] Step 2: `convert.py`: Docling `DocumentConverter` → `export_to_markdown()` → `paper.md`
- [x] Step 3: `figures.py`: figures saved as `figure-NN.png` (by figure number) at 216 dpi and linked with their captions; 40/40 correct across the samples
- [x] Step 4: `tables.py`: data tables → CSV, captions linked; known gap: merged cells land on one row
- [x] Step 5: `--formulas` flag → `do_formula_enrichment=True`. 5/6 Attention equations exact. The CodeFormulaV2 model can't use the Mac GPU (Docling drops MPS for it, and it has no MLX export), so it runs on CPU (~20 s per equation with 8 threads). On by default (`--no-formulas` to skip)
- [x] Step 5b: `superscripts.py`: sub/superscripts restored in text and tables (Attention: 122 marked, 2 skipped)
- [x] Page markers `[p. N]` for citing (`pages.py`)
- [x] Step 6: pytest suite: 13 unit tests + 12 end-to-end tests on 4 sample papers
- Later, optional: pymupdf4llm baseline for comparison, token-count report, `manifest.json`, batch mode

## Sample PDFs (in `samples/`, named `<arXiv id>.pdf`)

| ID | Paper | Tests |
|---|---|---|
| 1512.03385 | ResNet | two-column layout, vector plots, tables |
| 1706.03762 | Attention Is All You Need | equations, tables, diagrams |
| 2001.08361 | Scaling Laws | many vector matplotlib charts |
| 1606.06565 | Concrete Problems in AI Safety | text-heavy baseline |
| 1412.6980 | Adam | algorithm box, dense math |
