"""Parse raw/catalog/*.html into data/catalog.json (Phase 2, Part A).

Deterministic, no LLM. Produces one schema.Course per course: code, title,
credits, prereq_expr (raw text), exclusions, plus common_core_areas tagged from
the Common Core course list PDF.

Two sources, both untouched in raw/:

  raw/catalog/{SUBJECT}.html
      One page per subject from prog-crs.hkust.edu.hk/ugcourse/2026-27. Each
      course is an <li class="crse"> with crse-code / crse-title / crse-unit in
      the header and a data-row per field (Prerequisite(s), Exclusion(s), ...).

  raw/common_core/Active_Course_List_30-credit.pdf
      The area tags. Laid out in fixed columns, so areas are read by x-position
      rather than from the flowed text. An area may be cohort-conditional
      ("From 2025-26 Fall for 2025-26 and 2026-27 cohorts.", or an area that
      ended at "2024-25 Summer"), so each tag is filtered against --cohort and
      every decision is written to the report.

Three things the catalog states that the Course model needed a decision on;
all three are recorded in DECISIONS.md:

  * Credit ranges ("1-4 Credit(s)", 109 courses) -> credits = the minimum,
    credits_max = the top. Fixed-credit courses leave credits_max None.
  * Code ranges ("SOSC 1000-1010", 8 entries) -> expanded to one Course per
    code in the range, all sharing the entry's title and credits. The catalog
    publishes them as one row; a student registers for one code.
  * terms_offered stays empty for every course. The class schedule site
    disallows automated access (hard rule 7), so there is no source for it.

Usage:
    python pipeline/parse_catalog.py
    python pipeline/parse_catalog.py --cohort 2026-27 --report
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdfplumber  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from pipeline.fetcher import RAW, REPO, _utf8_stdout  # noqa: E402
from pipeline.pdf_to_text import render  # noqa: E402
from schema import Course  # noqa: E402

DATA = REPO / "data"
CATALOG_DIR = RAW / "catalog"
REQUIREMENTS_DIR = RAW / "requirements"
CC_LIST = RAW / "common_core" / "Active_Course_List_30-credit.pdf"

SINGLE_CODE = re.compile(r"^[A-Z]{2,6} \d{4}[A-Z]?$")
CODE_RANGE = re.compile(r"^([A-Z]{2,6}) (\d{4})-(\d{4})$")
UNIT = re.compile(r"^(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*Credit", re.I)


# --------------------------------------------------------------- catalog --

def expand_code_range(code: str) -> list[str]:
    """"SOSC 1000-1010" -> every code in the range. Anything else -> itself."""
    m = CODE_RANGE.match(code)
    if not m:
        return [code]
    subject, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
    return [f"{subject} {n:04d}" for n in range(lo, hi + 1)]


def parse_credits(text: str) -> tuple[float, float | None]:
    """"1-4 Credit(s)" -> (1.0, 4.0);  "3 Credit(s)" -> (3.0, None)."""
    m = UNIT.match(text.strip())
    if not m:
        raise ValueError(f"unreadable credit value {text!r}")
    lo = float(m.group(1))
    return lo, float(m.group(2)) if m.group(2) else None


def split_items(text: str) -> list[str]:
    """Split a comma-separated catalog field, keeping bracketed qualifiers.

    "LANG 1120 (prior to 2022-23), COMP 1023" keeps the parenthesis with its
    code. Free-text entries ("any COMP courses of 2000-level or above") are
    kept verbatim rather than dropped — Phase 3 decides what to do with them.
    """
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf).strip())
    return [s for s in out if s]


def parse_subject(path: Path) -> tuple[list[dict], list[str]]:
    """One subject page -> raw course dicts + a problem list."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
    rows: list[dict] = []
    problems: list[str] = []

    for li in soup.select("li.crse"):
        code_el, title_el = li.select_one(".crse-code"), li.select_one(".crse-title")
        unit_el = li.select_one(".crse-unit")
        if not (code_el and title_el and unit_el):
            problems.append(f"{path.stem}: a course header is missing code/title/unit")
            continue

        code = code_el.get_text(" ", strip=True)
        title = title_el.get_text(" ", strip=True)
        try:
            lo, hi = parse_credits(unit_el.get_text(" ", strip=True))
        except ValueError as exc:
            problems.append(f"{path.stem}: {code}: {exc}")
            continue

        fields: dict[str, str] = {}
        for row in li.select(".data-row"):
            head, data = row.select_one(".header"), row.select_one(".data")
            if head and data:
                fields[head.get_text(" ", strip=True)] = data.get_text(" ", strip=True)

        if not SINGLE_CODE.match(code) and not CODE_RANGE.match(code):
            problems.append(f"{path.stem}: unreadable course code {code!r}")
            continue

        for one in expand_code_range(code):
            rows.append({
                "code": one,
                "title": title,
                "credits": lo,
                "credits_max": hi,
                "prereq_expr": fields.get("Prerequisite(s)") or None,
                "exclusions": split_items(fields.get("Exclusion(s)", "")),
                "listed_as": code if one != code else None,
            })
    return rows, problems


