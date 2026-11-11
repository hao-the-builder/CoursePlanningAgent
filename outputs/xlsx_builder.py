"""Build the student's workbook (Phase 5).

One workbook per path, two sheets, laid out to match
`samples/sample_course_plan_v4.xlsx`.

**Every number is an Excel formula.** Not one total is computed in Python and
written as a value. The student can delete a course, change a credit value or
retype a status, and both sheets follow. That is the whole point of the
format: a plan that goes stale the moment it is edited is worth less than a
spreadsheet the student owns.

Only formulas that old Excel and Google Sheets both understand are used —
`SUM`, `SUMIFS`, `SUMPRODUCT`, `IF`, `MAX`. No `XLOOKUP`, no `FILTER`, no
dynamic arrays.

The Progress sheet adds up the Course Plan rows by filtering on the Status
column, which is blank on term-header and term-total rows. That is what keeps
those rows out of the arithmetic, and it is why the status dropdown matters:
a status the formulas do not know about silently drops a course from every
total.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path as FilePath

if __package__ in (None, ""):
    sys.path.insert(0, str(FilePath(__file__).resolve().parent.parent))

from openpyxl import Workbook  # noqa: E402
from openpyxl.formatting.rule import FormulaRule  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

from planner.allocate import Allocation, group_demand  # noqa: E402
from planner.terms import sort_key, term_sequence  # noqa: E402
from planner.validate import (ValidationReport, is_slot, row_credits,
                              slot_label)  # noqa: E402
from schema import Category, Course, NAreas, PlannedCourse, Program, Tier  # noqa: E402

FONT = "Arial"
COLUMNS = ["Semester", "Course Code", "Course Name", "Credits", "Status",
           "Common Core", "Major Requirements", "Minor Requirements", "Notes"]
NC = len(COLUMNS)
WIDTHS = [11, 16, 50, 9, 11, 16, 22, 19, 40]
STATUSES = {"taken": "Taken", "current": "Current", "transfer": "Transfer",
            "planned": "Planned", "exchange": "Exchange"}
DONE = ("Taken", "Current", "Transfer")

fill = lambda colour: PatternFill("solid", start_color=colour)  # noqa: E731
H_FILL, TERM_F, SUBT = fill("1F3864"), fill("BDD7EE"), fill("F2F2F2")
EX_HDR, EX_ROW, TOT, SEC = fill("F8CBAD"), fill("FCE4D6"), fill("1F3864"), fill("D9E1F2")
BAN, OK, NO, WARN = fill("FFF2CC"), fill("C6EFCE"), fill("FFC7CE"), fill("FFEB9C")
CC_F, MJ_F, MN_F, TR_F = fill("E2EFDA"), fill("DDEBF7"), fill("FFF2CC"), fill("EDEDED")
_thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
N = Font(name=FONT)
B = Font(name=FONT, bold=True)
BLUE = Font(name=FONT, color="0000FF")
HDR = Font(name=FONT, bold=True, color="FFFFFF")

TIER_WORDS = {
    Tier.VERIFIED: "verified against the official PDF",
    Tier.AUTO: "auto-extracted from the official PDF, not yet verified",
    Tier.UNSUPPORTED: "could not be read reliably",
}


@dataclass
class Row:
    """One line of the Course Plan sheet."""
    term: str
    code: str
    name: str
    credits: float | str
    status: str
    common_core: str = ""
    major: str = ""
    minor: str = ""
    note: str = ""


def _slot_row(entry: PlannedCourse, allocation: Allocation) -> Row:
    """A course the student has not chosen yet."""
    kind = entry.code.split(":", 1)[1] if ":" in entry.code else "any"
    free = kind.upper().startswith("FREE")
    # A slot carries its own credits, and they have to reach the Credits
    # column: the term totals are SUMIFS over it, so a blank here would make
    # every total on the sheet disagree with the validator.
    return Row(term=entry.term,
               code="Free elective" if free else f"CC — {kind}",
               name=slot_label(entry.code),
               credits=row_credits(entry, {}) or "",
               status="Planned",
               note=entry.note or "Slot: options are in the document")


def _exchange_row(entry: PlannedCourse, course: Course | None) -> Row:
    """An exchange row: the host course, and the requirement it should cover."""
    requirement = course.title if course else entry.code
    return Row(term=entry.term, code="Host course",
               name=f"{entry.host_course or 'Host course'}  ≈ {requirement}",
               credits=course.credits if course else "", status="Exchange",
               note=entry.note or "Pending approval of the credit mapping")


def plan_rows(path_plan: list[PlannedCourse], allocation: Allocation,
              catalog: dict[str, Course]) -> list[Row]:
    rows: list[Row] = []
    for entry in path_plan:
        course = catalog.get(entry.code)
        if is_slot(entry.code):
            row = _slot_row(entry, allocation)
        elif entry.status == "exchange":
            row = _exchange_row(entry, course)
        else:
            row = Row(term=entry.term, code=entry.code,
                      name=course.title if course else entry.code,
                      credits=course.credits if course else "",
                      status=STATUSES.get(entry.status, "Planned"),
                      note=entry.note)
        fillings = allocation.fills.get(entry.code)
        if fillings:
            row.common_core = fillings.common_core or ""
            row.major = fillings.major or ""
            row.minor = fillings.minor or ""
        rows.append(row)
    return rows


def _year_of(label: str) -> str:
    """"Y2 Fall" -> "YEAR 2", the way the sample workbook heads a term."""
    from planner.terms import parse_label

    try:
        year, _ = parse_label(label)
    except ValueError:
        return label.upper()
    return f"YEAR {year}" if year else "BEFORE HKUST"


def term_blocks(rows: list[Row], profile, years: int) -> list[tuple]:
    """(label, heading, kind, rows) for every term, in order, free ones too."""
    by_term: dict[str, list[Row]] = {}
    for row in rows:
        by_term.setdefault(row.term, []).append(row)

    sequence = term_sequence(profile.cohort or "2026-27", years,
                             use_summer=profile.use_summer or
                             any(t.endswith("Summer") for t in by_term),
                             use_winter=profile.use_winter or
                             any(t.endswith("Winter") for t in by_term))
    labels = [t.label for t in sequence]
    calendars = {t.label: t.calendar.upper() for t in sequence}
    if "Transfer" in by_term:
        labels.insert(0, "Transfer")
    for extra in by_term:
        if extra not in labels:
            labels.append(extra)

    away = set(profile.exchange_terms)
    blocks = []
    for label in sorted(dict.fromkeys(labels), key=sort_key):
        here = by_term.get(label, [])
        if label == "Transfer":
            kind, heading = "transfer", "BEFORE HKUST · TRANSFER CREDITS"
        elif label in away:
            host = (profile.exchange.host_university if profile.exchange
                    else None) or "host university TBD"
            kind = "exchange"
            heading = (f"{_year_of(label)} · {calendars.get(label, label)}"
                       f" · ✈️ EXCHANGE ({host})")
        else:
            season = label.split()[-1] if " " in label else ""
            kind = ("free" if not here else
                    "summer" if season == "Summer" else
                    "winter" if season == "Winter" else "regular")
            heading = f"{_year_of(label)} · {calendars.get(label, label)}"
        blocks.append((label, heading, kind, here))
    return blocks


def _banner(sheet, columns: int, banner: str, settings: str) -> None:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1,
                      end_column=columns)
    cell = sheet.cell(1, 1, banner)
    cell.font = Font(name=FONT, bold=True, color="9C5700")
    cell.fill = BAN
    cell.alignment = Alignment(wrap_text=True, vertical="center")
    sheet.row_dimensions[1].height = 30
    sheet.merge_cells(start_row=2, start_column=1, end_row=2,
                      end_column=columns)
    sheet.cell(2, 1, settings).font = Font(name=FONT, italic=True,
                                           color="404040")


def _header(sheet, row: int, names: list[str]) -> None:
    for index, name in enumerate(names, 1):
        cell = sheet.cell(row, index, name)
        cell.font, cell.fill, cell.border = HDR, H_FILL, BOX
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)


def banner_text(program: Program, profile, path_name: str) -> str:
    return (f"{path_name} — {program.title} ({program.code}), "
            f"{profile.cohort} intake. Data tier: {program.tier.value} "
            f"({TIER_WORDS[program.tier]}). Check this plan with your "
            f"academic advisor before you rely on it.")


def settings_text(profile, years: int) -> str:
    spread = {"even": "Even", "front": "Front-loaded",
              "back": "Back-loaded"}[profile.spread]
    bits = [f"Programme = {years} years", f"Workload = {spread}",
            f"Exchange = {', '.join(profile.exchange_terms) or 'none'}",
            f"Keep free = {', '.join(profile.free_terms) or 'none'}",
            f"Transfer = {profile.unspecified_transfer_credits:g} unspecified "
            f"credits" if profile.unspecified_transfer_credits
            else "Transfer = none",
            f"Target load = {profile.workload_min:g}–{profile.workload_max:g}"]
    return "Plan settings:  " + "  ·  ".join(bits)


# --------------------------------------------------------- Course Plan --

def course_plan_sheet(sheet, rows: list[Row], profile, program: Program,
                      years: int, path_name: str) -> tuple[int, list[int], dict]:
    """Write the sheet. Returns (last course row, term-total rows, by kind)."""
    _banner(sheet, NC, banner_text(program, profile, path_name),
            settings_text(profile, years))
    _header(sheet, 3, COLUMNS)

    at = 4
    totals: list[int] = []
    kinds: dict[str, list[int]] = {}

    for label, heading, kind, here in term_blocks(rows, profile, years):
        sheet.merge_cells(start_row=at, start_column=1, end_row=at,
                          end_column=NC)
        cell = sheet.cell(at, 1, heading)
        cell.font = B
        cell.fill = EX_HDR if kind == "exchange" else TERM_F
        at += 1
        start = at

        if not here:
            sheet.cell(at, 1, label).font = N
            sheet.cell(at, 3, "No courses — free term").font = Font(
                name=FONT, italic=True)
            for column in range(1, NC + 1):
                sheet.cell(at, column).border = BOX
            at += 1

        for row in here:
            values = [label, row.code, row.name, row.credits, row.status,
                      row.common_core, row.major, row.minor, row.note]
            for index, value in enumerate(values, 1):
                cell = sheet.cell(at, index, value if value != "" else None)
                cell.font, cell.border = N, BOX
            sheet.cell(at, 4).alignment = Alignment(horizontal="center")
            if kind == "transfer":
                for column in range(1, 6):
                    sheet.cell(at, column).fill = TR_F
            if kind == "exchange":
                for column in range(1, 6):
                    sheet.cell(at, column).fill = EX_ROW
            if row.common_core:
                sheet.cell(at, 6).fill = CC_F
            if row.major:
                sheet.cell(at, 7).fill = MJ_F
            if row.minor:
                sheet.cell(at, 8).fill = MN_F
            at += 1

        end = at - 1
        sheet.cell(at, 3, f"{label} total").font = B
        sheet.cell(at, 4, f"=SUM(D{start}:D{end})").font = B
        sheet.cell(at, 4).alignment = Alignment(horizontal="center")
        for column in "FGH":
            cell = sheet[f"{column}{at}"]
            cell.value = (f'=SUMPRODUCT(D{start}:D{end},'
                          f'--({column}{start}:{column}{end}<>""))')
            cell.font, cell.number_format = B, '0" cr"'
        sheet.cell(at, 9, "=" + _load_tag(kind, at)).font = B
        for column in range(1, NC + 1):
            sheet.cell(at, column).fill = SUBT
            sheet.cell(at, column).border = BOX
        totals.append(at)
        kinds.setdefault(kind, []).append(at)
        at += 1

    last = at - 1
    return last, totals, kinds


def _load_tag(kind: str, row: int) -> str:
    """The load tag formula, so the label follows the student's edits."""
    if kind == "transfer":
        return '"Earned before HKUST"'
    if kind == "exchange":
        return '"✈️ Exchange: credits pending approval"'
    if kind in ("summer", "winter"):
        return (f'IF(D{row}=0,"No credit-bearing courses",'
                f'"{kind.capitalize()} term")')
    return (f'IF(D{row}=0,"🟢 Free term",IF(D{row}>=18,"🔴 Heavy",'
            f'IF(D{row}<12,"🟡 Light — check minimum load","Normal")))')


