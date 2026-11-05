"""Phase 0 tests: the data contract in schema.py behaves as the plan assumes.

These run the example that ships inside schema.py rather than restating it, so
the test cannot drift from the example if the example is ever re-tuned.
"""
from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "schema.py"

sys.path.insert(0, str(REPO))

from schema import (  # noqa: E402
    Category,
    ChooseN,
    CommonCoreArea,
    Course,
    CreditsFrom,
    EveryTerm,
    NAreas,
    OneOf,
    PlannedCourse,
    Program,
    Required,
    RequirementGroup,
    evaluate,
)


@pytest.fixture(scope="module")
def example() -> dict:
    """Execute schema.py as __main__ and hand back its namespace.

    This is the "runs the example in schema.py" part: the example really runs,
    and the objects it built (catalog, comp, plan) come back for inspection.
    """
    return runpy.run_path(str(SCHEMA), run_name="__main__")


@pytest.fixture(scope="module")
def results(example) -> list:
    """Use the example namespace's own evaluate, not the imported one.

    runpy gives schema.py a second module identity, so its rule objects are not
    instances of the classes imported at the top of this file and the isinstance
    dispatch inside evaluate would match nothing. Anything touching the example
    has to stay inside the example's namespace.
    """
    return example["evaluate"](example["comp"], example["plan"], example["catalog"])


def group(results: list, name: str) -> list:
    found = [r for r in results if r.group == name]
    assert found, f"no rule results for group {name!r}"
    return found


# --------------------------------------------------------------- assertions --

def test_comp_9999_is_flagged_unknown(example):
    """A hallucinated course code must be caught, and only that one."""
    unknown = example["unknown_courses"](example["plan"], example["catalog"])
    assert unknown == ["COMP 9999"]


def test_depth_electives_rule_is_unmet(results):
    """Only COMP 4211 (3 cr) counts toward the 6-credit depth requirement:
    COMP 4900 is excluded and COMP 9999 is not in the catalog."""
    depth = group(results, "Depth electives")
    assert all(not r.satisfied for r in depth)
    assert depth[0].rule_type == "credits_from"
    assert depth[0].detail == "3/6 credits"


def test_programming_core_is_met(results):
    """COMP 2012H satisfies the one_of, COMP 3711 satisfies the required."""
    core = group(results, "Programming core")
    assert all(r.satisfied for r in core), [r.detail for r in core if not r.satisfied]
    assert {r.rule_type for r in core} == {"one_of", "required"}


def test_exchange_planned_course_validates():
    """Exchange rows are a first-class status, with the pending-approval fields."""
    pc = PlannedCourse(
        code="COMP 4211",
        term="Y3 Spring",
        status="exchange",
        host_course="Machine Learning Systems",
        host_university="NUS",
        note="Pending department approval of mapping",
    )
    assert pc.status == "exchange"
    assert pc.mapping_approved is False  # hard rule 6: never shown as done yet

    with pytest.raises(ValidationError):
        PlannedCourse(code="COMP 4211", term="Y3 Spring", status="registered")


# ------------------------------------------------------- supporting checks --

