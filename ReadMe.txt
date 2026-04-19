Here is the problem:

There are some files produced by SAS (monospace font, space-aligned, dash-separated). Your task is to build a command-line tool that detects the tables in the file and converts them to HTML:

python sas2html.py input.txt -o output.html

you can use any other coding language.

Requirements:
Use Vibe Coding: Build the tool with the help of an AI coding assistant (Claude Code / Codex, etc.). and send me the full history, I  want to see how you collaborate with AI to get the job done.

No LLM calls in your code: Your program itself is not allowed to call any LLM API. All table parsing must be done with rules, algorithms, or traditional libraries. "Vibe Coding" means using AI while you write the code, not using AI at runtime.
Detect and output tables correctly:

Preserve merged cells across rows and columns using rowspan / colspan where appropriate.
Preserve cell alignment:
Numeric columns are typically right-aligned or centered → keep them right-aligned / centered in HTML.
Text columns are typically left-aligned → keep them left-aligned in HTML, and preserve the leading indentation (e.g., if a sub-item is indented 2–4 spaces relative to its parent, that hierarchy must still be visible in the HTML — use padding-left or retain &nbsp;).
Multi-level headers must reflect the hierarchy (parent header spanning multiple child columns).
Other contents outside of tables can be ignored.

If the text file contains multiple tables, output them to one html file.

The small.txt contains 1 table, and big.txt contains lots of tables, you can start from 1 table, then 2, then the whole big file.