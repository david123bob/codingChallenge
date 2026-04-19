# SAS to HTML Table Converter

A command-line tool that parses SAS monospace text output files and converts all detected tables into a single, semantic HTML file. Built entirely with rule-based parsing — no LLM calls at runtime.

## Quick Start

```bash
python sas2html.py small.txt -o out/small.html
python sas2html.py big.txt  -o out/big.html
```

Open the output in any browser. All tables from the input file appear in order.

## Usage

```
python sas2html.py <input.txt> -o <output.html>
```

| Argument | Description |
|----------|-------------|
| `input.txt` | SAS monospace text file (one or many tables) |
| `-o output.html` | Path for the generated HTML file |

## What It Handles

- **Multiple tables** in one file — all rendered to a single HTML output
- **Multi-level column headers** with correct `colspan` (e.g. a parent header spanning 3 child columns)
- **Continuation pages** — SAS repeats table headers across page breaks; these are automatically stitched into one logical table
- **Row indentation** — sub-rows indented 2–15 spaces in the source are preserved via `padding-left` in HTML
- **Column alignment** — numeric/percentage columns detected and right-aligned; CI-range columns centered; text columns left-aligned
- **Footnotes stripped** — lines at column 0 after the data body are excluded from the table

## File Structure

```
sas2html.py      # CLI entry point (~30 lines)
sas_parser.py    # All parsing and rendering logic
small.txt        # Single-table fixture
big.txt          # Multi-table fixture (~110 tables)
out/             # Generated HTML outputs (git-ignored)
```

### sas_parser.py classes

| Class | Role |
|-------|------|
| `LineClassifier` | Classifies each raw line (blank, full rule, dash rule, page header, table title, etc.) |
| `PageStitcher` | Splits the file into pages, extracts `TableBlock` objects, stitches continuation pages |
| `ColumnDetector` | Extracts column geometry `(start, end)` from the leaf dash-rule line |
| `HeaderParser` | Builds multi-level header rows with `colspan` using bottom-up span accumulation |
| `BodyParser` | Slices data rows by column ranges; detects per-column alignment |
| `HTMLRenderer` | Emits `<!DOCTYPE html>` with `<thead>`/`<tbody>`, `colspan`, and `padding-left` |

## How the SAS Format Is Parsed

Every page in a SAS file follows this structure:

```
STUDY-ID - FINAL ANALYSIS                          <timestamp>
                                                   Page N of M
TABLE X.X.X.X : TITLE
--------------------------------------------------------------------------
ANALYSIS SET: LABEL                    (optional)

[header rows]
[leaf dash rule]   ← column boundaries derived from this line
[data rows]

FOOTNOTE TEXT...   ← excluded from table output
```

**Key rules:**
- A 60+ dash line after the TABLE title is a section separator, not a column ruler
- The last spaced-dash-group line before data rows defines leaf column positions
- Text above intermediate dash rules spans those columns → `colspan`
- Continuation pages (same TABLE title on the next page) are merged automatically
- Footnotes start at column 0 with uppercase text after the data body

## Development

```bash
# Lint
python -m ruff check .

# Run on fixtures
python sas2html.py small.txt -o out/small.html
python sas2html.py big.txt  -o out/big.html
```

## Assignment Context

This tool was built as a coding challenge using vibe coding — AI-assisted development with Claude Code. The program itself contains no LLM or network calls; all parsing is algorithmic. The full AI chat history is preserved alongside the code as required by the assignment.
