"""Build the document that explains the paths (Phase 5).

One `.docx` covering every path, beside the one `.xlsx` per path.

**The model writes prose and nothing else.** Every number, every course code,
every term total in this document is read from the ValidationReport and the
catalog — the same objects the spreadsheet is built from — so the two can
never disagree. If a path's prose is missing (the stub backend writes none),
the section still renders with its tables and says plainly that no commentary
was generated, rather than inventing some.

Section 1.2 fixes the shape: a title, the student's own inputs echoed back,
one section per path, and a closing "Data and limits" that carries the tier,
the source URLs, the cohort, every unresolved warning and the instruction to
check with an advisor.
"""
from __future__ import annotations

import sys
from pathlib import Path as FilePath

if __package__ in (None, ""):
    sys.path.insert(0, str(FilePath(__file__).resolve().parent.parent))

from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Pt, RGBColor  # noqa: E402

from planner.terms import sort_key  # noqa: E402
from planner.validate import is_slot  # noqa: E402
from schema import Course, Program, Tier  # noqa: E402

TIER_WORDS = {
    Tier.VERIFIED: "verified by hand against the official requirement PDF",
    Tier.AUTO: "read automatically from the official requirement PDF and "
               "auto-checked, but not yet verified by a person",
    Tier.UNSUPPORTED: "could not be read reliably from the official PDF",
}
GREY = RGBColor(0x59, 0x59, 0x59)