def programme_total(sheet, at: int, totals: list[int], kinds: dict,
                    years: int, first_term: str, last_term: str,
                    needed: float) -> int:
    """The bottom line: every figure a sum of the term totals above it."""
    add = lambda column: "=" + "+".join(f"{column}{r}" for r in totals)  # noqa: E731
    sheet.cell(at, 1, "PROGRAMME TOTAL").font = HDR
    sheet.cell(at, 3, f"{years}-year plan · {first_term} → {last_term} · "
                      f"graduation needs {needed:g}").font = HDR
    sheet.cell(at, 4, add("D")).font = HDR
    for column in "FGH":
        cell = sheet[f"{column}{at}"]
        cell.value, cell.font, cell.number_format = add(column), HDR, '0" cr"'
    sheet.cell(at, 5, f'=IF(D{at}>={needed:g},"✅ ≥{needed:g}",'
                      f'"❌ <{needed:g}")').font = HDR

    transfer = kinds.get("transfer", [])
    exchange = kinds.get("exchange", [])
    part = lambda rs: ("+".join(f"D{r}" for r in rs) if rs else "0")  # noqa: E731
    sheet.cell(at, 9, f'="Transfer "&({part(transfer)})&" · Exchange "&'
                      f'({part(exchange)})&" · HKUST "&'
                      f'(D{at}-({part(transfer)})-({part(exchange)}))').font = HDR
    for column in range(1, NC + 1):
        sheet.cell(at, column).fill = TOT
        sheet.cell(at, column).border = BOX
    sheet.cell(at, 4).alignment = Alignment(horizontal="center")
    return at


