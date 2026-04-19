"""sas2html.py — Convert SAS monospace text files to HTML tables."""

import argparse
import sys
from pathlib import Path

from sas_parser import convert


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert SAS monospace text output to HTML tables."
    )
    parser.add_argument("input", help="Path to input .txt file")
    parser.add_argument("-o", "--output", required=True, help="Path to output .html file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = input_path.read_text(encoding="utf-8", errors="replace")
    html = convert(text)
    output_path.write_text(html, encoding="utf-8")
    print(f"Written {len(html):,} bytes -> {output_path}")


if __name__ == "__main__":
    main()
