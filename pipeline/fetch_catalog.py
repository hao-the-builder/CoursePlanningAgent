"""Download the course catalog into raw/catalog/{SUBJECT}.html (Phase 1, task 2).

Reads the subject list off https://prog-crs.hkust.edu.hk/ugcourse and saves one
page per subject from https://prog-crs.hkust.edu.hk/ugcourse/{cohort}/{SUBJECT}

The pages are server-rendered, so no browser is needed. Each course appears as

    <div class="crse-code">COMP 2011</div>
    <div class="crse-title">Programming with C++</div>
    <div class="crse-unit">4 Credit(s)</div>
    ... data rows for Exclusion(s), Prerequisite(s), Description, ILOs

which Phase 2's parse_catalog.py turns into schema.Course objects.

Note: the index links carry a trailing slash, which 302-redirects to the
canonical slash-less URL. We normalise to the canonical form so the saved
provenance URL matches what CLAUDE.md documents.

Does NOT touch the class schedule site (w5.ab.ust.hk/wcq), which sets
Disallow: / — term offerings stay a documented TODO (hard rule 7).

Usage:
    python pipeline/fetch_catalog.py [--cohort 2026-27] [--limit N]
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

BASE = "https://prog-crs.hkust.edu.hk"
DEST = RAW / "catalog"
INDEX = DEST / "_index"


def parse_subjects(html: str, cohort: str) -> list[str]:
    """Every subject code linked from the course catalog index."""
    soup = BeautifulSoup(html, "lxml")
    pat = re.compile(rf"^/ugcourse/{re.escape(cohort)}/([A-Z]{{2,6}})/?$")
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        if m := pat.match(a["href"]):
            if m.group(1) not in found:
                found.append(m.group(1))
    return sorted(found)


def count_courses(html: str) -> int:
    return len(re.findall(r'class="crse-code"', html))


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", default="2026-27")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=1.2)
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    INDEX.mkdir(parents=True, exist_ok=True)

    with Fetcher(delay=args.delay) as f:
        print("Course catalog index")
        idx = INDEX / "ugcourse.html"
        f.save(f"{BASE}/ugcourse", idx, area="catalog-index",
               note="course catalog subject index", expect="text/html")
        if not idx.exists():
            raise SystemExit("could not fetch the course index; nothing else to do")

        subjects = parse_subjects(idx.read_text(encoding="utf-8"), args.cohort)
        if args.limit:
            subjects = subjects[: args.limit]
        print(f"  {len(subjects)} subjects: {' '.join(subjects)}")

        print("\nSubject pages")
        for s in subjects:
            f.save(f"{BASE}/ugcourse/{args.cohort}/{s}", DEST / f"{s}.html",
                   area="catalog", note=f"{s} courses", expect="text/html")

        render_sources()
        f.report("Catalog")

        # A page that parsed to zero courses is a silent failure, so say so.
        print("\nCourses per subject (from the page markup):")
        total, empty = 0, []
        for s in subjects:
            p = DEST / f"{s}.html"
            if not p.exists():
                empty.append(s)
                continue
            n = count_courses(p.read_text(encoding="utf-8"))
            total += n
            if n == 0:
                empty.append(s)
            print(f"  {s:6} {n:4}")
        print(f"\n  TOTAL {total} course entries across {len(subjects)} subjects")
        if empty:
            print(f"  WARNING: no courses found for: {', '.join(empty)}")


if __name__ == "__main__":
    main()