LEGEND = [
    "Grey rows = transfer credits · Orange = exchange term (credits count "
    "only after approval) · Blue band = term header · Grey band = term total.",
    "Term total row: Credits = all credits that term; Common Core / Major / "
    "Minor columns = credits counting toward each (a course can count "
    "toward two).",
    "Rows with no Common Core / Major / Minor entry are free electives. "
    "'(you choose)' rows are slots; the document suggests options for each.",
    "Status: Taken / Current / Transfer = done · Planned = future · "
    "Exchange = future, pending credit transfer approval.",
    "Every number on both sheets is a formula. Edit the plan and the totals "
    "follow.",
]


# ------------------------------------------------------------ Progress --

def progress_sections(major: Program, minor: Program | None,
                      common_core: Program | None,
                      catalog: dict[str, Course]) -> list[tuple]:
    """(title, column, [(label, keys, required credits)]) for each section.

    The keys are the exact labels allocate.py writes into the requirement
    columns, because SUMIFS matches on the text. A Broadening row sums over
    every eligible area, since which four the student uses is their choice.
    """
    sections = []
    if major is not None:
        items = [(group.name, [group.name], group_demand(group, catalog))
                 for group in major.groups]
        sections.append((f"MAJOR REQUIREMENTS — {major.title}", "G", items))

    if common_core is not None:
        items = []
        for group in common_core.groups:
            keys, required = [], 0.0
            for rule in group.rules:
                if isinstance(rule, NAreas):
                    keys += list(rule.areas)
                    required += rule.min_credits
                elif hasattr(rule, "area"):
                    keys.append(rule.area)
                    required += rule.min_credits
            if keys:
                items.append((group.name, keys, required))
        sections.append((f"COMMON CORE — {common_core.stated_total_credits:g}"
                         f"-credit program", "F", items))

    if minor is not None:
        items = [(group.name, [group.name], group_demand(group, catalog))
                 for group in minor.groups]
        sections.append((f"MINOR REQUIREMENTS — {minor.title}", "H", items))
    return sections


