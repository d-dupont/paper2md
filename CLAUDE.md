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
uv run paper2md 2307.09288 --out ~/papers         # arXiv ID or link: downloads to ~/papers/2307.09288/2307.09288.pdf, then converts
uv run paper2md samples/1512.03385.pdf --ocr      # also OCR page images (only needed for scanned PDFs)
uv run paper2md samples/1512.03385.pdf --verbose  # show the libraries' progress bars/notes and per-label counts
uv run paper2md samples/1706.03762.pdf --formulas  # also equations -> LaTeX text (~20 s per equation + ~30 s model load)
uv add <pkg>        # add a runtime dependency (updates pyproject.toml + uv.lock)
uv add --dev <pkg>  # add a dev-only dependency
```

Tests:

```bash
uv run pytest                    # everything (~2 min: converts 4 sample papers, one with equations)
uv run pytest -m "not slow"      # unit tests only (~5 s, mostly importing Docling), for quick checks while editing
uv run pytest -k page_marker     # tests whose name contains "page_marker"
uv run pytest tests/test_units.py::test_ambiguous_run_is_left_alone   # one test
```

`tests/test_units.py` checks single functions on hand-made inputs. `tests/test_papers.py` (marked `slow`) runs the real command on sample papers and checks what was verified by hand: figure/caption links, table CSVs, superscripts, page markers, equations. `conftest.py` downloads missing samples from arXiv (the PDFs aren't committed) and converts each paper only once per test run. When fixing a bug, add a test that fails without the fix.

GitHub Actions (`.github/workflows/tests.yml`) runs the unit tests on every push, on Linux and Windows; the slow tests stay local. Releases: bump `version` in `pyproject.toml`, push, wait for the ✓, then `git tag -a vX.Y.Z -m ...`, `git push origin vX.Y.Z`, `gh release create vX.Y.Z`. The user works from two computers (this Mac and a Windows PC), both pushing to `main`: `git pull` before starting.

## Everyday use (outside this project)

- `~/.zshrc` has an alias: `paper2md <pdf | arXiv ID | link>` from any folder, writing to `~/papers/<id>/` (it runs this project via `uv run --project`, so the locked versions in `uv.lock` are used).
- The Claude Code skill `read-paper` lives in `skills/read-paper/SKILL.md` and is symlinked from `~/.claude/skills/read-paper`. It tells Claude to reuse `~/papers/<id>/paper.md` or convert with the full `uv run --project ...` command (aliases don't load in non-interactive shells), and how to read the format. Keep it in sync when the output format or options change.

## Architecture

- `pyproject.toml` maps the `paper2md` command to `paper2md.cli:main` (src layout, `uv_build` backend).
- `src/paper2md/cli.py` parses and validates arguments, silences the libraries unless `--verbose` (env vars like `TQDM_DISABLE`, `TRANSFORMERS_VERBOSITY`, `PYTHONWARNINGS`, which they read at import time), and only then imports `pipeline.py`. `pipeline.py` runs the steps in order and prints the summary. Conversion logic lives in the step modules, not in `cli.py`.
- `convert.py` runs Docling (OCR off by default: identical output on arXiv PDFs at half the time). `figures.py` then post-processes Docling's pictures, because Docling alone splits multi-panel figures, mislinks or drops captions, and crops off axis labels. It groups pictures by their nearest "Figure N" caption (below or beside), extends each crop down to its caption, absorbs short touching text (axis labels) into the figure and removes it from the body, re-parents the caption under the figure (otherwise the Markdown prints it twice), and names files by figure number. It also absorbs panel titles (text right above the chart as detected, within its width, at most 60% as wide) and rejoins a caption's continuation line that Docling split off (`layout.continue_caption`).
- `tables.py` drops `document_index` tables (tables of contents, lists of figures: redundant with headings and captions), skips CSV export for an uncaptioned table before the abstract (the authors' title block), links tables lacking a "Table N" caption to the nearest unclaimed one above or below (accepting plain-text "Table N:" / "Table N." blocks for numbers with no labelled caption: 8 such tables in the Llama 2 paper, 2307.09288), and writes `table-NN.csv` / `untitled-table-NN.csv`. It runs after `figures.py`, which may detach a figure caption Docling had wrongly attached to a table.
- `arxiv.py` lets the `pdf` argument be an arXiv ID or link (new- and old-style IDs, abs/pdf URLs); `cli.py` downloads it to `<out>/<id>/<id>.pdf` unless it's already there.
- `reading_order.py` fixes two-column pages where Docling reads the right column first (only ResNet's page 1 among the samples): reorders full-width blocks / left column / right column / footnotes, then repairs the paragraph joins Docling made from its wrong order (moves the next-page continuation to the page's last paragraph; rejoins a paragraph split at the column break). It only touches two-column pages (2+ paragraphs per column) with an actual inversion.
- `pages.py` adds `[p. N]` markers (the PDF's printed page label if it has one, else the page's position; when the label differs from the position both are kept, `[p. 4567 | pdf 3]`, so the quote checker in the second project can match a citation against either): a line before each item that starts on a different page than the previous item ended on (so footnotes, which Docling reads after the next page has started, get their own page), and inside paragraphs that cross a page break at the character where the new page starts (from the item's per-page `prov.charspan`, snapped forward to a space because Docling's positions drift after rejoining hyphenated words). The in-paragraph pass runs first and shifts the charspans it moves, so `figures.py` still cuts at the right place; `figures.py` drops a marker left dangling by a cut. The before-item pass runs after `figures.py`, so a cut piece doesn't count as a page start. Checked against the PDF text: 111/115 markers verified, the rest check artifacts.
- `superscripts.py` restores the sub/superscripts Docling flattens (`10-9` → `10^{-9}`, `β1` → `β_{1}`): it reads each character's baseline and font size with pdfium, marks runs smaller and raised/lowered than a nearby same-line character, and finds each run in Docling's text (or table cell) by its surrounding characters, longest unique context first; ambiguous runs are skipped. Order in `pipeline.py` matters: reading order → page markers inside paragraphs → figures → page markers before items → equations → superscripts → accents → row groups → tables. `figures.py` cuts text by character position, which inserted `^{...}` would shift, and the CSV files must be written after the marks. Stacked inline math is a known limitation (see below).
- Equations: `pipeline.convert_with_estimate` does a quick pass without the formula model to count equations, prints a time estimate, then reconverts with it. The formula model (CodeFormulaV2) is CPU-only on Macs; `convert.performance_cores()` sets Docling's threads to the performance-core count (8 threads: 77 s vs Docling's default 4: 133 s; adding efficiency cores didn't help). Docling swallows `KeyboardInterrupt` during the formula step, so `cli.stop_now` handles Ctrl+C with `os._exit(130)`; nothing is written before conversion finishes.
- `accents.py` joins spacing accents that LaTeX PDFs store before their letter (`M¨uller` → `Müller`, `Garc´ıa` → `García`, `˜B` → `B̃`); a backtick counts as a grave accent only between two letters, so code fences stay intact.
- `equations.py` crops every display equation from the pdfium render into `equations/equation-NN.png` (reading order) and links it in place. By default (no `--formulas`) the link replaces Docling's `<!-- formula-not-decoded -->`; with `--formulas` it follows the LaTeX so Claude can check it (the model garbled Attention's learning-rate equation; the image is perfectly readable). Runs after the page markers because it replaces items with location-less links.
- `write_markdown` passes `escape_underscores=False` (so `x_{1}` isn't written `x\_{1}`) and `escape_html=False` (so `<` and `&` aren't written `&lt;` and `&amp;`): the output is for Claude, not a Markdown viewer.
- `row_groups.py` spreads a first-column group label ("(A)" in Attention's Table 3) over all rows between two horizontal lines, which it reads from the PDF with pdfium because Docling records neither the span nor the lines. Only the first column (blanks elsewhere can mean "same as baseline"), only one-line labels (taller cells are usually row labels Docling merged, as in ResNet's Table 13).
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
- [x] Step 4: `tables.py`: data tables → CSV, captions linked; row-group labels spread by `row_groups.py`
- [x] Step 5: `--formulas` flag → `do_formula_enrichment=True`. 5/6 Attention equations exact. The CodeFormulaV2 model can't use the Mac GPU (Docling drops MPS for it, and it has no MLX export), so it runs on CPU (~20 s per equation with 8 threads). Off by default since equations are saved as images (`--formulas` adds LaTeX text)
- [x] Step 5b: `superscripts.py`: sub/superscripts restored in text and tables (Attention: 122 marked, 2 skipped)
- [x] Page markers `[p. N]` for citing (`pages.py`)
- [x] Step 6: pytest suite (now 41 unit tests + 18 end-to-end tests)
- [x] Leftovers: accents, footnote pages, row-group labels, two-column page order, panel titles + split captions
- Later, optional: pymupdf4llm baseline for comparison, token-count report, `manifest.json`, batch mode, cache converted papers

## Known limitations

- **Stacked inline math is left garbled, by decision.** A fraction or a big operator with limits inside a sentence (Attention: `1/√d_k` → `1 √_{dk}`, `∑_{i=1}^{d_k}` → `∑_{dk}_{i=1}`) stacks characters vertically, which `superscripts.py` reads as sub/superscripts. Only ~3 such cases exist across the 5 samples; Adam and Scaling Laws write inline fractions with a slash, which comes out fine. A fraction-bar detector (short horizontal path with text above and below) flagged ~150 "fractions", nearly all false: radical overlines, hats, underlines, lines between text rows. Each false positive would corrupt correct text, so don't add one without a way to measure false positives on many more papers. Note that a superscript and a subscript on the same letter (`W^{Q}_{i}`, `β^{t}_{1}`) are correct, not garbled.
- **Some tables stay untitled** when Docling swallows the caption into the table's cells (Llama 2's Table 41) or a table has two parts sharing one caption (Llama 2's Table 9). Their content is complete. Don't name an untitled table after a captioned neighbour on the same page: ResNet's untitled CIFAR table sits next to Table 6.
- **The formula model makes occasional mistakes** (Attention's learning-rate equation: `d_{\min odl}` for `d_{model}`; 5/6 exact). Nothing to fix on our side short of a different model.
- **Time estimates and thread choice are calibrated on an M1 Max** (`SECONDS_PER_FORMULA`, `FORMULA_MODEL_STARTUP_SECONDS`, `performance_cores()`). On other machines (e.g. the user's Windows PC: fast CPU, AMD GPU, so CPU-only for the formula model unless ROCm-on-Windows supports the card) the estimate will be off until re-measured; `performance_cores()` falls back to `os.cpu_count()` off macOS.

## Sample PDFs (in `samples/`, named `<arXiv id>.pdf`)

| ID | Paper | Tests |
|---|---|---|
| 1512.03385 | ResNet | two-column layout, vector plots, tables |
| 1706.03762 | Attention Is All You Need | equations, tables, diagrams |
| 2001.08361 | Scaling Laws | many vector matplotlib charts |
| 1606.06565 | Concrete Problems in AI Safety | text-heavy baseline |
| 1412.6980 | Adam | algorithm box, dense math |
