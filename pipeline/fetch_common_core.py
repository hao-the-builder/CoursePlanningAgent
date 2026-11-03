"""Download the Common Core material into raw/common_core/ (Phase 1, task 3).

Sources, all official and all cohort-aware:

  curriculum.html   https://uce.ust.hk/web/courses_2026/curriculum.html
                    The 2026-27 structure in prose: Foundations (18 credits:
                    HAIC, HMW, E-Comm, C-Comm), Broadening (12 credits across
                    four *non-home* areas) and Experiencing (0 credits, one
                    UxOP). Also states each program's "home" areas, which
                    decide what counts toward Broadening.

  Active_Course_List_30-credit.pdf
                    The course list per area — the source for Phase 2's
                    common_core_areas tags on each catalog course.

  Program-specific Credit Requirements2026.pdf
                    Per-program credit requirements per area. Needed because
                    the Broadening requirement differs by program.

  30-credit Common Core Curriculum with SUS area.jpg
                    The curriculum table as published. Kept as evidence; the
                    numbers are read from the prose page, not from the image.

This page is linked as "University Common Core Requirements" from every program
page in the catalog, so it is the right document for this cohort.

Usage:
    python pipeline/fetch_common_core.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402

from pipeline.fetcher import RAW, Fetcher, _utf8_stdout, render_sources  # noqa: E402

DEST = RAW / "common_core"
CURRICULUM = "https://uce.ust.hk/web/courses_2026/curriculum.html"

SOURCES = [
    (CURRICULUM, "curriculum.html",
     "2026-27 Common Core curriculum: groups, areas, credits, home areas", "text/html"),
    ("https://uce.ust.hk/web/resources/Active_Course_List_30-credit.pdf",
     "Active_Course_List_30-credit.pdf",
     "active Common Core course list by area (30-credit program)", "pdf"),
    ("https://uce.ust.hk/web/resources/Program-specific Credit Requirements2026.pdf",
     "Program-specific_Credit_Requirements_2026.pdf",
     "per-program Common Core credit requirements per area", "pdf"),
    ("https://uce.ust.hk/web/images/courses_2026/30-credit Common Core Curriculum with SUS area.jpg",
     "30-credit_Common_Core_Curriculum_with_SUS_area.jpg",
     "published curriculum table (image, evidence only)", "image"),
]

# The area abbreviations the curriculum page uses. Phase 2 maps catalog courses
# onto these; they are recorded here so the Phase 2 extractor has a checklist
# rather than inventing area names.
AREAS = {
    "HAIC": "Human-AI Co-Creation and Data Literacy (Foundations)",
    "HMW": "Habits, Mindsets, and Wellness (Foundations)",
    "E-Comm": "English Communication (Foundations)",
    "C-Comm": "Chinese Communication (Foundations)",
    "A": "Arts (Broadening)",
    "H": "Humanities (Broadening)",
    "S": "Science (Broadening)",
    "T": "Technology (Broadening)",
    "SA": "Social Analysis (Broadening)",
    "SUS": "Sustainability (Broadening)",
    "UxOP": "Experiencing: UROP / UTOP / UPOP / UCOP (0 credits)",
}


def extra_pdfs(html: str) -> list[tuple[str, str]]:
    """Any other PDF the curriculum page links, so nothing is missed."""
    soup = BeautifulSoup(html, "lxml")
    from urllib.parse import urljoin

    out: list[tuple[str, str]] = []
    known = {u for u, _, _, _ in SOURCES}
    for a in soup.find_all("a", href=True):
        url = urljoin(CURRICULUM, a["href"])
        if url.lower().endswith(".pdf") and url not in known:
            name = re.sub(r"[^A-Za-z0-9._-]+", "_", url.rsplit("/", 1)[-1])
            out.append((url, name))
    return sorted(set(out))


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)

    with Fetcher(delay=args.delay) as f:
        print("Common Core")
        for url, name, note, expect in SOURCES:
            f.save(url, DEST / name, area="common_core", note=note, expect=expect)

        page = DEST / "curriculum.html"
        if page.exists():
            found = extra_pdfs(page.read_text(encoding="utf-8", errors="replace"))
            if found:
                print("\nOther PDFs linked from the curriculum page")
                for url, name in found:
                    f.save(url, DEST / name, area="common_core",
                           note="linked from the curriculum page", expect="pdf")

        (DEST / "AREAS.md").write_text(
            "# Common Core areas, 2026-27 intake\n\n"
            "Area codes used by the curriculum page, for Phase 2 to map onto catalog\n"
            "courses. Credits and rules come from `curriculum.html` and the two PDFs in\n"
            "this folder — not from this list, which is only a checklist of names.\n\n"
            "| Code | Area |\n|---|---|\n"
            + "".join(f"| `{k}` | {v} |\n" for k, v in AREAS.items())
            + "\n## Structure\n\n"
            "- **Foundations — 18 credits.** HAIC, HMW, E-Comm, C-Comm. All compulsory;\n"
            "  recommended in year 1. HAIC is new for the 2026-27 intake.\n"
            "- **Broadening — 12 credits.** 12 credits from four *different* non-home\n"
            "  areas. A program's home area(s) depend on its school, so what counts\n"
            "  differs per program — see `Program-specific_Credit_Requirements_2026.pdf`.\n"
            "- **Experiencing — 0 credits.** Any one UxOP: UROP, UTOP, UPOP or UCOP.\n",
            encoding="utf-8")
        print(f"  wrote {(DEST / 'AREAS.md').relative_to(RAW.parent).as_posix()}")

        render_sources()
        f.report("Common Core")


if __name__ == "__main__":
    main()
