"""Download official requirement PDFs into raw/requirements/ (Phase 1, task 1).

Three steps, all provenance-logged:

  1. GET the program index, https://prog-crs.hkust.edu.hk/ugprog, and read off
     every major, minor and school-requirement document for the cohort, with
     its school and department.
  2. GET each program page, /ugprog/{cohort}/{CODE}. These carry the
     "Normative Program Duration" and the total-credit sentence that Phase 2
     needs for default_years and stated_total_credits, and — crucially — the
     real href of that program's requirement PDF.
  3. Download each PDF to raw/requirements/{CODE}.pdf.

The PDF URL is *read from the page*, never constructed. The 2026-27 files do
happen to follow the 2025-26 pattern
(.../prog_crs/ug/202627/pdf/26-27comp.pdf), but CLAUDE.md Phase 1 says find the
pattern rather than guess it, and scraping the link also picks up any program
whose filename breaks the pattern.

Writes raw/requirements/_index/manifest.json: code -> title, school, kind,
duration, credits sentence and PDF URL. That is provenance, not derived course
data; Program.source_url in Phase 2 is filled from it.

Usage:
    python pipeline/fetch_requirements.py [--cohort 2026-27] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow both `python pipeline/fetch_requirements.py` (CLAUDE.md section 8 style)
# and `python -m pipeline.fetch_requirements`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402

from pipeline.fetcher import RAW, REPO as REPO_ROOT, Fetcher, _utf8_stdout, render_sources  # noqa: E402

BASE = "https://prog-crs.hkust.edu.hk"
DEST = RAW / "requirements"
INDEX = DEST / "_index"

# School sections carry a code in the page's filter controls; this maps the
# human heading to the short code CLAUDE.md uses (SENG, SSCI, SBM, HSS, AIS).
SCHOOL_CODES = {
    "School of Science": "SSCI",
    "School of Engineering": "SENG",
    "School of Business and Management": "SBM",
    "School of Humanities and Social Science": "SHSS",
    "Academy of Interdisciplinary Studies": "AIS",
    "Joint-School Program(s)": "JOINT",
}


def classify(code: str, title: str) -> str:
    if code.startswith("SREQ-"):
        return "school_requirement"
    if code.startswith("MINOR-") or title.lower().startswith("minor program"):
        return "minor"
    return "major"


def parse_index(html: str, cohort: str) -> list[dict]:
    """Pull every program out of the catalog index, with its school."""
    soup = BeautifulSoup(html, "lxml")
    programs: list[dict] = []
    for section in soup.select("div.school"):
        heading = next((d.get_text(strip=True) for d in section.find_all("div", recursive=False)), "")
        school = SCHOOL_CODES.get(heading, heading or "UNKNOWN")
        for a in section.select("li.program > a[href]"):
            href = a["href"]
            if f"/{cohort}/" not in href:
                continue
            code = (a.select_one(".program-name") or a).get_text(strip=True)
            # The title attribute is the clean title; .program-degree carries a
            # joint-offering footnote marker appended to it.
            title = (a.get("title") or "").strip() or \
                a.select_one(".program-degree").get_text(" ", strip=True)
            dept = a.select_one(".program-school")
            programs.append({
                "code": code,
                "title": title,
                "school": school,
                "school_name": heading,
                "department": dept.get_text(strip=True) if dept else "",
                "kind": classify(code, title),
                "page_url": BASE + href,
            })
    return programs


DURATION_RE = re.compile(r"Normative Program Duration\s*(\d+)\s*year", re.I)
CREDITS_RE = re.compile(r"At least\s+(\d+)\s+credits", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def pick_requirement_pdf(pdfs: list[dict], code: str, title: str, kind: str) -> dict | None:
    """Choose the program's *own* requirement PDF from the links on its page.

    Three label shapes appear in the catalog:
      major  -> "Major Requirements: BSc in Chemistry"  (the page ALSO links
                "School Requirements: School of Science", which is a different
                document shared by every program in that school)
      minor  -> just the program title, "Minor Program in Chemistry"
      school -> "SSCI School Requirements"

    "Normative Pathway Example N" PDFs are sample study plans, not requirements.
    """
    cands = [p for p in pdfs
             if "pathway" not in _norm(p["label"])
             and "/pw_" not in p["url"].lower()
             and not re.search(r"pw_[a-z-]+\.pdf$", p["url"].lower())
             and "study_pathways" not in p["url"].lower()]
    t = _norm(title)

    if kind == "school_requirement":
        for p in cands:
            if "school requirement" in _norm(p["label"]):
                return p

    # An exact "<Kind> Requirements: <title>" match is the strongest signal.
    for prefix in ("major requirements", "minor requirements", "program requirements"):
        for p in cands:
            if _norm(p["label"]) == f"{prefix}: {t}":
                return p
    for prefix in ("major requirements", "minor requirements", "program requirements"):
        for p in cands:
            if _norm(p["label"]).startswith(prefix):
                return p
    # Minors label the link with the program title alone.
    for p in cands:
        if _norm(p["label"]) == t:
            return p
    # Last resort: the filename carries the program code (26-27minor-chem.pdf).
    slug = code.lower()
    for p in cands:
        if slug in p["url"].lower():
            return p
    return None


def parse_program_page(html: str, code: str, title: str, kind: str) -> dict:
    """Read the facts Phase 2 needs, plus the requirement PDF links."""
    soup = BeautifulSoup(html, "lxml")
    for junk in soup(["script", "style"]):
        junk.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    out: dict = {}
    if m := DURATION_RE.search(text):
        out["normative_years"] = int(m.group(1))
    if m := CREDITS_RE.search(text):
        out["stated_total_credits"] = int(m.group(1))
        out["credits_quote"] = text[max(0, m.start() - 10):m.end() + 180].strip()

    pdfs = [{"url": a["href"], "label": a.get_text(" ", strip=True)}
            for a in soup.find_all("a", href=True)
            if a["href"].lower().endswith(".pdf")]

    chosen = pick_requirement_pdf(pdfs, code, title, kind)
    if chosen:
        out["pdf_url"] = chosen["url"]
        out["pdf_label"] = chosen["label"]

    # A major must satisfy its school's requirements as well as its own. Record
    # that document so Phase 2 can attach it as a Category.SCHOOL group.
    for p in pdfs:
        if "school requirement" in _norm(p["label"]) and p is not chosen:
            out["school_pdf_url"] = p["url"]
            out["school_pdf_label"] = p["label"]
            break

    out["pathway_pdfs"] = [p for p in pdfs
                           if "pathway" in _norm(p["label"])
                           or "study_pathways" in p["url"].lower()]
    out["all_pdfs"] = pdfs

    # University-level requirements linked from every program page.
    links = {}
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if any(k in label for k in ("Common Core Requirements", "English Language Requirement",
                                    "Legal Education Requirement", "Academic Regulations")):
            links[label] = a["href"]
    out["university_links"] = links
    return out


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", default="2026-27")
    ap.add_argument("--limit", type=int, default=0, help="stop after N programs (for testing)")
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    INDEX.mkdir(parents=True, exist_ok=True)

    with Fetcher(delay=args.delay) as f:
        # ---- 1. the index -------------------------------------------------
        print("Program index")
        idx_path = INDEX / "ugprog.html"
        f.save(f"{BASE}/ugprog", idx_path, area="requirements-index",
               note="program catalog index", expect="text/html")
        if not idx_path.exists():
            raise SystemExit("could not fetch the program index; nothing else to do")

        programs = parse_index(idx_path.read_text(encoding="utf-8"), args.cohort)
        if args.limit:
            programs = programs[: args.limit]
        kinds: dict[str, int] = {}
        for p in programs:
            kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
        print(f"  {len(programs)} programs for {args.cohort}: "
              + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))

        # ---- 2. program pages --------------------------------------------
        print("\nProgram pages")
        for p in programs:
            page = INDEX / f"{p['code']}.html"
            f.save(p["page_url"], page, area="requirements-index",
                   note=f"{p['code']} program page", expect="text/html")
            if page.exists():
                p.update(parse_program_page(page.read_text(encoding="utf-8"),
                                            p["code"], p["title"], p["kind"]))

        # ---- 3. the PDFs --------------------------------------------------
        print("\nRequirement PDFs")
        missing: list[dict] = []
        for p in programs:
            url = p.get("pdf_url")
            if not url:
                missing.append(p)
                continue
            p["pdf_path"] = f"raw/requirements/{p['code']}.pdf"
            status = f.save(url, DEST / f"{p['code']}.pdf", area="requirements",
                            note=f"{p['code']} — {p['title']}", expect="pdf")
            if status == "failed":
                missing.append(p)

        # ---- 3a. programs that publish no PDF -----------------------------
        # A few programs (EABU, WBB, the dual degree) do not publish a
        # requirement PDF. Where the page points at an external curriculum
        # page instead, save it so the gap is evidenced rather than asserted.
        if missing:
            print("\nPrograms with no requirement PDF — looking for an external page")
            for p in missing:
                page = INDEX / f"{p['code']}.html"
                if not page.exists():
                    continue
                soup = BeautifulSoup(page.read_text(encoding="utf-8"), "lxml")
                ext = next(
                    (a["href"] for a in soup.find_all("a", href=True)
                     if "curriculum-requirement" in a["href"].lower()
                     or "curriculum_requirement" in a["href"].lower()),
                    None)
                if not ext:
                    print(f"  {p['code']:12} no external requirements page either")
                    continue
                p["requirements_external_url"] = ext
                safe = p["code"].replace("&", "and")
                f.save(ext, INDEX / f"{safe}_requirements.html",
                       area="requirements-index",
                       note=f"{p['code']} external curriculum requirements (no PDF published)",
                       expect="text/html")

        # ---- 3b. school-requirement documents -----------------------------
        # Only SSCI and SBM appear as SREQ-* entries in the index, but every
        # school's programs link their school document. Fetch each distinct one
        # once so no major is missing its Category.SCHOOL requirements.
        print("\nSchool requirement PDFs (referenced by majors)")
        school_urls: dict[str, str] = {}
        for p in programs:
            if url := p.get("school_pdf_url"):
                school_urls.setdefault(url, p["school"])
        for url, school in sorted(school_urls.items(), key=lambda kv: kv[1]):
            name = url.rsplit("/", 1)[-1]
            dest = DEST / f"SREQ-{school}.pdf"
            if dest.exists():
                print(f"  have   {dest.relative_to(REPO_ROOT).as_posix()} ({school})")
                continue
            f.save(url, dest, area="requirements",
                   note=f"school requirements for {school} ({name})", expect="pdf")
        if not school_urls:
            print("  none referenced")

        # ---- manifest + provenance ---------------------------------------
        (INDEX / "manifest.json").write_text(
            json.dumps({"cohort": args.cohort, "programs": programs}, indent=2,
                       ensure_ascii=False),
            encoding="utf-8")
        print(f"\n  wrote {Path('raw/requirements/_index/manifest.json')}")
        render_sources()

        f.report("Requirements")
        have = sum(1 for p in programs if (DEST / f"{p['code']}.pdf").exists())
        print(f"PDFs on disk: {have}/{len(programs)}")

        # Record the gaps in the repo, not just in the console.
        why = {
            "T&M-DDP": "Dual degree program. Out of scope — CLAUDE.md section 7 marks dual "
                       "degrees unsupported. Its page only links the component majors' PDFs "
                       "(already downloaded separately) plus both school requirement docs.",
            "EABU": "2+2 joint degree with Nazarbayev University; two years of residence at "
                    "each. Publishes no requirement PDF — requirements live on an external "
                    "page, saved as `_index/EABU_requirements.html`.",
            "WBB": "World Bachelor in Business across USC, HKUST and Bocconi. The catalog "
                   "page links no requirement document at all.",
        }
        lines = [
            "# Programs with no requirement PDF\n",
            f"{have} of {len(programs)} programs in the 2026-27 catalog publish a requirement",
            "PDF. The three below do not. Each is a joint or dual-degree program whose",
            "curriculum is set outside the standard catalog, so Phase 2 should mark them",
            "`unsupported` (hard rule 5: say plainly that the program cannot be planned",
            "reliably, and do not produce a plan).\n",
            "| Code | Program | Why there is no PDF |",
            "|---|---|---|",
        ]
        for p in missing:
            lines.append(f"| `{p['code']}` | {p['title']} | "
                         f"{why.get(p['code'], 'No requirement PDF linked from its catalog page.')} |")
        lines.append("")
        (DEST / "MISSING.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"  wrote raw/requirements/MISSING.md ({len(missing)} programs)")

        if missing:
            print(f"\nNo PDF for {len(missing)} program(s):")
            for p in missing:
                print(f"  - {p['code']:14} {p['title'][:50]:52} ({p['kind']})")


if __name__ == "__main__":
    main()