# ------------------------------------------- courses only the PDFs publish --
# The requirement PDFs offer electives the 2026-27 course pages do not list:
# postgraduate 5000-level courses, and lettered sections of a parent course
# (COMP 4901B "Large Language Models" under COMP 4901 "Special Topics"). Each
# is printed there with its own title and credit value, so they are read from
# that official source rather than left out — see DECISIONS.md. Courses the
# PDFs themselves mark deleted or unapproved are skipped.

NUMBER_CELL = re.compile(r"^(\d{4}[A-Z]?)\**$")
CREDIT_CELL = re.compile(r"^(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?$")
SKIP_REMARK = re.compile(r"deleted subsequently|subject to approval", re.I)
ANY_CODE = re.compile(r"\b[A-Z]{2,6} \d{4}[A-Z]?\b")


def requirement_pdf_courses() -> tuple[dict[str, dict], set[str]]:
    """Courses printed as table rows in the requirement PDFs, and the skips."""
    found: dict[str, dict] = {}
    withdrawn: set[str] = set()

    for path in sorted(REQUIREMENTS_DIR.glob("*.pdf")):
        with pdfplumber.open(path) as pdf:
            lines = [line for page in pdf.pages for line in render(page, 3.5, 12.0)]
        for line in lines:
            cells = [c.strip() for c in line.split(" | ")]
            if SKIP_REMARK.search(line):
                withdrawn.update(ANY_CODE.findall(line))
                continue
            if len(cells) < 3:
                continue
            credit = CREDIT_CELL.match(cells[-1])
            if re.fullmatch(r"[A-Z]{2,6}", cells[0]) and len(cells) >= 4:
                number = NUMBER_CELL.match(cells[1])
                code, title = f"{cells[0]} {number.group(1)}" if number else "", 2
            elif re.match(r"^[A-Z]{2,6} ?\d{4}[A-Z]?\**$", cells[0]):
                whole = re.match(r"^([A-Z]{2,6}) ?(\d{4}[A-Z]?)", cells[0])
                code, title = f"{whole.group(1)} {whole.group(2)}", 1
            else:
                continue
            if not (code and credit):
                continue
            found.setdefault(code, {
                "code": code,
                "title": " ".join(cells[title:-1]).strip(),
                "credits": float(credit.group(1)),
                "credits_max": float(credit.group(2)) if credit.group(2) else None,
                "source": path.name,
            })
    return found, withdrawn


# ----------------------------------------------------------- common core --
# Fixed columns in Active_Course_List_30-credit.pdf, by x-position on the page.
CC_COLS = {"code": (25, 105), "credits": (580, 620), "area": (620, 697),
           "remark": (697, 920)}
CC_BODY_TOP = 175        # below the repeated page header
CC_AREAS = {"HAIC", "HMW", "CTDL", "E-Comm", "C-Comm",
            "A", "H", "S", "T", "SA", "SUS", "UxOP"}
TERM_ORDER = {"Fall": 0, "Winter": 1, "Spring": 2, "Summer": 3}
ENDS = re.compile(r"\bto\s+(20\d\d-\d\d)\s+(Fall|Winter|Spring|Summer)")


def _col(words: list[dict], bounds: tuple[int, int]) -> str:
    lo, hi = bounds
    return " ".join(w["text"] for w in words if lo <= w["x0"] < hi).strip()


def area_applies(remark: str, cohort: str) -> tuple[bool, str]:
    """Does an area tag apply to `cohort`? Returns (applies, why).

    Three wordings appear in the PDF, and nothing is assumed beyond them:
      - names cohorts  ("... for 2025-26 and 2026-27 cohorts.")  -> ours listed?
      - has an end     ("From 2022-23 Spring to 2024-25 Summer.") -> ended yet?
      - a start only, or no remark at all                         -> applies
    """
    text = remark.strip()
    if not text:
        return True, "unconditional"
    if "cohort" in text.lower():
        listed = re.findall(r"20\d\d-\d\d", text)
        ok = cohort in listed
        return ok, f"cohorts {', '.join(listed) or '?'}"
    end = ENDS.search(text)
    if end:
        ends_after = (end.group(1), TERM_ORDER[end.group(2)]) >= (cohort, 0)
        return ends_after, f"ended {end.group(1)} {end.group(2)}"
    return True, "no end date"