def progress_sheet(sheet, last: int, sections: list[tuple], report,
                   profile, program: Program, years: int, path_name: str,
                   needed: float) -> None:
    _banner(sheet, 7, banner_text(program, profile, path_name),
            settings_text(profile, years))
    _header(sheet, 3, ["Requirement", "Required", "Done", "Planned",
                       "Exchange (pending)", "Remaining", "Status"])

    plan = "'Course Plan'"
    ref = lambda column: f"{plan}!${column}$4:${column}${last}"  # noqa: E731

    def summed(column: str, keys: list[str], statuses) -> str:
        return "+".join(
            f'SUMIFS({ref("D")},{ref(column)},"{key}",{ref("E")},"{status}")'
            for key in keys for status in statuses)

    def status_formula(row: int) -> str:
        return (f'=IF(C{row}+D{row}>=B{row},"✅ On track",'
                f'IF(C{row}+D{row}+E{row}>=B{row},'
                f'"⚠️ Needs exchange approval","❌ Short"))')

    at = 4

    def section_header(title: str) -> None:
        nonlocal at
        sheet.cell(at, 1, title).font = B
        for column in range(1, 8):
            sheet.cell(at, column).fill = SEC
            sheet.cell(at, column).border = BOX
        at += 1

    for title, column, items in sections:
        section_header(title)
        start = at
        for label, keys, required in items:
            sheet.cell(at, 1, "   " + label).font = N
            sheet.cell(at, 2, required).font = BLUE
            sheet.cell(at, 3, "=" + summed(column, keys, DONE)).font = N
            sheet.cell(at, 4, "=" + summed(column, keys, ["Planned"])).font = N
            sheet.cell(at, 5, "=" + summed(column, keys, ["Exchange"])).font = N
            sheet.cell(at, 6, f"=MAX(0,B{at}-C{at}-D{at}-E{at})").font = N
            sheet.cell(at, 7, status_formula(at)).font = N
            for col in range(1, 8):
                sheet.cell(at, col).border = BOX
            at += 1
        sheet.cell(at, 1, "   Subtotal").font = B
        for index, letter in zip(range(2, 7), "BCDEF"):
            sheet.cell(at, index, f"=SUM({letter}{start}:{letter}{at - 1})"
                       ).font = B
        sheet.cell(at, 7, status_formula(at)).font = B
        for col in range(1, 8):
            sheet.cell(at, col).border = BOX
        at += 2

    section_header(f"GRADUATION — {needed:g} credits")
    every = lambda statuses: "=" + "+".join(  # noqa: E731
        f'SUMIFS({ref("D")},{ref("E")},"{s}")' for s in statuses)
    sheet.cell(at, 1, "   Total credits (each course counted once)").font = B
    sheet.cell(at, 2, needed).font = Font(name=FONT, bold=True, color="0000FF")
    sheet.cell(at, 3, every(DONE)).font = B
    sheet.cell(at, 4, every(["Planned"])).font = B
    sheet.cell(at, 5, every(["Exchange"])).font = B
    sheet.cell(at, 6, f"=MAX(0,B{at}-C{at}-D{at}-E{at})").font = B
    sheet.cell(at, 7, status_formula(at)).font = B
    for col in range(1, 8):
        sheet.cell(at, col).border = BOX
    graduation = at
    at += 1

    done_test = "((" + ")+(".join(f'{ref("E")}="{s}"' for s in DONE) + "))"
    free = lambda test: (  # noqa: E731
        f'=SUMPRODUCT({ref("D")},--({ref("F")}=""),--({ref("G")}=""),'
        f'--({ref("H")}=""),{test})')
    both = lambda test: (  # noqa: E731
        f'=SUMPRODUCT({ref("D")},--({ref("G")}<>""),--({ref("H")}<>""),{test})')
    planned, exchanged = f'--({ref("E")}="Planned")', f'--({ref("E")}="Exchange")'

    info = [("   …of which transfer credits", every(["Transfer"]), None, None),
            ("   …of which free electives", free(done_test), free(planned),
             free(exchanged))]
    if any(title.startswith("MINOR") for title, _, _ in sections):
        info.append(("   Credits double-counted Major + Minor",
                     both(done_test), both(planned), both(exchanged)))
    for label, third, fourth, fifth in info:
        sheet.cell(at, 1, label).font = N
        sheet.cell(at, 3, third).font = N
        if fourth:
            sheet.cell(at, 4, fourth).font = N
        if fifth:
            sheet.cell(at, 5, fifth).font = N
        for col in range(1, 8):
            sheet.cell(at, col).border = BOX
        at += 1
    at += 1

    section_header("THINGS TO CHECK")
    for line in things_to_check(report, program):
        sheet.cell(at, 1, line).font = N
        at += 1

    for formula, shade in ((['LEFT($G4,1)="✅"'], OK),
                           (['LEFT($G4,1)="❌"'], NO),
                           (['LEFT($G4,1)="⚠"'], WARN)):
        sheet.conditional_formatting.add(
            f"G4:G{graduation}", FormulaRule(formula=formula, fill=shade))
    for column, width in zip("ABCDEFG", [52, 10, 9, 9, 12, 11, 26]):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A4"


