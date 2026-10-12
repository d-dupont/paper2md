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
uv add <pkg>        # add a runtime dependency (updates pyproject.toml + uv.lock)
uv add --dev <pkg>  # add a dev-only dependency
```

There are no tests yet (pytest arrives in Step 6). Once it does: `uv run pytest`, or `uv run pytest tests/test_convert.py::test_name` for a single test.

## Architecture

- `pyproject.toml` maps the `paper2md` command to `paper2md.cli:main` (src layout, `uv_build` backend).
- `src/paper2md/cli.py` only parses and validates arguments. Conversion logic belongs in separate modules that `cli.py` calls.
- Output layout per paper: `<out>/<pdf stem>/paper.md`, plus `figures/figure-NN.png` and `tables/table-NN.csv`.
- `samples/` (test PDFs downloaded from arXiv) and `output/` are gitignored.

## Roadmap

Commit once at the end of each step.

- [x] Step 0: scaffold (uv package, git)
- [x] Step 1: argparse CLI with input validation
- [x] Step 2: `convert.py`: Docling `DocumentConverter` → `export_to_markdown()` → `paper.md`
- [ ] Step 3: `figures.py`: `generate_picture_images=True`, `images_scale≈2`; save `doc.pictures` with `caption_text(doc)`; Markdown via `ImageRefMode.REFERENCED`
- [ ] Step 4: `tables.py`: `doc.tables` → `export_to_dataframe()` → CSV
- [ ] Step 5: `--formulas` flag → `do_formula_enrichment=True` (slow; LaTeX equations)
- [ ] Step 6: pytest tests on a small sample PDF
- Later, optional: pymupdf4llm baseline for comparison, token-count report, `manifest.json`, batch mode

## Sample PDFs (in `samples/`, named `<arXiv id>.pdf`)

| ID | Paper | Tests |
|---|---|---|
| 1512.03385 | ResNet | two-column layout, vector plots, tables |
| 1706.03762 | Attention Is All You Need | equations, tables, diagrams |
| 2001.08361 | Scaling Laws | many vector matplotlib charts |
| 1606.06565 | Concrete Problems in AI Safety | text-heavy baseline |
| 1412.6980 | Adam | algorithm box, dense math |
