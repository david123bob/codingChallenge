# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a coding challenge submission built entirely with vibe coding (AI-assisted development using Claude Code). The program itself contains no LLM or network calls — all parsing is algorithmic.

**The problem:** Clinical trial statisticians produce SAS outputs as fixed-width monospace `.txt` files. These are the official analysis results for regulatory submission (ICH E3 / CTD format). They are human-readable but not machine-readable — no structure, just aligned text. The goal is to convert them into a clean, navigable HTML document that a medical reviewer or biostatistician can open in any browser.

**The data (study XLAB-114-1807):** A Phase 3 clinical trial comparing EFG PH70 SC (an immunoglobulin therapy) vs placebo for CIDP (Chronic Inflammatory Demyelinating Polyneuropathy), a rare autoimmune nerve disease. The output contains ~110 tables covering: analysis sets, ECI (Evidence of Clinical Improvement) responder rates, time-to-event (Kaplan-Meier), Cox proportional hazards models, and safety summaries.

**The tool:**

```
python sas2html.py <input.txt> -o <output.html>
```

**Input fixtures** (do not modify): `small.txt` (1 table) and `big.txt` (~110 tables). Write outputs to `./out/` (git-ignored). Prove every feature on `small.txt` before moving to `big.txt`.

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

The output follows **ICH E3 / CTD appendix** publication style — no vertical cell borders, horizontal rules only, sans-serif labels, monospace data cells.

**Page structure:**
- Fixed left sidebar (240 px, `#1a1a2e` navy) containing a search/filter input and a grouped TOC. Each table gets an `<a>` link; links are grouped by section prefix (e.g. `14.7.1`, `14.7.5`).
- Scrollable `<main>` area to the right (`margin-left: 240px`).
- `IntersectionObserver` JS (vanilla, inline) highlights the active TOC item as the user scrolls and auto-scrolls the sidebar to keep it visible.

**Per table:**
- Wrapped in `<section class="table-section" id="table-{idx}">` for anchor linking.
- Title in `<h2 class="table-title">`, analysis-set label in `<p class="table-subtitle">`.
- Header rows in `<thead>`, data rows in `<tbody>`. `<th colspan=N>` for parent headers.
- Only the inline `padding-left` style is emitted on `<td>` (indentation). All other styling via CSS classes: `.num` (right-align), `.ctr` (center), `.lft` (left).

**Table styling (publication style):**
- `border-collapse: collapse`, no outer border, no vertical cell borders.
- `border-top: 1.5px solid #1a1a2e` on first `<thead>` row; `border-bottom: 1.5px solid` on last `<thead>` row; `border-bottom: 1px solid` on last `<tbody>` row.
- `<th>` uses system-ui/sans-serif; `<td>` uses `'Courier New', monospace`.
- Even `<tbody>` rows get `background: #f7f8fa` zebra striping.

## Module Layout

Two-file structure — keep all logic in these files, no additional modules:

```
sas2html.py     # CLI entry point (~30 lines): argparse, read input, call convert(), write output
sas_parser.py   # All parsing and rendering logic (~700 lines), 7 classes + convert()
```

| Class | Role |
|-------|------|
| `LineClassifier` | Classifies raw lines (blank, full_rule, dash_rule, page_header, table_title, footnote) |
| `PageStitcher` | Splits file into pages, extracts `TableBlock`s, stitches continuation pages |
| `ColumnDetector` | Derives leaf column geometry `(start, end)` from the dash rule with the most runs |
| `HeaderParser` | Builds multi-level header rows with `colspan` using bottom-up span accumulation |
| `BodyParser` | Slices data rows by column ranges; detects alignment; merges label-overflow continuations |
| `HTMLRenderer` | Emits the full ICH E3/CTD HTML document with sidebar TOC and publication-style tables |

`render_document` accepts `list[tuple[str, str]]` — `(title, rendered_table_html)` pairs. `render_table` takes an `idx` int used for the `id="table-{idx}"` anchor.

## Build & Test Commands

| Task | Command |
|------|---------|
| Run on small fixture | `python sas2html.py small.txt -o out/small.html` |
| Run on big fixture | `python sas2html.py big.txt -o out/big.html` |
| Lint | `ruff check .` |
| Format check | `ruff format --check .` |
| Unit + e2e tests | `pytest -q` |
| Small-only tests | `pytest -q tests/test_end_to_end_small.py` |

