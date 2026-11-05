"""Phase 3 tests: the deterministic tools the agent is allowed to ask."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from planner.tools import (  # noqa: E402
    All,
    Any_,
    CourseReq,
    Other,
    catalog,
    common_core_for,
    courses_in,
    get_program,
    home_areas,
    list_programs,
    parse_prereq,
    program_row,
    regulation,
    regulation_source,
    satisfied_by,
    search_courses,
)
from schema import NAreas  # noqa: E402


# ------------------------------------------------------------- lookups --

def test_a_program_loads_by_code_including_its_variants():
    assert get_program("COMP").title == "BEng in Computer Science"
    variant = get_program("MATH-STA")
    assert variant.parent == "MATH"
    assert "Statistics Track" in variant.title
    with pytest.raises(KeyError):
        get_program("NOPE")


def test_list_programs_filters_the_way_a_dropdown_needs():
    everything = list_programs()
    assert len(everything) == 129
    assert {r["kind"] for r in list_programs(kind="minor")} == {"minor"}
    assert {r["school"] for r in list_programs(school="SENG")} == {"SENG"}
    assert all(r["tier"] == "unsupported"
               for r in list_programs(tier="unsupported"))
    assert program_row("COMP")["school"] == "SENG"


def test_search_finds_courses_by_title_and_by_code():
    assert search_courses("COMP 3711")[0].code == "COMP 3711"
    hits = {c.code for c in search_courses("machine learning", subject="COMP")}
    assert "COMP 4211" in hits
    assert all(c.code.startswith("COMP ") for c in
               search_courses("data", subject="COMP"))
    assert all(c.code.split()[1].startswith("4") for c in
               search_courses("data", subject="COMP", level=4))
    assert search_courses("quantum basket weaving for cats") == []


def test_a_regulation_comes_back_with_the_page_it_came_from():
    assert regulation("max_credits_regular_term") == 18
    assert regulation("min_credits_regular_term") == 12
    assert regulation("graduation_total_credits") == 120
    assert regulation_source("max_credits_regular_term").startswith("http")
    # the ones HKUST does not publish stay None, so a check can say "verify"
    assert regulation("max_credits_summer_term") is None
    assert regulation("fyp_duration_terms") is None


def test_broadening_drops_the_students_own_home_areas():
    """"12 credits from four different non-home areas" — which areas are
    non-home depends on the program, so the rule has to be narrowed."""
    def areas(code: str) -> list[str]:
        program = common_core_for(code)
        rule = next(r for g in program.groups for r in g.rules
                    if isinstance(r, NAreas))
        return rule.areas

    assert home_areas("COMP") == ["T"]
    assert areas("COMP") == ["A", "H", "S", "SA", "SUS"]
    assert areas("BIEN") == ["A", "H", "SA", "SUS"]        # home S and T
    assert areas("GCS-SS") == ["A", "S", "T", "SUS"]       # home H and SA
    assert set(areas("MINOR-MATH")) == {"A", "H", "S", "T", "SA", "SUS"}


# --------------------------------------------------------- prerequisites --

def test_a_plain_expression_becomes_a_boolean_tree():
    tree = parse_prereq("(COMP 2011 OR COMP 2012) AND COMP 2711")
    assert isinstance(tree, All)
    assert isinstance(tree.terms[0], Any_)
    assert tree.terms[1] == CourseReq("COMP 2711")
    assert courses_in(tree) == {"COMP 2011", "COMP 2012", "COMP 2711"}


def test_a_slash_reads_as_or():
    """The catalog writes short alternatives as "COMP 1021 / COMP 1023"."""
    assert courses_in(parse_prereq("COMP 1021 / COMP 1023")) == {
        "COMP 1021", "COMP 1023"}


def test_prose_beside_a_course_does_not_hide_the_course():
    """"COMP 1022P (prior to 2025-26)" is still a reference to COMP 1022P."""
    tree = parse_prereq("COMP 1021 OR COMP 1022P (prior to 2025-26) "
                        "OR COMP 1023")
    assert courses_in(tree) == {"COMP 1021", "COMP 1022P", "COMP 1023"}

    tree = parse_prereq("ISOM 3540 (Note: students with sufficient background "
                        "may enroll upon approval by the instructor)")
    assert courses_in(tree) == {"ISOM 3540"}


def test_a_condition_the_data_cannot_see_is_flagged_not_failed():
    tree = parse_prereq("Level 4 in HKDSE English Language")
    assert isinstance(tree, Other)
    met, unverifiable = satisfied_by(tree, set())
    assert met and unverifiable == ["Level 4 in HKDSE English Language"]


def test_nothing_and_an_empty_string_mean_no_prerequisite():
    assert parse_prereq(None) is None
    assert parse_prereq("   ") is None
    assert satisfied_by(None, set()) == (True, [])


def test_satisfaction_follows_the_booleans():
    tree = parse_prereq("(COMP 2011 AND COMP 2012) OR COMP 2012H")
    assert satisfied_by(tree, {"COMP 2012H"})[0]
    assert satisfied_by(tree, {"COMP 2011", "COMP 2012"})[0]
    assert not satisfied_by(tree, {"COMP 2011"})[0]
    assert not satisfied_by(tree, set())[0]


def test_every_prerequisite_in_the_catalog_parses_without_losing_a_code():
    """701 expressions. A code that appears in the sentence must appear in
    the tree, or a plan could be validated against half a prerequisite."""
    import re

    code = re.compile(r"\b[A-Z]{2,6} ?\d{4}[A-Z]?\b")
    prose_only = 0
    for course in catalog().values():
        if not course.prereq_expr:
            continue
        tree = parse_prereq(course.prereq_expr)
        found = courses_in(tree)
        mentioned = {re.sub(r"([A-Z]{2,6}) ?(\d{4}[A-Z]?)", r"\1 \2", m.group())
                     for m in code.finditer(course.prereq_expr)}
        assert mentioned <= found, course.code
        prose_only += isinstance(tree, Other)
    assert prose_only < 20     # a handful of pure language requirements
