"""
sas_parser.py — Rule-based SAS monospace text → HTML table converter (core logic).

Pipeline:
  LineClassifier  — classifies each raw line
  PageStitcher    — stitches pages into logical TableBlocks
  ColumnDetector  — extracts column geometry from dash rules
  HeaderParser    — builds multi-level headers with colspan
  BodyParser      — extracts data rows and detects column alignment
  HTMLRenderer    — renders TableBlocks to HTML
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from html import escape


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Column:
    start: int
    end: int
    align: str = "left"  # 'left' | 'right' | 'center'


@dataclass
class HeaderCell:
    text: str
    colspan: int = 1


@dataclass
class BodyCell:
    text: str
    indent: int = 0  # leading spaces in first column → padding-left
    colspan: int = 1


@dataclass
class TableBlock:
    title: str
    section_label: str = ""
    header_lines: list[str] = field(default_factory=list)
    data_lines: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LineClassifier
# ---------------------------------------------------------------------------

class LineClassifier:
    _FULL_RULE = re.compile(r'^-{60,}\s*$')
    # dash rule: 2+ runs of 2+ dashes, separated by spaces
    _DASH_RULE = re.compile(r'^[\s-]*$')
    _DASH_RUN = re.compile(r'-{2,}')
    _PAGE_HEADER = re.compile(r'^[A-Z]{2,}[\w\-].*(?:FINAL|ANALYSIS|STUDY)', re.IGNORECASE)
    _PAGE_NUMBER = re.compile(r'Page\s+\d+\s+of\s+\d+', re.IGNORECASE)
    _TABLE_TITLE = re.compile(r'^TABLE\b', re.IGNORECASE)
    _SECTION_LABEL = re.compile(r'^ANALYSIS SET\s*:', re.IGNORECASE)


    @staticmethod
    def is_blank(line: str) -> bool:
        return line.strip() == ''

    @classmethod
    def is_full_rule(cls, line: str) -> bool:
        return bool(cls._FULL_RULE.match(line))

    @classmethod
    def is_dash_rule(cls, line: str) -> bool:
        stripped = line.rstrip()
        if not stripped or not cls._DASH_RULE.match(stripped):
            return False
        if cls.is_full_rule(line):
            return False
        runs = cls._DASH_RUN.findall(stripped)
        return len(runs) >= 1 and sum(len(r) for r in runs) >= 4

    @classmethod
    def is_page_header(cls, line: str) -> bool:
        # Study header: starts at col 0 with study ID pattern like "XLAB-..."
        return bool(re.match(r'^[A-Z]{2,4}-\d+', line))

    @classmethod
    def is_page_number(cls, line: str) -> bool:
        return bool(cls._PAGE_NUMBER.search(line))

    @classmethod
    def is_table_title(cls, line: str) -> bool:
        return bool(cls._TABLE_TITLE.match(line))

    @classmethod
    def is_section_label(cls, line: str) -> bool:
        return bool(cls._SECTION_LABEL.match(line))

    @classmethod
    def is_footnote_line(cls, line: str) -> bool:
        """Any col-0, non-blank, non-structural, non-rule line is a footnote candidate."""
        if not line or line[0] == ' ':
            return False
        if cls.is_table_title(line) or cls.is_page_header(line) or cls.is_section_label(line):
            return False
        if cls.is_full_rule(line) or cls.is_dash_rule(line):
            return False
        return True


# ---------------------------------------------------------------------------
# PageStitcher
# ---------------------------------------------------------------------------

class PageStitcher:
    """Converts raw lines into a list of logical TableBlocks, stitching continuation pages."""

    lc = LineClassifier()

    def stitch(self, lines: list[str]) -> list[TableBlock]:
        pages = self._split_pages(lines)
        blocks: list[TableBlock] = []
        for page in pages:
            block = self._parse_page(page)
            if block is None:
                continue
            if blocks and self._same_title(blocks[-1].title, block.title):
                # Continuation page — merge data only
                blocks[-1].data_lines.extend(block.data_lines)
            else:
                blocks.append(block)
        for b in blocks:
            b.data_lines = self._strip_trailing_blanks(b.data_lines)
        return blocks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _split_pages(self, lines: list[str]) -> list[list[str]]:
        """Split on page boundaries.

        A new page starts whenever a study-ID header line appears at col 0
        (pattern ^[A-Z]{2,4}-\\d+). The preceding blank/space line (if any)
        is consumed as the separator and not included in either page.
        """
        pages: list[list[str]] = []
        current: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if LineClassifier.is_page_header(line):
                # Trim trailing blank lines from the current page before saving
                while current and current[-1].strip() == '':
                    current.pop()
                if current:
                    pages.append(current)
                current = [line]
            else:
                current.append(line)
            i += 1
        while current and current[-1].strip() == '':
            current.pop()
        if current:
            pages.append(current)
        return pages

    def _parse_page(self, page_lines: list[str]) -> TableBlock | None:
        """Extract a TableBlock from one page's lines."""
        lc = LineClassifier

        # Find TABLE title line
        title_idx = None
        for i, line in enumerate(page_lines):
            if lc.is_table_title(line):
                title_idx = i
                break
        if title_idx is None:
            return None

        # Collect full title (may wrap to next line before full_rule)
        title_parts = [page_lines[title_idx].strip()]
        j = title_idx + 1
        while j < len(page_lines) and not lc.is_full_rule(page_lines[j]):
            if lc.is_blank(page_lines[j]):
                break
            title_parts.append(page_lines[j].strip())
            j += 1
        title = ' '.join(title_parts)

        # Skip full_rule
        if j < len(page_lines) and lc.is_full_rule(page_lines[j]):
            j += 1

        # Optional ANALYSIS SET label
        section_label = ""
        if j < len(page_lines) and lc.is_section_label(page_lines[j]):
            section_label = page_lines[j].strip()
            j += 1

        # Skip blank lines after section label
        while j < len(page_lines) and lc.is_blank(page_lines[j]):
            j += 1

        # Find the leaf dash rule — everything up to (and including) it is header_lines
        # Then the rest is data_lines
        header_lines: list[str] = []
        data_lines: list[str] = []
        remaining = page_lines[j:]

        # Find the last dash_rule in the "header zone" (before any data rows)
        leaf_rule_idx = self._find_leaf_rule_idx(remaining)

        if leaf_rule_idx is None:
            # No column ruler found — treat all remaining as data (simple/no-column table)
            data_lines = remaining[:]
        else:
            header_lines = remaining[: leaf_rule_idx + 1]
            data_lines = remaining[leaf_rule_idx + 1 :]

        # Strip footnotes from data_lines
        data_lines = self._strip_footnotes(data_lines)

        return TableBlock(
            title=title,
            section_label=section_label,
            header_lines=header_lines,
            data_lines=data_lines,
        )

    def _find_leaf_rule_idx(self, lines: list[str]) -> int | None:
        """Return the dash rule with the most dash runs — that is the leaf column ruler.
        Ties go to the first occurrence (earlier in the header wins)."""
        best_idx: int | None = None
        best_runs = 0
        for i, line in enumerate(lines):
            if LineClassifier.is_dash_rule(line):
                runs = len(LineClassifier._DASH_RUN.findall(line))
                if runs > best_runs:
                    best_runs = runs
                    best_idx = i
        return best_idx

    def _strip_footnotes(self, lines: list[str]) -> list[str]:
        """Strip footnotes by forward-scanning for the first col-0 non-structural line
        that is preceded by a blank line — that marks the footnote zone start."""
        lc = LineClassifier
        prev_blank = False
        footnote_start: int | None = None
        for i, line in enumerate(lines):
            if lc.is_blank(line):
                prev_blank = True
            elif lc.is_footnote_line(line) and prev_blank:
                footnote_start = i
                break
            else:
                prev_blank = False
        if footnote_start is None:
            result = list(lines)
            while result and lc.is_blank(result[-1]):
                result.pop()
            return result
        result = list(lines[:footnote_start])
        while result and lc.is_blank(result[-1]):
            result.pop()
        return result

    @staticmethod
    def _strip_trailing_blanks(lines: list[str]) -> list[str]:
        while lines and lines[-1].strip() == '':
            lines.pop()
        return lines

    @staticmethod
    def _same_title(a: str, b: str) -> bool:
        """Compare titles ignoring whitespace differences."""
        return ' '.join(a.split()) == ' '.join(b.split())


