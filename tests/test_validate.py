"""Phase 3 tests: validate_plan says exactly what each test case should make it say.

Each case is a pair of files. `tests/profiles/{name}.json` holds a student
profile and a plan; `tests/expected/{name}.json` holds what the validator
should report, written by hand from the case's intent rather than copied from
a run — otherwise the test only asserts that the code does what it does.

Errors are matched exactly: the set of (check, course, term) triples must be
the one the expectation lists, no more and no less. Warnings are matched by
which checks fire, plus any phrase the case turns on. That split is deliberate
— an error changes whether a plan may be shown at all, so its list has to be
closed; a warning's wording is allowed to improve.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from planner.intake import StudentProfile  # noqa: E402
from planner.validate import ValidationReport, validate_plan  # noqa: E402
from schema import PlannedCourse  # noqa: E402

PROFILES = REPO / "tests" / "profiles"
EXPECTED = REPO / "tests" / "expected"

CASES = sorted(p.stem for p in PROFILES.glob("*.json")) if PROFILES.exists() else []


def load(name: str) -> tuple[list[PlannedCourse], StudentProfile, dict]:
    fixture = json.loads((PROFILES / f"{name}.json").read_text(encoding="utf-8"))
    expected = json.loads((EXPECTED / f"{name}.json").read_text(encoding="utf-8"))
    plan = [PlannedCourse.model_validate(row) for row in fixture["plan"]]
    profile = StudentProfile.model_validate({
        **fixture["profile"],
        "transfer_credits": [r for r in fixture["plan"]
                             if r.get("status") == "transfer"],
    })
    return plan, profile, expected


def run(name: str) -> tuple[ValidationReport, dict]:
    plan, profile, expected = load(name)
    return validate_plan(plan, profile), expected


@pytest.mark.skipif(not CASES, reason="Phase 3 fixtures not written yet")
@pytest.mark.parametrize("name", CASES)
def test_the_expected_errors_and_nothing_else(name):
    report, expected = run(name)
    got = sorted((i.check, i.course, i.term) for i in report.errors)
    want = sorted((e["check"], e.get("course"), e.get("term"))
                  for e in expected["errors"])
    assert got == want, "\n".join(str(i) for i in report.errors)
    assert report.ok is expected["ok"]


@pytest.mark.skipif(not CASES, reason="Phase 3 fixtures not written yet")
@pytest.mark.parametrize("name", CASES)
def test_each_error_says_what_it_should(name):
    report, expected = run(name)
    for want in expected["errors"]:
        matches = [i for i in report.errors if i.check == want["check"]
                   and want["contains"] in i.message]
        assert matches, (f"no {want['check']} error mentioning "
                         f"{want['contains']!r}; got "
                         + " | ".join(i.message for i in report.errors))


@pytest.mark.skipif(not CASES, reason="Phase 3 fixtures not written yet")
@pytest.mark.parametrize("name", CASES)
def test_the_expected_warnings_and_infos_fire(name):
    report, expected = run(name)
    assert sorted({i.check for i in report.warnings}) == sorted(
        expected["warning_checks"])
    assert sorted({i.check for i in report.infos}) == sorted(
        expected["info_checks"])

    said = " || ".join(i.message for i in report.issues)
    for phrase in expected["must_say"]:
        assert phrase in said, f"nothing said {phrase!r}"


@pytest.mark.skipif(not CASES, reason="Phase 3 fixtures not written yet")
@pytest.mark.parametrize("name", CASES)
def test_the_credit_arithmetic_matches_the_hand_count(name):
    report, expected = run(name)
    for field, value in expected["credits"].items():
        assert getattr(report.credits, field) == value, field
    for term, credits in expected["per_term"].items():
        assert report.per_term.get(term, 0.0) == credits, term
    assert sum(report.per_term.values()) == sum(expected["per_term"].values())


# ------------------------------- the things every one of them has in common --

def test_a_valid_plan_reports_no_errors_at_all():
    """The whole point of case 1: a correct plan must be clean."""
    report, _ = run("01-comp-correct")
    assert report.errors == []
    assert report.ok


def test_warnings_never_block_a_plan():
    """A plan with warnings and no errors is still usable — hard rule 2 only
    requires that the warnings be shown."""
    for name in ("01-comp-correct", "06-front-loaded-free-final",
                 "09-transfer-credits"):
        report, _ = run(name)
        assert report.warnings and report.ok


def test_every_issue_is_in_plain_english_and_points_somewhere():
    """These messages end up in a student's spreadsheet."""
    for name in CASES:
        report, _ = run(name)
        for issue in report.issues:
            assert issue.message.strip().endswith((".", "!")), issue.message
            assert issue.message[0].isupper() or issue.message[0].isalnum()
            assert len(issue.message) > 25, issue.message
            assert issue.check and issue.severity


def test_a_plan_for_an_unsupported_program_still_validates():
    """MATH's base program cannot be planned (a track must be chosen), but the
    validator must not fall over on it — hard rule 5 is the agent's job."""
    profile = StudentProfile(cohort="2026-27", major="MATH")
    plan = [PlannedCourse(code="MATH 1020", term="Y1 Fall", status="planned")]
    report = validate_plan(plan, profile)
    assert report.errors
    assert any(i.check == "check_graduation" for i in report.errors)