def _note(document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = GREY


def _table(document, headings: list[str], rows: list[list[str]]):
    table = document.add_table(rows=1, cols=len(headings))
    table.style = "Light Grid Accent 1"
    for cell, heading in zip(table.rows[0].cells, headings):
        cell.text = heading
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = value
    return table


def student_summary(document, profile, program: Program,
                    minor: Program | None) -> None:
    document.add_heading("What you told me", level=1)
    rows = [
        ["Program", f"{program.title} ({program.code})"],
        ["Intake cohort", profile.cohort or "not given"],
        ["Programme length", f"{profile.programme_years} years"],
        ["Minor", minor.title if minor else "none"],
        ["Credits per term", f"{profile.workload_min:g}–"
                             f"{profile.workload_max:g}"],
        ["Workload shape", {"even": "Even across the degree",
                            "front": "Front-loaded",
                            "back": "Back-loaded"}[profile.spread]],
        ["Terms to keep free", ", ".join(profile.free_terms) or "none"],
        ["Exchange", ", ".join(profile.exchange_terms) or "no"],
        ["Summer / winter terms",
         ("summer" if profile.use_summer else "")
         + (" and winter" if profile.use_winter else "")
         or "not used"],
    ]
    if profile.exchange and profile.exchange.host_university:
        rows.append(["Host university", profile.exchange.host_university])
    if profile.unspecified_transfer_credits:
        rows.append(["Unspecified transfer credits",
                     f"{profile.unspecified_transfer_credits:g} — these may "
                     f"count as free electives only"])
    for label, value in (("Direction", profile.direction),
                         ("Career interests", profile.career_interests),
                         ("Background", profile.background)):
        if value:
            rows.append([label, value])
    if profile.gpa_target:
        rows.append(["GPA target",
                     f"{profile.gpa_target:g} — used for workload advice "
                     f"only; no grade is predicted anywhere in this document"])
    _table(document, ["", ""], rows)


def workload_table(document, report) -> None:
    rows = []
    for term, credits in sorted(report.per_term.items(),
                                key=lambda kv: sort_key(kv[0])):
        tag = ("Earned before HKUST" if term == "Transfer" else
               "Free term" if credits == 0 else
               "Heavy" if credits >= 18 else
               "Light — check the minimum load" if credits < 12 else "Normal")
        rows.append([term, f"{credits:g}", tag])
    rows.append(["Total", f"{report.credits.with_exchange:g}",
                 f"{report.credits.confirmed:g} confirmed, "
                 f"{report.credits.exchange_pending:g} pending exchange "
                 f"approval"])
    _table(document, ["Term", "Credits", ""], rows)


def exchange_section(document, path, catalog: dict[str, Course]) -> None:
    rows = [p for p in path.plan if p.status == "exchange"]
    if not rows:
        return
    document.add_heading("Exchange", level=2)
    document.add_paragraph(
        "None of these count toward your degree until the mapping is "
        "approved. Get each one agreed with the department before you go — "
        "the credit totals above hold them separately for that reason.")
    _table(document, ["Covers", "Credits", "Host course", "Status"],
           [[f"{r.code} — {catalog[r.code].title}" if r.code in catalog
             else r.code,
             f"{catalog[r.code].credits:g}" if r.code in catalog else "?",
             r.host_course or "to be chosen",
             "approved" if r.mapping_approved else "pending approval"]
            for r in rows])


def slots_section(document, path, catalog: dict[str, Course]) -> None:
    slots = sorted({p.code for p in path.plan if is_slot(p.code)})
    if not slots:
        return
    document.add_heading("Courses you still have to choose", level=2)
    rows = []
    for slot in slots:
        suggestions = path.slot_suggestions.get(slot, [])
        named = [f"{code} — {catalog[code].title}" for code in suggestions
                 if code in catalog]
        rows.append([slot, "; ".join(named) or
                     "no suggestions were generated; search the catalog"])
    _table(document, ["Slot", "Options"], rows)


def path_section(document, path, catalog: dict[str, Course], index: int) -> None:
    document.add_heading(f"Path {index}: {path.name}", level=1)

    if path.summary:
        document.add_paragraph(path.summary)
    else:
        _note(document, "No commentary was written for this path — it was "
                        "generated without a model. The tables below are "
                        "still accurate.")

    if path.why_it_fits:
        document.add_heading("Why this one", level=2)
        for reason in path.why_it_fits:
            document.add_paragraph(reason, style="List Bullet")

    document.add_heading("Term by term", level=2)
    workload_table(document, path.report)

    exchange_section(document, path, catalog)
    slots_section(document, path, catalog)

    if path.trade_offs:
        document.add_heading("What it costs you", level=2)
        for cost in path.trade_offs:
            document.add_paragraph(cost, style="List Bullet")

    issues = path.report.errors + path.report.warnings + path.report.infos
    if issues:
        document.add_heading("Things to check", level=2)
        for issue in issues:
            mark = {"error": "Must fix", "warning": "Check",
                    "info": "Note"}[issue.severity]
            document.add_paragraph(f"{mark}: {issue.message}",
                                   style="List Bullet")


def data_and_limits(document, profile, program: Program, minor: Program | None,
                    common_core: Program | None, result) -> None:
    document.add_heading("Data and limits", level=1)
    rows = [["Cohort", profile.cohort or "not given"],
            ["Program data tier",
             f"{program.tier.value} — {TIER_WORDS[program.tier]}"
             + (f" on {program.verified_on}" if program.verified_on else "")],
            ["Program source", program.source_url]]
    if minor is not None:
        rows.append([f"Minor source ({minor.code})", minor.source_url])
    if common_core is not None:
        rows.append(["Common Core source", common_core.source_url])
    rows.append(["Academic Regulations",
                 "https://registry.hkust.edu.hk/resource-library/"
                 "academic-regulations-governing-ug-studies-2026-27"])
    _table(document, ["", ""], rows)

    caveats = list(program.caveats) + list(minor.caveats if minor else [])
    if caveats:
        document.add_heading("Conditions this plan does not check", level=2)
        document.add_paragraph(
            "The requirement PDFs state these, but no rule in the data can "
            "enforce them. Read them yourself.")
        for caveat in caveats[:20]:
            document.add_paragraph(caveat, style="List Bullet")

    unresolved = [i for path in result.paths
                  for i in (path.report.errors if path.report else [])]
    if unresolved:
        document.add_heading("Problems that were not resolved", level=2)
        document.add_paragraph(
            "These remain in the plans above. They are shown rather than "
            "hidden, and they have to be settled before you register.")
        for issue in unresolved:
            document.add_paragraph(issue.message, style="List Bullet")

    closing = document.add_paragraph()
    run = closing.add_run(
        "This is a draft to take to your academic advisor, not an "
        "authorisation. Nothing here registers you for anything, and no "
        "grade is predicted. Check it against the official requirement PDF "
        "above before you rely on it.")
    run.bold = True


def build_document(result, profile, program: Program, minor: Program | None,
                   common_core: Program | None, catalog: dict[str, Course]):
    document = Document()
    title = document.add_heading(
        f"Course plan — {program.title}", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _note(document, f"{profile.cohort} intake · "
                    f"{len(result.paths)} path(s) · data tier "
                    f"{program.tier.value} · generated for discussion with "
                    f"your academic advisor")

    student_summary(document, profile, program, minor)
    for index, path in enumerate(result.paths, 1):
        document.add_page_break()
        path_section(document, path, catalog, index)
    document.add_page_break()
    data_and_limits(document, profile, program, minor, common_core, result)
    return document


def write_document(result, profile, program: Program, minor: Program | None,
                   common_core: Program | None, catalog: dict[str, Course],
                   destination: FilePath) -> FilePath:
    document = build_document(result, profile, program, minor, common_core,
                              catalog)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(destination)
    return destination
