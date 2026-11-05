"""Print a requirement PDF as clean text (Phase 2, Part B, task 1).

    python pipeline/pdf_to_text.py raw/requirements/COMP.pdf

Why not pdfplumber's extract_text(): the requirement PDFs are three-column
tables (course code | title | credits) and plain extraction mangles them in
two ways. It drops the space between cells, so "COMP 2711 OR COMP 2711H"
arrives as "COMP 2711 ORCOMP 2711H"; and when a title wraps, the title and its
credit value land on different output lines, so the credits appear to belong
to the wrong course.

This rebuilds rows from word positions instead:

  * words are clustered into visual rows (y within --row-tol points);
  * within a row, a gap wider than --cell-gap points starts a new cell, and
    cells are printed separated by " | ", so columns stay aligned and no
    space between words is ever lost;
  * a row that is one cell starting in the title column is a wrapped line and
    is folded back into the row above it;
  * a row that is one cell starting at the left margin is a heading or a
    paragraph and is printed as it stands.

The output is for reading — by a person or by Claude Code while writing
data/programs/{CODE}.json — not for machine parsing. Nothing is dropped:
every word on the page appears in the output exactly once.

Usage:
    python pipeline/pdf_to_text.py raw/requirements/COMP.pdf
    python pipeline/pdf_to_text.py raw/requirements/COMP.pdf --pages 2-3
    python pipeline/pdf_to_text.py raw/common_core/*.pdf --raw
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdfplumber  # noqa: E402

from pipeline.fetcher import _utf8_stdout  # noqa: E402

TITLE_COL = 0.28     # fraction of page width where the title column starts
RIGHT_COL = 0.70     # ... and where the right-hand (credits) column starts

# The PDFs set "OR" and "AND" hard against what follows, so the text really
# does read "COMP 2711 ORCOMP 2711H". Only re-space a keyword that is glued to
# a bracket or a course code — "ORGANIC" must survive untouched.
GLUED = re.compile(r"(?<![A-Za-z])(AND|OR)(?=(?:[A-Z]{2,6} ?\d{3,4}[A-Z]?\b|[(\[]))")


def unglue(text: str) -> str:
    return GLUED.sub(r"\1 ", text)


# The only thing the renderer drops: the two-line heading that sits above the
# credits column on every requirement page. Nothing else is ever discarded.
COL_HEADER = {"Credit(s)", "attained", "Minimum", "credit(s)", "required"}


def parse_pages(spec: str | None, total: int) -> range:
    if not spec:
        return range(total)
    lo, _, hi = spec.partition("-")
    return range(int(lo) - 1, int(hi or lo))


def rows(page, row_tol: float,
         cell_gap: float) -> list[tuple[list[str], list[float], float, float]]:
    """Visual rows: (cell texts, each cell's left edge, the row's, the last cell's)."""
    words = sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"]))
    clusters: list[list[dict]] = []
    for w in words:
        if clusters and abs(w["top"] - clusters[-1][0]["top"]) <= row_tol:
            clusters[-1].append(w)
        else:
            clusters.append([w])

    out: list[list[str]] = []
    for cluster in clusters:
        line = sorted(cluster, key=lambda w: w["x0"])
        cells: list[list[dict]] = [[line[0]]]
        for prev, word in zip(line, line[1:]):
            (cells.append([word]) if word["x0"] - prev["x1"] > cell_gap
             else cells[-1].append(word))
        out.append(([" ".join(w["text"] for w in cell) for cell in cells],
                    [cell[0]["x0"] for cell in cells],
                    line[0]["x0"], cells[-1][0]["x0"]))
    return out


def render(page, row_tol: float, cell_gap: float) -> list[str]:
    title_x, right_x = page.width * TITLE_COL, page.width * RIGHT_COL
    out: list[tuple[list[str], list[float]]] = []

    for cells, xs, left, last in rows(page, row_tol, cell_gap):
        if len(cells) == 1:
            if left >= right_x and cells[0] in COL_HEADER:
                continue                        # "Credit(s)" over "attained"
            if left >= title_x and out:
                _fold(out[-1], cells[0], left)
                continue
            out.append(([cells[0]], xs))
            continue
        # A code cell too wide for its column wraps onto the next row, which
        # then carries no credit value: "ELEC/IEDA/" above "MATH | 2540 OR ..."
        if last < right_x and out and out[-1][0][0].endswith("/"):
            out[-1][0][0] += cells[0]
            for cell, x in zip(cells[1:], xs[1:]):
                _fold(out[-1], cell, x)
            continue
        out.append((["  " * (left >= title_x) + cells[0], *cells[1:]], xs))

    return [unglue(" | ".join(cells)) for cells, _ in out]


def _fold(line: tuple[list[str], list[float]], text: str, x: float) -> None:
    """Append a wrapped line to the cell of the column it starts in."""
    cells, xs = line
    i = max((j for j, cx in enumerate(xs) if cx <= x + 1), default=len(cells) - 1)
    cells[min(i, len(cells) - 1)] += f" {text}"


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+", type=Path)
    ap.add_argument("--pages", help="e.g. 2 or 2-4 (1-based, inclusive)")
    ap.add_argument("--raw", action="store_true",
                    help="pdfplumber's own text, for comparison")
    ap.add_argument("--row-tol", type=float, default=3.5)
    ap.add_argument("--cell-gap", type=float, default=12.0)
    args = ap.parse_args()

    for path in args.pdf:
        if len(args.pdf) > 1:
            print(f"\n{'=' * 70}\n{path}\n{'=' * 70}")
        with pdfplumber.open(path) as pdf:
            for i in parse_pages(args.pages, len(pdf.pages)):
                page = pdf.pages[i]
                print(f"\n----- page {i + 1} of {len(pdf.pages)} -----")
                if args.raw:
                    print(page.extract_text() or "")
                else:
                    print("\n".join(render(page, args.row_tol, args.cell_gap)))


if __name__ == "__main__":
    main()
