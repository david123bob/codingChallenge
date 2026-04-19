# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Build a command-line tool (`sas2html.py`) that reads SAS monospace text output and emits a single HTML file with semantic `<table>` elements. Everything outside tables (titles, footnotes, page numbers) is ignored.

```
python sas2html.py <input.txt> -o <output.html>
```

**Input fixtures** (do not modify): `small.txt` (1 table) and `big.txt` (many tables). Write outputs to `./out/` (git-ignored). Prove every feature on `small.txt` before moving to `big.txt`.

## Hard Constraints

1. **No runtime LLM calls.** The shipped script must be 100% rule-based / algorithmic. No network calls of any kind.
2. **Vibe-coding during development only.** AI assistants (Claude Code, etc.) are used to *write* the code; the running program never talks to an AI. Preserve the full chat history as requested by the assignment.
3. **Fidelity over cleverness.** When in doubt, reproduce what the SAS file shows rather than "improving" it.
4. **Character-index parsing over regex** for anything involving column geometry. Regex is acceptable for trivial line classification (e.g. "is this line all dashes and spaces?"), but column boundaries, header spans, and cell extraction must use integer column indices derived from the dash rules.

## SAS Table Parsing Model

A SAS table in these files has this structure:

```
 Header Line 1 (optional, spans parent groups)
 Header Line 2 (column names)
 ------- ------- ------- -------     <-- dash rule; one run of '-' per column
 data    data    data    data
 data    data    data    data
 ------- ------- ------- -------     <-- optional closing rule or section rule
```

Key invariants the parser relies on:

- **Dash rules define column geometry.** A line made up only of `-` and spaces (with at least two runs of 2+ dashes) is a rule line. Each contiguous run of dashes marks the horizontal extent `[start_col, end_col]` of one leaf column.
- **The rule line immediately below the header block** is the authoritative leaf-column layout for the table that follows.
- **Multi-level headers** appear as one or more text lines *above* that rule. A parent header is centered over the child columns it spans; detect this by checking which leaf-column ranges the parent's non-space text overlaps. Parents become `<th colspan=N>`.
- **A blank line (or page-break artefact) after the data block** ends the table. A new dash-rule with a *different* column layout also ends the current table and starts a new one.

## Cell Extraction Rules

For each data line, slice by the leaf-column character ranges from the rule line:

- **Trim trailing spaces** from each cell.
- **Preserve leading spaces** — they carry hierarchy. Convert leading spaces to `padding-left` on the `<td>` (e.g. `style="padding-left: Nch"` where N = leading-space count) **or** to `&nbsp;` prefixes. Pick one approach and use it consistently.
- **Alignment detection per column** (decide once per column, not per cell):
  - Scan every body cell in that column. If ≥80% match `^-?\d[\d,.\s%]*$` (numeric, percent, currency-ish), the column is **numeric → `text-align: right`**.
  - If values are consistently centered within their column slice (roughly equal left/right padding across rows), mark as **centered**.
  - Otherwise **left-aligned**.
- **Row merging (`rowspan`)**: when a cell in column *c* is empty on row *r* AND the previous non-empty cell in column *c* is a continuation (no new value started), treat it as a vertical merge of the cell above. Emit `rowspan` on the first occurrence; skip the `<td>` on subsequent rows.
  - Be conservative: only merge when the empty cell sits between two rows that clearly belong together (e.g. the first column of that row is also blank or indented). Do not over-merge.
- **Column merging (`colspan`)**: a body cell whose text visibly spans more than one leaf-column range (its non-space text starts before the next column and ends after the previous one) emits `colspan=N`.

## HTML Output Requirements

- One `<!DOCTYPE html>` document, one `<head>` with `<meta charset="utf-8">`, one `<style>` block, one `<body>`.
- Each detected table → one `<table>` element, in source order.
- Header rows go in `<thead>`; data rows in `<tbody>`.
- Use `<th>` for header cells (with `colspan` for parent headers) and `<td>` for body cells (`rowspan`/`colspan` as detected).
- Minimal CSS in the `<style>` block: `table { border-collapse: collapse; }`, `th, td { border: 1px solid #999; padding: 2px 6px; vertical-align: top; }`, plus utility classes `.num { text-align: right; }` and `.ctr { text-align: center; }` applied per column.
- Do not emit inline styles beyond the `padding-left` used for indentation.
- Do not emit any content between tables (no titles, no footnotes) — the spec says ignore non-table content.

## Module Layout

Keep the code functional and modular. Aim for this shape:

```
sas2html.py            # CLI entry point; arg parsing; orchestrates pipeline
parser/
  __init__.py
  lines.py             # classify_line(line) -> {'blank','rule','text'}; utilities
  tables.py            # find_table_blocks(lines) -> list[TableBlock]
  columns.py           # columns_from_rule(rule_line) -> list[(start, end)]
  headers.py           # build_header_tree(header_lines, leaf_cols) -> HeaderNode
  cells.py             # extract_row(line, leaf_cols), detect_alignment, detect_rowspans
render/
  html.py              # render_document(tables) -> str
tests/
  test_lines.py
  test_columns.py
  test_headers.py
  test_cells.py
  test_end_to_end_small.py
  test_end_to_end_big.py
```

Functions preferred over classes except where a small dataclass (e.g. `Column`, `HeaderNode`, `TableBlock`) genuinely clarifies the data.

## Build & Test Commands

| Task | Command |
|------|---------|
| Run on small fixture | `python sas2html.py small.txt -o out/small.html` |
| Run on big fixture | `python sas2html.py big.txt -o out/big.html` |
| Lint | `ruff check .` |
| Format check | `ruff format --check .` |
| Unit + e2e tests | `pytest -q` |
| Small-only tests | `pytest -q tests/test_end_to_end_small.py` |