# ---------------------------------------------------------------------------
# ColumnDetector
# ---------------------------------------------------------------------------

class ColumnDetector:
    """Derives column geometry from dash-rule lines."""

    @staticmethod
    def dash_runs(line: str) -> list[tuple[int, int]]:
        """Return [(start, end), ...] for each contiguous '-' run (0-indexed, end inclusive)."""
        runs = []
        start = None
        for i, ch in enumerate(line):
            if ch == '-':
                if start is None:
                    start = i
            else:
                if start is not None:
                    runs.append((start, i - 1))
                    start = None
        if start is not None:
            runs.append((start, len(line) - 1))
        return runs

    def leaf_columns(self, header_lines: list[str]) -> list[Column]:
        """Extract leaf columns from the last dash_rule in header_lines."""
        lc = LineClassifier
        leaf_line = None
        for line in reversed(header_lines):
            if lc.is_dash_rule(line):
                leaf_line = line
                break
        if leaf_line is None:
            return [Column(0, 200)]  # fallback: single wide column

        runs = self.dash_runs(leaf_line)
        if not runs:
            return [Column(0, 200)]

        cols: list[Column] = []
        # If the first run doesn't start at/near col 0, add implicit label column
        if runs[0][0] > 1:
            cols.append(Column(0, runs[0][0] - 1))
        for start, end in runs:
            cols.append(Column(start, end))
        return cols

    def intermediate_rules(self, header_lines: list[str]) -> list[list[tuple[int, int]]]:
        """All dash_rule lines except the last (leaf)."""
        lc = LineClassifier
        rules = [self.dash_runs(ln) for ln in header_lines if lc.is_dash_rule(ln)]
        return rules[:-1] if len(rules) > 1 else []