def test_schema_py_prints_the_example():
    """`python schema.py` is a documented command; it must still work."""
    proc = subprocess.run(
        [sys.executable, str(SCHEMA)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Unknown courses: ['COMP 9999']" in proc.stdout
    assert "Total credits:" in proc.stdout
    assert "JSON schema keys:" in proc.stdout


def test_the_six_rule_types_are_intact():
    """Hard rule 9: rule-type semantics do not change without a decision.

    Adding a rule type is allowed, so this asserts the six are present rather
    than that there are exactly six. n_areas was added in Phase 2 with the
    developer's agreement (see DECISIONS.md) and is checked alongside them.
    """
    expected = {
        Required: "required",
        OneOf: "one_of",
        ChooseN: "choose_n",
        CreditsFrom: "credits_from",
        CommonCoreArea: "cc_area",
        EveryTerm: "every_term",
        NAreas: "n_areas",
    }
    for model, tag in expected.items():
        assert model.model_fields["type"].default == tag, model.__name__

    # The discriminated union must still dispatch on those tags.
    parsed = RequirementGroup.model_validate(
        {
            "name": "probe",
            "category": "Major",
            "rules": [
                {"type": "required", "courses": ["COMP 2011"]},
                {"type": "one_of", "options": [["COMP 2012"], ["COMP 2012H"]]},
                {"type": "choose_n", "n": 1, "courses": ["COMP 3711"]},
                {"type": "credits_from", "patterns": ["COMP 4xxx"], "min_credits": 6},
                {"type": "cc_area", "area": "HAIC", "min_credits": 3},
                {"type": "every_term", "course": "COMP 4900"},
                {"type": "n_areas", "areas": ["A", "H"], "n_areas": 2,
                 "min_credits": 6},
            ],
        }
    )
    assert [type(r) for r in parsed.rules] == list(expected)


def test_total_credits_counts_each_course_once(example):
    """COMP 4900 appears in 8 terms; graduation credits count a course once."""
    plan, catalog = example["plan"], example["catalog"]
    assert sum(1 for p in plan if p.code == "COMP 4900") == 8
    expected = sum(catalog[c].credits for c in {p.code for p in plan} if c in catalog)
    assert example["total_credits"](plan, catalog) == expected


# ------------------------------------------- Phase 2: the n_areas rule type --

def _broadening(areas: list[str], n: int = 4, credits: float = 12) -> Program:
    """A stand-in Common Core program with one Broadening rule."""
    return Program(
        code="CC", title="Common Core", kind="common_core", cohort="2026-27",
        source_url="https://uce.ust.hk/web/courses_2026/curriculum.html",
        groups=[RequirementGroup(name="Broadening", category=Category.COMMON_CORE,
                                 rules=[NAreas(areas=areas, n_areas=n,
                                               min_credits=credits)])])


def _cc_catalog(tagged: dict[str, list[str]]) -> dict[str, Course]:
    return {code: Course(code=code, title=code, credits=3, common_core_areas=a)
            for code, a in tagged.items()}


def _plan(codes: list[str]) -> list[PlannedCourse]:
    return [PlannedCourse(code=c, term="Y2 Fall", status="planned") for c in codes]


def test_n_areas_needs_both_the_credits_and_the_spread():
    """12 credits over four areas: three areas' worth of credits is not enough."""
    catalog = _cc_catalog({"X 1": ["A"], "X 2": ["A"], "X 3": ["H"], "X 4": ["T"]})
    program = _broadening(["A", "H", "T", "SA", "SUS"])

    result = evaluate(program, _plan(list(catalog)), catalog)[0]
    assert not result.satisfied
    assert result.detail == "12/12 credits over 3/4 areas"

    catalog["X 5"] = Course(code="X 5", title="X 5", credits=3,
                            common_core_areas=["SUS"])
    spread = evaluate(program, _plan(list(catalog)), catalog)[0]
    assert spread.satisfied, spread.detail


def test_n_areas_counts_a_two_area_course_once():
    """A course tagged "S, T" can fill S or T, not both."""
    catalog = _cc_catalog({"X 1": ["A", "H"], "X 2": ["A", "H"]})
    result = evaluate(_broadening(["A", "H"], n=2, credits=6),
                      _plan(list(catalog)), catalog)[0]
    assert result.satisfied and result.detail == "6/6 credits over 2/2 areas"

    one = _cc_catalog({"X 1": ["A", "H"]})
    assert evaluate(_broadening(["A", "H"], n=2, credits=3),
                    _plan(list(one)), one)[0].detail == "3/3 credits over 1/2 areas"


def test_n_areas_ignores_home_areas():
    """Courses in an area the rule does not list contribute nothing."""
    catalog = _cc_catalog({"X 1": ["S"], "X 2": ["A"]})
    result = evaluate(_broadening(["A", "H", "T", "SA", "SUS"]),
                      _plan(list(catalog)), catalog)[0]
    assert result.detail == "3/12 credits over 1/4 areas"


def test_variable_credit_courses_keep_their_range():
    """Phase 2 decision: credits is the minimum, credits_max the top."""
    fixed = Course(code="COMP 3711", title="Algorithms", credits=3)
    variable = Course(code="UROP 2100", title="UROP", credits=1, credits_max=4)
    assert fixed.credits_max is None
    assert (variable.credits, variable.credits_max) == (1, 4)
