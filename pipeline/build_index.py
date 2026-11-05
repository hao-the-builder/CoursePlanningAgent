"""Build data/program_index.json from the program files (Phase 2, Part E).

One row per selectable program, which is what the intake dropdown reads: code,
title, kind, school, tier, default_years, plus two things Phase 3 and Phase 6
need and Part E's list does not mention.

  `parent`      the base program, when the row is a track or option variant.
                Variants exist because a Program's groups must all be met, so
                "BSc in Mathematics - Statistics Track" is its own row.

  `home_areas`  the Common Core Broadening areas this program counts as its
                own. A student must take 12 credits from four *non-home*
                areas, so the Broadening rule in data/common_core.json cannot
                be applied without them. They are published per program, not
                per course, which is why they live here and not in the catalog.

Usage:
    python pipeline/build_index.py
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.fetcher import RAW, REPO, _utf8_stdout  # noqa: E402
from schema import Program, Tier  # noqa: E402

DATA = REPO / "data"
PROGRAMS = DATA / "programs"
MANIFEST = RAW / "requirements" / "_index" / "manifest.json"

HOME_AREA_SOURCES = [
    "https://uce.ust.hk/web/courses_2026/curriculum.html",
    "raw/common_core/Program-specific_Credit_Requirements_2026.pdf",
]

# "All programs in School of Science (SSCI): Science (S)" and the exceptions
# that follow it, read from the curriculum page and the program-specific PDF.
HOME_BY_SCHOOL = {"SSCI": ["S"], "SENG": ["T"], "SBM": ["SA"]}
HOME_BY_PROGRAM = {
    "BIEN": ["S", "T"], "CENG": ["S", "T"], "EEEN": ["S", "T"],
    "COSC": ["T"], "GCS": ["H", "SA"], "QSA": ["SA"],
    "EVMT": ["SA", "SUS"], "IDT": ["T"],
}
HOME_UNKNOWN = {
    "IIM": "The Academy states that home areas differ for individual students; "
           "contact AIS.",
    "COSC": "There may be a second home area for individual students; "
            "contact SENG.",
    "EABU": "Excluded from the \"all SBM programs\" rule on the curriculum "
            "page, and no home area is published for it.",
    "WBB": "Excluded from the \"all SBM programs\" rule on the curriculum "
           "page, and no home area is published for it.",
    "T&M-DDP": "A dual degree program takes the union of both majors' home "
               "areas; see the program-specific credit requirements.",
}


def home_areas(code: str, school: str, kind: str) -> tuple[list[str], str]:
    """The program's own Common Core areas, and a note where they are unclear."""
    if kind == "minor":
        return [], ("A minor has no home areas of its own; Broadening is "
                    "decided by the student's major.")
    if code.startswith("EXTM-"):
        return [], ("An extended major is taken alongside a first major, "
                    "whose home areas apply.")
    areas = HOME_BY_PROGRAM.get(code) or HOME_BY_SCHOOL.get(school, [])
    return areas, HOME_UNKNOWN.get(code, "")


def main() -> None:
    _utf8_stdout()
    argparse.ArgumentParser(description=__doc__).parse_args()

    catalog_entries = {e["code"]: e for e in
                       json.loads(MANIFEST.read_text(encoding="utf-8"))["programs"]}

    rows = []
    for path in sorted(PROGRAMS.glob("*.json")):
        program = Program.model_validate_json(path.read_text(encoding="utf-8"))
        entry = catalog_entries.get(program.parent or program.code, {})
        school = entry.get("school", "")
        areas, note = home_areas(program.parent or program.code, school,
                                 program.kind)
        issues = PROGRAMS / f"{program.code}.issues.md"
        rows.append({
            "code": program.code,
            "title": program.title,
            "kind": program.kind,
            "school": school,
            "school_name": entry.get("school_name", ""),
            "department": entry.get("department", ""),
            "parent": program.parent,
            "tier": program.tier.value,
            "default_years": 4,
            "stated_total_credits": program.stated_total_credits,
            "home_areas": areas,
            "home_areas_note": note,
            "groups": len(program.groups),
            "rules": sum(len(g.rules) for g in program.groups),
            "caveats": len(program.caveats),
            "unparsed_lines": len(program.unparsed_lines),
            "source_url": program.source_url,
            "issues_file": issues.name if issues.exists() else None,
        })

    index = {
        "cohort": "2026-27",
        "default_years": 4,
        "default_years_note":
            "Only 4-year programmes are supported; see DECISIONS.md.",
        "home_area_sources": HOME_AREA_SOURCES,
        "common_core": "data/common_core.json",
        "regulations": "data/regulations.json",
        "programs": rows,
    }
    out = DATA / "program_index.json"
    out.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")

    tiers = collections.Counter(r["tier"] for r in rows)
    kinds = collections.Counter(r["kind"] for r in rows)
    schools = collections.Counter(r["school"] for r in rows)
    print(f"program_index.json: {len(rows)} programs "
          f"({sum(1 for r in rows if r['parent'])} of them track/option variants)")
    print("  tiers:   " + ", ".join(f"{k}={v}" for k, v in sorted(tiers.items())))
    print("  kinds:   " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    print("  schools: " + ", ".join(f"{k or '?'}={v}"
                                    for k, v in sorted(schools.items())))
    missing = [r["code"] for r in rows if not r["home_areas"]
               and r["kind"] == "major" and not r["home_areas_note"]]
    if missing:
        print(f"  !! no home areas and no explanation: {', '.join(missing)}")


if __name__ == "__main__":
    main()
