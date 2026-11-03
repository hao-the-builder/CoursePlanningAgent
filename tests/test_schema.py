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
    ChooseN,
    CommonCoreArea,
    CreditsFrom,
    EveryTerm,
    OneOf,
    PlannedCourse,
    Required,
    RequirementGroup,
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
    than that there are exactly six.
    """
    expected = {
        Required: "required",
        OneOf: "one_of",
        ChooseN: "choose_n",
        CreditsFrom: "credits_from",
        CommonCoreArea: "cc_area",
        EveryTerm: "every_term",
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