def parse_common_core(cohort: str) -> tuple[dict[str, list[str]], list[dict], list[str]]:
    """Area tags per course code, plus the conditional decisions and problems."""
    tags: dict[str, list[str]] = {}
    decisions: list[dict] = []
    problems: list[str] = []
    rows: list[list] = []        # [code, credits, group, [[area, remark], ...]]
    group = None

    with pdfplumber.open(CC_LIST) as pdf:
        for page in pdf.pages:
            lines: dict[int, list[dict]] = collections.defaultdict(list)
            for w in page.extract_words():
                if w["top"] >= CC_BODY_TOP:
                    lines[round(w["top"])].append(w)
            for top in sorted(lines):
                words = sorted(lines[top], key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in words)
                if text.startswith("Notes:"):
                    group = None          # footnotes follow; stop collecting
                    continue
                if "Cross-Listed" in text:
                    group = "Foundations+Broadening"
                    continue
                if "Courses in" in text and "Group" in text:
                    group = text.split("Courses in")[1].split("Group")[0].strip()
                    continue
                if group is None:
                    continue

                code = _col(words, CC_COLS["code"])
                area = _col(words, CC_COLS["area"])
                remark = _col(words, CC_COLS["remark"])
                if SINGLE_CODE.match(code):
                    rows.append([code, _col(words, CC_COLS["credits"]), group,
                                 [[area, remark]] if area else []])
                elif rows and area:
                    rows[-1][3].append([area, remark])
                elif rows and remark and rows[-1][3]:
                    rows[-1][3][-1][1] = f"{rows[-1][3][-1][1]} {remark}".strip()

    for code, _credits, _group, area_lines in rows:
        kept: list[str] = []
        for raw_area, remark in area_lines:
            for token in (a.strip() for a in raw_area.split(",")):
                name = token.split("–")[0].strip() or token   # "UxOP – UROP"
                if name not in CC_AREAS:
                    problems.append(f"{code}: unreadable area {token!r}")
                    continue
                applies, why = area_applies(remark, cohort)
                if remark.strip():
                    decisions.append({"code": code, "area": name, "kept": applies,
                                      "why": why, "remark": remark.strip()})
                if applies and name not in kept:
                    kept.append(name)
        if kept:
            tags[code] = kept
    return tags, decisions, problems


# ---------------------------------------------------------------- report --

def build(cohort: str) -> tuple[dict[str, Course], dict]:
    rows: list[dict] = []
    problems: list[str] = []
    per_subject: dict[str, int] = {}

    for path in sorted(CATALOG_DIR.glob("*.html")):
        subject_rows, subject_problems = parse_subject(path)
        rows.extend(subject_rows)
        problems.extend(subject_problems)
        per_subject[path.stem] = len(subject_rows)
        if not subject_rows:
            problems.append(f"{path.stem}: no courses parsed from the page")

    tags, decisions, cc_problems = parse_common_core(cohort)
    problems.extend(cc_problems)

    catalog: dict[str, Course] = {}
    duplicates: list[str] = []
    for row in rows:
        if row["code"] in catalog:
            duplicates.append(row["code"])
            continue
        catalog[row["code"]] = Course(
            code=row["code"], title=row["title"],
            credits=row["credits"], credits_max=row["credits_max"],
            prereq_expr=row["prereq_expr"], exclusions=row["exclusions"],
            terms_offered=[], common_core_areas=tags.get(row["code"], []))

    from_pdfs, withdrawn = requirement_pdf_courses()
    added: list[dict] = []
    for code, row in sorted(from_pdfs.items()):
        if code in catalog or code in withdrawn:
            continue
        catalog[code] = Course(code=code, title=row["title"],
                               credits=row["credits"], credits_max=row["credits_max"],
                               common_core_areas=tags.get(code, []))
        added.append(row)

    untagged = sorted(set(tags) - set(catalog))
    stats = {
        "cohort": cohort,
        "subjects": per_subject,
        "courses": len(catalog),
        "from_requirement_pdfs": added,
        "withdrawn_in_pdfs": sorted(withdrawn - set(catalog)),
        "expanded_from_ranges": sum(1 for r in rows if r["listed_as"]),
        "variable_credits": sum(1 for c in catalog.values() if c.credits_max),
        "zero_credits": sorted(c.code for c in catalog.values() if c.credits == 0),
        "with_prereq": sum(1 for c in catalog.values() if c.prereq_expr),
        "with_exclusions": sum(1 for c in catalog.values() if c.exclusions),
        "common_core_tagged": sum(1 for c in catalog.values() if c.common_core_areas),
        "common_core_not_in_catalog": untagged,
        "area_counts": collections.Counter(
            a for c in catalog.values() for a in c.common_core_areas),
        "conditional_areas": decisions,
        "duplicates": duplicates,
        "problems": problems,
    }
    return catalog, stats


