"""Phase 5 tests: the spreadsheet's formulas compute the right numbers.

Phase 5 asks for the workbooks to be recalculated and the results checked,
because a formula that *looks* right and sums the wrong rows is exactly the
bug this format invites. CLAUDE.md names LibreOffice headless for the
recalculation; it is not installed here, so these tests recalculate with
`formulas`, a pure-Python Excel engine, which needs no install beyond pip and
runs in CI. `recalculate()` uses LibreOffice instead when `soffice` is on the
PATH, so the originally specified route still works where it exists.

What is actually asserted is the thing that matters: the totals a student
reads come out equal to numbers computed independently from the
ValidationReport — not equal to other cells in the same sheet.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from openpyxl import load_workbook  # noqa: E402

from outputs.docx_builder import write_document  # noqa: E402
from outputs.xlsx_builder import things_to_check, write_workbook  # noqa: E402
from planner.agent import load_profile, plan_for  # noqa: E402
from planner.terms import sort_key  # noqa: E402
from planner.tools import catalog, common_core_for, get_program  # noqa: E402
from planner.validate import is_slot  # noqa: E402

PROFILES = REPO / "tests" / "profiles"
CASES = ["01-comp-correct", "06-front-loaded-free-final", "07-exchange-term",
         "09-transfer-credits", "10-front-free-exchange"]

try:
    import formulas                                   # noqa: F401
    HAVE_ENGINE = True
except ImportError:                                   # pragma: no cover
    HAVE_ENGINE = False


def recalculate(path: Path) -> dict[tuple[str, str], object]:
    """Every computed cell, as {(SHEET, "D12"): value}.

    LibreOffice if it is installed, `formulas` otherwise. Both answer the
    same question: what does Excel show when it opens this file?
    """
    if shutil.which("soffice"):                       # pragma: no cover
        out = path.parent / "recalculated"
        subprocess.run(["soffice", "--headless", "--convert-to", "xlsx",
                        "--outdir", str(out), str(path)], check=True,
                       capture_output=True, timeout=180)
        book = load_workbook(out / path.name, data_only=True)
        return {(sheet.title.upper(), cell.coordinate): cell.value
                for sheet in book.worksheets
                for row in sheet.iter_rows() for cell in row
                if cell.value is not None}

    import formulas

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        solution = formulas.ExcelModel().loads(str(path)).finish().calculate()

    values: dict[tuple[str, str], object] = {}
    for key, cell in solution.items():
        if "!" not in key:
            continue
        sheet, _, ref = key.rpartition("!")
        sheet = sheet.strip("'").partition("]")[2].upper()
        try:
            values[(sheet, ref.replace("$", ""))] = cell.value[0, 0]
        except Exception:                             # noqa: BLE001
            values[(sheet, ref.replace("$", ""))] = getattr(cell, "value", None)
    return values


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict:
    """Build every case once: profile, report, workbook and recalculation."""
    root = tmp_path_factory.mktemp("outputs")
    made = {}
    for name in CASES:
        profile = load_profile(PROFILES / f"{name}.json")
        result = plan_for(profile, paths=1)
        assert result.paths, f"{name} produced no path"
        path = result.paths[0]
        program = get_program(profile.major)
        minor = get_program(profile.minor) if profile.minor else None
        core = common_core_for(profile.major)
        book = write_workbook(path, profile, program, minor, core, catalog(),
                              root / f"{name}.xlsx")
        made[name] = {"profile": profile, "result": result, "path": path,
                      "program": program, "minor": minor, "core": core,
                      "file": book}
    return made


@pytest.fixture(scope="module")
def recalculated(built) -> dict:
    if not HAVE_ENGINE and not shutil.which("soffice"):  # pragma: no cover
        pytest.skip("no recalculation engine: pip install formulas, or put "
                    "LibreOffice's soffice on the PATH")
    return {name: recalculate(case["file"]) for name, case in built.items()}


def rows_of(sheet, column: str, test) -> list[int]:
    return [cell.row for cell in sheet[column]
            if isinstance(cell.value, str) and test(cell.value)]


# ------------------------------------------------------------ structure --

@pytest.mark.parametrize("name", CASES)
def test_the_workbook_has_the_two_sheets_the_sample_has(built, name):
    book = load_workbook(built[name]["file"])
    assert book.sheetnames == ["Course Plan", "Progress"]
    plan = book["Course Plan"]
    assert plan.freeze_panes == "A4"
    headings = [plan.cell(3, i).value for i in range(1, 10)]
    assert headings == ["Semester", "Course Code", "Course Name", "Credits",
                        "Status", "Common Core", "Major Requirements",
                        "Minor Requirements", "Notes"]


@pytest.mark.parametrize("name", CASES)
def test_every_number_is_a_formula_not_a_value(built, name):
    """The student edits the plan and the totals follow. That only works if
    no total was computed in Python and written as a number."""
    book = load_workbook(built[name]["file"])
    plan = book["Course Plan"]
    for row in rows_of(plan, "C", lambda v: v.endswith(" total")):
        for column in "DFGH":
            value = plan[f"{column}{row}"].value
            assert isinstance(value, str) and value.startswith("="), \
                f"{column}{row} is not a formula"

    progress = book["Progress"]
    for row in range(4, progress.max_row + 1):
        for column in "CDEF":
            value = progress[f"{column}{row}"].value
            if value is not None:
                assert isinstance(value, str) and value.startswith("="), \
                    f"Progress!{column}{row} is a hard-coded number"


@pytest.mark.parametrize("name", CASES)
def test_only_formulas_both_excel_and_sheets_understand(built, name):
    book = load_workbook(built[name]["file"])
    banned = ("XLOOKUP", "FILTER(", "SORT(", "UNIQUE(", "LET(", "LAMBDA(",
              "TEXTJOIN", "_xlfn")
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    for word in banned:
                        assert word not in cell.value.upper(), \
                            f"{sheet.title}!{cell.coordinate}: {word}"


@pytest.mark.parametrize("name", CASES)
def test_the_status_dropdown_covers_every_course_row(built, name):
    book = load_workbook(built[name]["file"])
    plan = book["Course Plan"]
    validations = plan.data_validations.dataValidation
    assert len(validations) == 1
    assert validations[0].formula1 == \
        '"Taken,Current,Transfer,Planned,Exchange"'
    last = max(rows_of(plan, "C", lambda v: v.endswith(" total")))
    assert f"E4:E{last}" in str(validations[0].sqref)


# -------------------------------------------------------- the arithmetic --

@pytest.mark.parametrize("name", CASES)
def test_recalculating_produces_no_formula_errors(recalculated, name):
    broken = {ref: value for ref, value in recalculated[name].items()
              if isinstance(value, str) and value.startswith("#")}
    assert broken == {}


@pytest.mark.parametrize("name", CASES)
def test_the_programme_total_is_the_sum_of_the_term_totals(built,
                                                           recalculated, name):
    book = load_workbook(built[name]["file"])
    plan = book["Course Plan"]
    values = recalculated[name]
    terms = rows_of(plan, "C", lambda v: v.endswith(" total"))
    grand = next(cell.row for cell in plan["A"]
                 if cell.value == "PROGRAMME TOTAL")

    per_term = [values[("COURSE PLAN", f"D{row}")] for row in terms]
    assert values[("COURSE PLAN", f"D{grand}")] == pytest.approx(sum(per_term))


@pytest.mark.parametrize("name", CASES)
def test_the_term_totals_match_the_validator_not_each_other(built,
                                                            recalculated, name):
    """The real check: the spreadsheet agrees with the number Python
    computed from the plan, independently of the spreadsheet."""
    case = built[name]
    book = load_workbook(case["file"])
    plan = book["Course Plan"]
    values = recalculated[name]
    expected = case["path"].report.per_term

    for row in rows_of(plan, "C", lambda v: v.endswith(" total")):
        label = plan[f"C{row}"].value.removesuffix(" total")
        assert values[("COURSE PLAN", f"D{row}")] == pytest.approx(
            expected.get(label, 0.0)), label


@pytest.mark.parametrize("name", CASES)
def test_the_graduation_row_agrees_with_the_credit_summary(built,
                                                           recalculated, name):
    case = built[name]
    book = load_workbook(case["file"])
    progress = book["Progress"]
    values = recalculated[name]
    row = next(cell.row for cell in progress["A"]
               if isinstance(cell.value, str)
               and "Total credits" in cell.value)

    credits = case["path"].report.credits
    done = values[("PROGRESS", f"C{row}")]
    planned = values[("PROGRESS", f"D{row}")]
    pending = values[("PROGRESS", f"E{row}")]

    assert done == pytest.approx(credits.earned)
    assert planned == pytest.approx(credits.planned)
    assert pending == pytest.approx(credits.exchange_pending)
    # the unspecified transfer credits have no course row, so they are not here
    assert done + planned == pytest.approx(
        credits.confirmed - credits.unspecified_transfer)


def test_a_requirement_met_only_by_exchange_is_not_shown_as_met(
        built, recalculated):
    """Hard rule 6: never a tick until the mapping is approved."""
    case = built["10-front-free-exchange"]
    book = load_workbook(case["file"])
    progress = book["Progress"]
    values = recalculated["10-front-free-exchange"]

    pending = [row for row in range(4, progress.max_row + 1)
               if isinstance(values.get(("PROGRESS", f"E{row}")), (int, float))
               and values[("PROGRESS", f"E{row}")] > 0]
    assert pending, "no row carries pending exchange credits"
    for row in pending:
        status = values.get(("PROGRESS", f"G{row}"))
        if status and "Needs exchange approval" in str(status):
            break
    else:
        pytest.fail("no requirement is flagged as needing exchange approval")


@pytest.mark.parametrize("name", CASES)
def test_the_free_term_shows_as_free_and_the_heavy_term_as_heavy(
        built, recalculated, name):
    book = load_workbook(built[name]["file"])
    plan = book["Course Plan"]
    values = recalculated[name]
    for row in rows_of(plan, "C", lambda v: v.endswith(" total")):
        credits = values[("COURSE PLAN", f"D{row}")]
        tag = str(values.get(("COURSE PLAN", f"I{row}")) or "")
        label = plan[f"C{row}"].value
        if "Transfer" in label or "Exchange" in tag:
            continue
        if credits == 0:
            assert "Free term" in tag, label
        elif credits >= 18:
            assert "Heavy" in tag, label
        elif credits < 12:
            assert "Light" in tag, label
        else:
            assert tag == "Normal", (label, tag)


# ------------------------------------------------------------- contents --

@pytest.mark.parametrize("name", CASES)
def test_every_course_code_in_the_sheet_exists_in_the_catalog(built, name):
    """Hard rule 1, at the last place it could go wrong."""
    known = catalog()
    book = load_workbook(built[name]["file"])
    plan = book["Course Plan"]
    allowed = {"Host course", "Course Code"}
    for row in range(4, plan.max_row + 1):
        code = plan[f"B{row}"].value
        if not code or code in allowed or str(code).startswith(("CC — ",
                                                                "Free")):
            continue
        assert code in known, f"row {row}: {code}"


@pytest.mark.parametrize("name", CASES)
def test_the_banner_carries_the_tier_and_the_advisor_warning(built, name):
    book = load_workbook(built[name]["file"])
    for sheet in book.worksheets:
        banner = str(sheet["A1"].value)
        assert built[name]["program"].tier.value in banner
        assert "academic advisor" in banner
        assert built[name]["profile"].cohort in banner


def test_things_to_check_shows_every_unresolved_problem(built):
    """Hard rule 2: a plan may be shown with errors only if they are visible."""
    case = built["07-exchange-term"]
    lines = things_to_check(case["path"].report, case["program"])
    report = case["path"].report
    for issue in report.errors + report.warnings:
        assert any(issue.message in line for line in lines), issue.message
    assert any("advisor" in line for line in lines)
    assert any(case["program"].source_url in line for line in lines)


# ------------------------------------------------------------- document --

def test_the_document_covers_every_path_and_closes_with_its_limits(built,
                                                                   tmp_path):
    from docx import Document

    case = built["10-front-free-exchange"]
    result = plan_for(case["profile"], paths=2)
    target = write_document(result, case["profile"], case["program"],
                            case["minor"], case["core"], catalog(),
                            tmp_path / "plan.docx")
    document = Document(target)
    text = "\n".join(p.text for p in document.paragraphs)

    assert "What you told me" in text
    for index, path in enumerate(result.paths, 1):
        assert f"Path {index}: {path.name}" in text
    assert "Data and limits" in text
    assert case["program"].source_url in "\n".join(
        cell.text for table in document.tables for row in table.rows
        for cell in row.cells)
    assert "academic advisor" in text
    assert "no grade is predicted" in text.lower() or \
        "No grade is predicted" in text


def test_the_document_never_states_a_number_the_report_does_not(built,
                                                                tmp_path):
    """Section 1.2: the model writes prose, code writes every number."""
    from docx import Document

    case = built["01-comp-correct"]
    result = plan_for(case["profile"], paths=1)
    target = write_document(result, case["profile"], case["program"], None,
                            case["core"], catalog(), tmp_path / "one.docx")
    document = Document(target)

    report = result.paths[0].report
    table = next(t for t in document.tables
                 if t.rows[0].cells[0].text == "Term")
    rows = {r.cells[0].text: r.cells[1].text for r in table.rows[1:]}
    for term, credits in report.per_term.items():
        assert rows[term] == f"{credits:g}"
    assert rows["Total"] == f"{report.credits.with_exchange:g}"


def test_a_slot_is_offered_options_rather_than_an_invented_course(tmp_path):
    from docx import Document

    from planner.agent import Path as AgentPath

    case_profile = load_profile(PROFILES / "01-comp-correct.json")
    result = plan_for(case_profile, paths=1)
    path = result.paths[0]
    path.plan.append(
        type(path.plan[0])(code="SLOT:CC-A", term="Y2 Fall", status="planned"))
    path.slot_suggestions = {"SLOT:CC-A": ["AMCC 2010", "COMP 1943"]}
    path.report = plan_for(case_profile, paths=1).paths[0].report

    target = write_document(result, case_profile, get_program("COMP"), None,
                            common_core_for("COMP"), catalog(),
                            tmp_path / "slots.docx")
    text = "\n".join(cell.text for table in Document(target).tables
                     for row in table.rows for cell in row.cells)
    assert "SLOT:CC-A" in text
    assert "AMCC 2010" in text and "Digital Audio Workstation" in text
    assert isinstance(path, AgentPath) and is_slot("SLOT:CC-A")