# ---------------------------------------------------------------------------
# HeaderParser
# ---------------------------------------------------------------------------

class HeaderParser:
    """Builds multi-level header rows with correct colspan values."""

    # Replace dash runs in a line with spaces so the text portions remain
    _DASH_RUN_RE = re.compile(r'-{2,}')

    def build(
        self,
        header_lines: list[str],
        leaf_cols: list[Column],
    ) -> list[list[HeaderCell]]:
        """Build header rows top-to-bottom.

        Processing order: reversed (bottom-up) so that dash spans from lower lines
        are accumulated before parsing lines above them. This ensures a parent-header
        text line only gets bridged by spans from the row(s) directly below it, not
        by spans from sibling or child rows that could over-merge leaf column labels.
        """
        lc = LineClassifier

        # Identify the leaf rule line so we can skip it
        leaf_rule_line = None
        for line in reversed(header_lines):
            if lc.is_dash_rule(line):
                leaf_rule_line = line
                break

        # Walk bottom-to-top, accumulating dash spans; parse each text line with
        # only the spans from lines BELOW it
        accumulated_spans: list[tuple[int, int]] = []
        rows_bottom_up: list[list[HeaderCell]] = []

        for line in reversed(header_lines):
            if line is leaf_rule_line or lc.is_blank(line):
                continue
            if lc.is_dash_rule(line):
                # Pure dash rule (intermediate) — extract spans, don't emit a row
                for m in re.finditer(r'-{4,}', line):
                    accumulated_spans.append((m.start(), m.end() - 1))
                continue

            # Blank out inline dash runs before parsing text
            cleaned = self._DASH_RUN_RE.sub(lambda m: ' ' * len(m.group()), line)
            row = self._parse_header_row(cleaned, leaf_cols, list(accumulated_spans))
            if any(cell.text for cell in row):
                rows_bottom_up.append(row)

            # Extract any dash runs from this mixed line for lines above
            for m in re.finditer(r'-{4,}', line):
                accumulated_spans.append((m.start(), m.end() - 1))

        return list(reversed(rows_bottom_up))

    def _parse_header_row(
        self,
        line: str,
        leaf_cols: list[Column],
        intermediate_spans: list[tuple[int, int]] | None = None,
    ) -> list[HeaderCell]:
        """Map a header text line onto leaf columns, computing colspan.

        Uses connected components: two text segments belong to the same cell if
        they share at least one overlapping leaf column. intermediate_spans are
        injected as virtual segments that bridge words straddling column boundaries
        (e.g. "COMPARISON OF EFG ... SC <a>" spanning three columns).
        """
        segments = self._text_segments(line)
        if not segments:
            return [HeaderCell("") for _ in leaf_cols]

        # Append virtual segments for each intermediate span (empty text, bridges cols)
        real_count = len(segments)
        if intermediate_spans:
            for ss, se in intermediate_spans:
                segments.append((ss, se, ''))

        # For each segment, find the set of leaf-column indices it overlaps
        seg_cols: list[set[int]] = []
        for ss, se, _ in segments:
            hits = {
                ci for ci, col in enumerate(leaf_cols)
                if ss <= col.end and se >= col.start
            }
            seg_cols.append(hits)

        # Union-Find to group segments sharing leaf columns
        parent = list(range(len(segments)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                if seg_cols[i] & seg_cols[j]:
                    union(i, j)

        # Build groups: root → (set of leaf-col indices, list of REAL segment indices)
        groups: dict[int, tuple[set[int], list[int]]] = defaultdict(lambda: (set(), []))
        for i, _ in enumerate(segments):
            root = find(i)
            groups[root][0].update(seg_cols[i])
            if i < real_count:  # only real segments contribute text
                groups[root][1].append(i)

        # Map each leaf-column index to its group root
        col_to_root: dict[int, int] = {}
        for root, (col_set, _) in groups.items():
            for ci in col_set:
                col_to_root[ci] = root

        # Build the header row left-to-right, merging consecutive columns with same root
        row: list[HeaderCell] = []
        i = 0
        while i < len(leaf_cols):
            root = col_to_root.get(i)
            if root is None:
                row.append(HeaderCell("", colspan=1))
                i += 1
            else:
                span = 1
                while i + span < len(leaf_cols) and col_to_root.get(i + span) == root:
                    span += 1
                seg_list = sorted(groups[root][1])
                text = ' '.join(segments[si][2].strip() for si in seg_list)
                row.append(HeaderCell(text.strip(), colspan=span))
                i += span
        return row

    @staticmethod
    def _text_segments(line: str) -> list[tuple[int, int, str]]:
        """Return list of (start, end, text) for each contiguous non-space run."""
        segments = []
        start = None
        for i, ch in enumerate(line):
            if ch != ' ':
                if start is None:
                    start = i
            else:
                if start is not None:
                    segments.append((start, i - 1, line[start:i]))
                    start = None
        if start is not None:
            segments.append((start, len(line) - 1, line[start:]))
        return segments


# ---------------------------------------------------------------------------
# BodyParser
# ---------------------------------------------------------------------------

class BodyParser:
    """Extracts data rows and detects per-column alignment."""

    _NUMERIC = re.compile(r'^\s*[\d,.()\-/%\s]+\s*$')
    _CI_RANGE = re.compile(r'^\s*\([\d.,;\s]+\)\s*$')

    def extract_rows(
        self,
        data_lines: list[str],
        leaf_cols: list[Column],
    ) -> list[list[BodyCell]]:
        lc = LineClassifier
        raw_rows: list[tuple[list[BodyCell], str]] = []
        for line in data_lines:
            if lc.is_blank(line) or lc.is_dash_rule(line):
                continue
            raw_rows.append((self._extract_row(line, leaf_cols), line))

        merged: list[list[BodyCell]] = []
        for cells, src_line in raw_rows:
            if (merged
                    and cells[0].text
                    and all(c.text == '' for c in cells[1:])
                    and src_line and src_line[0] == ' '
                    and any(c.text for c in merged[-1][1:])):
                merged[-1][0] = BodyCell(
                    text=merged[-1][0].text + ' ' + cells[0].text,
                    indent=merged[-1][0].indent,
                )
            else:
                merged.append(cells)
        return merged

    def _extract_row(self, line: str, leaf_cols: list[Column]) -> list[BodyCell]:
        cells = []
        for ci, col in enumerate(leaf_cols):
            # Slice the column range from the line (pad if line is shorter)
            seg = line[col.start: col.end + 1] if col.start < len(line) else ''
            if ci == 0:
                # Measure indentation (leading spaces in the raw slice)
                indent = len(seg) - len(seg.lstrip(' '))
                text = seg.strip()
                cells.append(BodyCell(text=text, indent=indent))
            else:
                cells.append(BodyCell(text=seg.strip()))
        return cells

    def detect_alignment(self, rows: list[list[BodyCell]], col_idx: int) -> str:
        values = [
            row[col_idx].text
            for row in rows
            if col_idx < len(row) and row[col_idx].text
        ]
        if not values:
            return 'left'
        numeric = sum(1 for v in values if self._NUMERIC.match(v))
        ci = sum(1 for v in values if self._CI_RANGE.match(v))
        ratio = len(values)
        if numeric / ratio >= 0.75:
            return 'right'
        if ci / ratio >= 0.50:
            return 'center'
        return 'left'


# ---------------------------------------------------------------------------
# HTMLRenderer
# ---------------------------------------------------------------------------

class HTMLRenderer:
    CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    font-size: 13px;
    color: #212529;
    background: #ffffff;
    display: flex;
    min-height: 100vh;
}
/* ── Sidebar ── */
#sidebar {
    position: fixed;
    top: 0; left: 0;
    width: 240px;
    height: 100vh;
    background: #1a1a2e;
    color: #c8c8e0;
    display: flex;
    flex-direction: column;
    z-index: 100;
    font-size: 11px;
}
#sidebar-header {
    padding: 16px 14px 12px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    flex-shrink: 0;
}
#sidebar-title {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #505080;
    margin-bottom: 10px;
}
#toc-search {
    width: 100%;
    padding: 6px 9px;
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 3px;
    color: #e8e8f4;
    font-size: 11px;
    font-family: inherit;
    outline: none;
    -webkit-appearance: none;
}
#toc-search::placeholder { color: #505080; }
#toc-search:focus {
    border-color: rgba(123,140,222,0.6);
    background: rgba(255,255,255,0.11);
}
#toc-nav { padding: 6px 0 20px; overflow-y: auto; flex: 1; }
.toc-group { margin-bottom: 4px; }
.toc-group-label {
    padding: 8px 14px 3px;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #505080;
    user-select: none;
}
.toc-link {
    display: block;
    padding: 4px 12px 4px 14px;
    font-size: 10.5px;
    color: #9090b8;
    text-decoration: none;
    line-height: 1.35;
    border-left: 2px solid transparent;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    transition: background 0.1s, color 0.1s, border-color 0.1s;
}
.toc-link:hover {
    background: rgba(255,255,255,0.06);
    color: #d8d8f0;
    border-left-color: rgba(123,140,222,0.4);
}
.toc-link.active {
    border-left-color: #7b8cde;
    color: #ffffff;
    background: rgba(123,140,222,0.14);
}
.toc-link.hidden { display: none; }
.toc-group.hidden { display: none; }
/* ── Main ── */
#main {
    margin-left: 240px;
    padding: 28px 36px 60px 36px;
    flex: 1;
    min-width: 0;
    overflow-x: hidden;
}
/* ── Table section ── */
.table-section {
    margin-bottom: 44px;
    scroll-margin-top: 16px;
}
.table-title {
    font-size: 11px;
    font-weight: 600;
    color: #1a1a2e;
    margin-bottom: 2px;
    line-height: 1.4;
}
.table-subtitle {
    font-size: 10px;
    color: #666;
    margin-bottom: 8px;
    font-style: italic;
}
.table-wrap {
    overflow-x: auto;
    max-width: 100%;
}
/* ── ICH E3 / CTD publication-style table ── */
table { border-collapse: collapse; width: auto; font-size: 10.5px; }
thead tr:first-child th { border-top: 1.5px solid #1a1a2e; }
thead tr:last-child th  { border-bottom: 1.5px solid #1a1a2e; padding-bottom: 5px; }
tbody tr:last-child td  { border-bottom: 1px solid #1a1a2e; }
th {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    font-weight: 600;
    font-size: 10.5px;
    text-align: center;
    padding: 3px 12px;
    vertical-align: bottom;
    background: #ffffff;
    white-space: nowrap;
    border: none;
}
td {
    font-family: 'Courier New', Courier, monospace;
    font-size: 10.5px;
    padding: 2px 12px;
    vertical-align: top;
    border: none;
    white-space: nowrap;
}
tbody tr:nth-child(even) td { background: #f7f8fa; }
.num { text-align: right; }
.ctr { text-align: center; }
.lft { text-align: left; }
"""

    JS = """
(function () {
    var search = document.getElementById('toc-search');
    search.addEventListener('input', function () {
        var q = this.value.toLowerCase();
        document.querySelectorAll('.toc-group').forEach(function (group) {
            var vis = 0;
            group.querySelectorAll('.toc-link').forEach(function (a) {
                var show = !q || a.textContent.toLowerCase().includes(q)
                        || (a.getAttribute('title') || '').toLowerCase().includes(q);
                a.classList.toggle('hidden', !show);
                if (show) vis++;
            });
            group.classList.toggle('hidden', vis === 0);
        });
    });

    var linkMap = {};
    document.querySelectorAll('.toc-link').forEach(function (a) {
        linkMap[a.getAttribute('href').slice(1)] = a;
    });

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                Object.values(linkMap).forEach(function (a) { a.classList.remove('active'); });
                var link = linkMap[entry.target.id];
                if (link) {
                    link.classList.add('active');
                    link.scrollIntoView({ block: 'nearest' });
                }
            }
        });
    }, { rootMargin: '-5% 0px -85% 0px', threshold: 0 });

    document.querySelectorAll('.table-section').forEach(function (s) { observer.observe(s); });
}());
"""

    @staticmethod
    def _toc_prefix(title: str) -> str:
        m = re.match(r'TABLE\s+(\d+\.\d+\.\d+)', title)
        return m.group(1) if m else 'Other'

    def render_document(self, tables: list[tuple[str, str]]) -> str:
        # Build sidebar TOC grouped by section prefix
        groups: dict[str, list[tuple[int, str]]] = {}
        for i, (title, _) in enumerate(tables):
            groups.setdefault(self._toc_prefix(title), []).append((i, title))

        toc_parts: list[str] = []
        for prefix, entries in groups.items():
            toc_parts.append('<div class="toc-group">')
            toc_parts.append(f'  <div class="toc-group-label">{escape(prefix)}</div>')
            for idx, title in entries:
                toc_parts.append(
                    f'  <a class="toc-link" href="#table-{idx}"'
                    f' title="{escape(title)}">{escape(title)}</a>'
                )
            toc_parts.append('</div>')
        toc_html = '\n'.join(toc_parts)

        body_html = '\n'.join(html for _, html in tables)

        return (
            '<!DOCTYPE html>\n'
            '<html lang="en">\n'
            '<head>\n'
            '  <meta charset="utf-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '  <title>Clinical Study Tables</title>\n'
            f'  <style>{self.CSS}</style>\n'
            '</head>\n'
            '<body>\n'
            '<nav id="sidebar">\n'
            '  <div id="sidebar-header">\n'
            '    <p id="sidebar-title">Clinical Study Tables</p>\n'
            '    <input id="toc-search" type="search" placeholder="Filter tables\u2026"'
            ' autocomplete="off">\n'
            '  </div>\n'
            '  <div id="toc-nav">\n'
            f'{toc_html}\n'
            '  </div>\n'
            '</nav>\n'
            '<main id="main">\n'
            f'{body_html}\n'
            '</main>\n'
            f'<script>{self.JS}</script>\n'
            '</body>\n'
            '</html>\n'
        )

    def render_table(
        self,
        block: TableBlock,
        headers: list[list[HeaderCell]],
        rows: list[list[BodyCell]],
        leaf_cols: list[Column],
        idx: int = 0,
    ) -> str:
        parts: list[str] = []
        parts.append(f'<section class="table-section" id="table-{idx}">')
        parts.append(f'  <h2 class="table-title">{escape(block.title)}</h2>')
        if block.section_label:
            parts.append(f'  <p class="table-subtitle">{escape(block.section_label)}</p>')
        parts.append('  <div class="table-wrap">')
        parts.append('  <table>')

        if headers:
            parts.append('    <thead>')
            for hrow in headers:
                parts.append('      <tr>')
                for cell in hrow:
                    cs = f' colspan="{cell.colspan}"' if cell.colspan > 1 else ''
                    parts.append(f'        <th{cs}>{escape(cell.text)}</th>')
                parts.append('      </tr>')
            parts.append('    </thead>')

        parts.append('    <tbody>')
        for row in rows:
            parts.append('      <tr>')
            for ci, cell in enumerate(row):
                align_class = ''
                if ci < len(leaf_cols):
                    a = leaf_cols[ci].align
                    align_class = ' class="num"' if a == 'right' else (' class="ctr"' if a == 'center' else '')
                indent_style = ''
                if ci == 0 and cell.indent > 0:
                    indent_style = f' style="padding-left:{cell.indent + 2}ch"'
                cs = f' colspan="{cell.colspan}"' if cell.colspan > 1 else ''
                parts.append(f'        <td{align_class}{indent_style}{cs}>{escape(cell.text)}</td>')
            parts.append('      </tr>')
        parts.append('    </tbody>')
        parts.append('  </table>')
        parts.append('  </div>')
        parts.append('</section>')

        return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Top-level convert function (used by sas2html.py)
# ---------------------------------------------------------------------------

def convert(input_text: str) -> str:
    """Convert SAS monospace text to an HTML document string."""
    lines = input_text.splitlines()

    blocks = PageStitcher().stitch(lines)
    detector = ColumnDetector()
    header_parser = HeaderParser()
    body_parser = BodyParser()
    renderer = HTMLRenderer()

    rendered_tables: list[tuple[str, str]] = []
    for idx, block in enumerate(blocks):
        leaf_cols = detector.leaf_columns(block.header_lines)
        headers = header_parser.build(block.header_lines, leaf_cols)
        rows = body_parser.extract_rows(block.data_lines, leaf_cols)

        for ci, col in enumerate(leaf_cols):
            col.align = body_parser.detect_alignment(rows, ci)

        rendered_tables.append(
            (block.title, renderer.render_table(block, headers, rows, leaf_cols, idx=idx))
        )

    return renderer.render_document(rendered_tables)
