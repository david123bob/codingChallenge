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
    # Footnote: starts at col 0 with capital letter, bracket, or typical footnote starters
    _FOOTNOTE_START = re.compile(r'^[A-Z\[\*]')

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
        """A footnote starts at column 0 with uppercase/bracket (not a table title)."""
        if not line or line[0] == ' ':
            return False
        if cls.is_table_title(line) or cls.is_page_header(line) or cls.is_section_label(line):
            return False
        return bool(cls._FOOTNOTE_START.match(line))


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
        """Find the index of the last dash_rule that appears before actual data rows.
        Strategy: scan forward; the last dash_rule before a non-blank, non-rule line is the leaf."""
        lc = LineClassifier
        last_rule = None
        for i, line in enumerate(lines):
            if lc.is_dash_rule(line):
                last_rule = i
            elif not lc.is_blank(line) and last_rule is not None:
                # We hit a data line after seeing at least one rule
                break
        return last_rule

    def _strip_footnotes(self, lines: list[str]) -> list[str]:
        """Remove trailing footnote lines (col-0 uppercase/bracket after the body)."""
        lc = LineClassifier
        # Find last non-blank data line index
        result = list(lines)
        # Walk backwards from end, dropping footnote+blank runs
        while result and (lc.is_blank(result[-1]) or lc.is_footnote_line(result[-1])):
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
        rows = []
        for line in data_lines:
            if lc.is_blank(line) or lc.is_dash_rule(line):
                continue
            rows.append(self._extract_row(line, leaf_cols))
        return rows

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
        body { font-family: sans-serif; padding: 1em; }
        h2 { font-size: 0.95em; color: #444; margin: 1.5em 0 0.2em; }
        table { border-collapse: collapse; margin-bottom: 2em; }
        th, td {
            border: 1px solid #999;
            padding: 3px 8px;
            vertical-align: top;
            font-family: monospace;
            font-size: 0.82em;
            white-space: nowrap;
        }
        th { background: #f0f0f0; text-align: center; }
        .num { text-align: right; }
        .ctr { text-align: center; }
        .lft { text-align: left; }
    """

    def render_document(self, tables: list[str]) -> str:
        body = '\n'.join(tables)
        return (
            '<!DOCTYPE html>\n'
            '<html lang="en">\n'
            '<head>\n'
            '  <meta charset="utf-8">\n'
            '  <title>SAS Tables</title>\n'
            f'  <style>{self.CSS}</style>\n'
            '</head>\n'
            '<body>\n'
            f'{body}\n'
            '</body>\n'
            '</html>\n'
        )

    def render_table(
        self,
        block: TableBlock,
        headers: list[list[HeaderCell]],
        rows: list[list[BodyCell]],
        leaf_cols: list[Column],
    ) -> str:
        parts: list[str] = []

        # Title + section label as heading
        parts.append(f'<h2>{escape(block.title)}</h2>')
        if block.section_label:
            parts.append(f'<p style="font-size:0.85em;color:#555">{escape(block.section_label)}</p>')

        parts.append('<table>')

        # thead
        if headers:
            parts.append('  <thead>')
            for hrow in headers:
                parts.append('    <tr>')
                for cell in hrow:
                    cs = f' colspan="{cell.colspan}"' if cell.colspan > 1 else ''
                    parts.append(f'      <th{cs}>{escape(cell.text)}</th>')
                parts.append('    </tr>')
            parts.append('  </thead>')

        # tbody
        parts.append('  <tbody>')
        for row in rows:
            parts.append('    <tr>')
            for ci, cell in enumerate(row):
                align_class = ''
                if ci < len(leaf_cols):
                    a = leaf_cols[ci].align
                    align_class = ' class="num"' if a == 'right' else (' class="ctr"' if a == 'center' else '')
                indent_style = ''
                if ci == 0 and cell.indent > 0:
                    indent_style = f' style="padding-left:{cell.indent + 2}ch"'
                cs = f' colspan="{cell.colspan}"' if cell.colspan > 1 else ''
                parts.append(f'      <td{align_class}{indent_style}{cs}>{escape(cell.text)}</td>')
            parts.append('    </tr>')
        parts.append('  </tbody>')
        parts.append('</table>')

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

    rendered_tables: list[str] = []
    for block in blocks:
        leaf_cols = detector.leaf_columns(block.header_lines)
        headers = header_parser.build(block.header_lines, leaf_cols)
        rows = body_parser.extract_rows(block.data_lines, leaf_cols)

        # Detect and apply alignment per column
        for ci, col in enumerate(leaf_cols):
            col.align = body_parser.detect_alignment(rows, ci)

        rendered_tables.append(renderer.render_table(block, headers, rows, leaf_cols))

    return renderer.render_document(rendered_tables)