MARK = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}


def things_to_check(report: ValidationReport, program: Program) -> list[str]:
    """Every validator message, in the order that matters most first.

    Hard rule 2: a plan with unresolved errors may still be shown, but only
    with those errors visible. This is where they become visible.
    """
    lines = [f"{MARK[issue.severity]} {issue.message}"
             for issue in report.errors + report.warnings + report.infos]
    lines.append("ℹ️ Done = Taken + Current + Transfer. Blue numbers are "
                 "requirement inputs; every other number is a formula over "
                 "the Course Plan sheet.")
    lines.append(f"ℹ️ Data tier: {program.tier.value} — "
                 f"{TIER_WORDS[program.tier]}"
                 f"{f' on {program.verified_on}' if program.verified_on else ''}"
                 f". Source: {program.source_url}")
    lines.append("ℹ️ Verify this plan with your academic advisor before you "
                 "rely on it.")
    return lines


# -------------------------------------------------------------- the API --

def build_workbook(path, profile, program: Program, minor: Program | None,
                   common_core: Program | None, catalog: dict[str, Course],
                   needed: float = 120.0) -> Workbook:
    """One path's workbook. `path` is a planner.agent.Path."""
    report = path.report
    allocation = report.allocation
    rows = plan_rows(path.plan, allocation, catalog)
    years = profile.programme_years

    book = Workbook()
    sheet = book.active
    sheet.title = "Course Plan"
    last, totals, kinds = course_plan_sheet(sheet, rows, profile, program,
                                            years, path.name)

    at = last + 2
    ordered = sorted({r.term for r in rows}, key=sort_key)
    first_term = ordered[0] if ordered else "Y1 Fall"
    last_term = ordered[-1] if ordered else "Y4 Spring"
    programme_total(sheet, at, totals, kinds, years, first_term, last_term,
                    needed)
    at += 2

    sheet.cell(at, 1, "Legend").font = B
    at += 1
    for line in LEGEND:
        sheet.cell(at, 1, line).font = N
        at += 1

    dropdown = DataValidation(
        type="list", formula1='"Taken,Current,Transfer,Planned,Exchange"')
    sheet.add_data_validation(dropdown)
    dropdown.add(f"E4:E{last}")
    for column, width in zip("ABCDEFGHI", WIDTHS):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A4"

    progress_sheet(book.create_sheet("Progress"), last,
                   progress_sections(program, minor, common_core, catalog),
                   report, profile, program, years, path.name, needed)
    return book


def write_workbook(path, profile, program: Program, minor: Program | None,
                   common_core: Program | None, catalog: dict[str, Course],
                   destination: FilePath, needed: float = 120.0) -> FilePath:
    book = build_workbook(path, profile, program, minor, common_core, catalog,
                          needed)
    destination.parent.mkdir(parents=True, exist_ok=True)
    book.save(destination)
    return destination