def write_sources(stats: dict) -> None:
    """data/CATALOG_SOURCES.md — which courses came from which official source."""
    added = stats["from_requirement_pdfs"]
    by_pdf: dict[str, list[dict]] = collections.defaultdict(list)
    for row in added:
        by_pdf[row["source"]].append(row)

    lines = [
        "# Where each course in `data/catalog.json` comes from",
        "",
        "Generated by `pipeline/parse_catalog.py`. Do not edit by hand.",
        "",
        f"Cohort **{stats['cohort']}**, {stats['courses']} courses in total.",
        "",
        "| Source | Courses |",
        "|---|---|",
        f"| `prog-crs.hkust.edu.hk/ugcourse/{stats['cohort']}/{{SUBJECT}}` "
        f"({len(stats['subjects'])} subject pages) | {stats['courses'] - len(added)} |",
        f"| `raw/requirements/*.pdf` (printed there with a title and a credit "
        f"value, absent from the course pages) | {len(added)} |",
        "",
        "## Courses read from the requirement PDFs",
        "",
        "The course pages do not list postgraduate 5000-level courses, nor the",
        "lettered sections of a parent course (`COMP 4901B` under `COMP 4901",
        "Special Topics`). The official requirement PDFs print both as elective",
        "options with their own title and credits, so they are read from there —",
        "nothing is invented. They carry no prerequisites or exclusions, because",
        "the PDFs do not state any. **Enrolling in a 5000-level course as an",
        "undergraduate normally needs approval**; the programs that offer them",
        "say so in their `caveats`.",
        "",
        "| Course | Credits | Title | First seen in |",
        "|---|---|---|---|",
    ]
    for row in sorted(added, key=lambda r: r["code"]):
        credits = (f"{row['credits']:g}-{row['credits_max']:g}"
                   if row["credits_max"] else f"{row['credits']:g}")
        lines.append(f"| `{row['code']}` | {credits} | {row['title']} "
                     f"| `{row['source']}` |")

    skipped = stats["withdrawn_in_pdfs"]
    lines += [
        "",
        "## Courses the PDFs mention but that were deliberately left out",
        "",
        f"{len(skipped)} courses are named in a requirement PDF's own remarks as",
        "deleted, last offered in an earlier year, or \"subject to approval\".",
        "They are not in the catalog, so no rule may cite them; each affected",
        "program records the omission in its `caveats`.",
        "",
        "> " + ", ".join(f"`{c}`" for c in skipped),
        "",
    ]
    (DATA / "CATALOG_SOURCES.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", default="2026-27")
    ap.add_argument("--report", action="store_true",
                    help="also print every cohort-conditional area decision")
    args = ap.parse_args()

    catalog, stats = build(args.cohort)

    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / "catalog.json"
    out.write_text(
        json.dumps({c: catalog[c].model_dump() for c in sorted(catalog)},
                   indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    write_sources(stats)

    print(f"catalog.json: {stats['courses']} courses from "
          f"{len(stats['subjects'])} subjects ({out.stat().st_size / 1e6:.1f} MB)")
    print(f"  {len(stats['from_requirement_pdfs'])} of them read from requirement "
          f"PDFs (not on the 2026-27 course pages); "
          f"{len(stats['withdrawn_in_pdfs'])} withdrawn courses skipped")
    print(f"  {stats['with_prereq']} with a prerequisite expression, "
          f"{stats['with_exclusions']} with exclusions")
    print(f"  {stats['variable_credits']} with a credit range, "
          f"{len(stats['zero_credits'])} worth 0 credits, "
          f"{stats['expanded_from_ranges']} expanded from code ranges")
    print(f"  {stats['common_core_tagged']} tagged with a Common Core area")
    print("  areas: " + ", ".join(f"{a}={n}" for a, n in
                                  sorted(stats["area_counts"].items())))

    dropped = [d for d in stats["conditional_areas"] if not d["kept"]]
    print(f"  {len(stats['conditional_areas'])} cohort-conditional area tags, "
          f"{len(dropped)} not applicable to {args.cohort}")
    if args.report:
        for d in stats["conditional_areas"]:
            print(f"    [{'keep' if d['kept'] else 'DROP'}] {d['code']:11} "
                  f"{d['area']:7} {d['why']:28} {d['remark'][:60]}")

    if stats["common_core_not_in_catalog"]:
        print(f"  !! {len(stats['common_core_not_in_catalog'])} Common Core "
              f"courses are not in the catalog: "
              f"{', '.join(stats['common_core_not_in_catalog'])}")
    if stats["duplicates"]:
        print(f"  !! duplicate codes: {', '.join(sorted(set(stats['duplicates'])))}")
    for p in stats["problems"]:
        print(f"  !! {p}")
    if not stats["problems"]:
        print("  no parse failures")


if __name__ == "__main__":
    main()
