"""Phase 3 tests: the term sequence and the ordering everything else relies on."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from planner.terms import (  # noqa: E402
    Term,
    calendar_year,
    final_term,
    in_residence,
    is_regular,
    label_range,
    parse_label,
    sort_key,
    start_year,
    term_sequence,
)


def labels(terms: list[Term]) -> list[str]:
    return [t.label for t in terms]


def test_a_four_year_plan_is_eight_regular_terms():
    terms = term_sequence("2026-27", years=4)
    assert labels(terms) == [f"Y{y} {s}" for y in range(1, 5)
                             for s in ("Fall", "Spring")]
    assert len(terms) == 8
    assert all(t.is_regular for t in terms)


def test_calendar_years_follow_the_september_academic_year():
    """Fall sits in the first calendar year of its academic year, the rest in
    the second: the 2026-27 cohort starts in Fall 2026 and Y1 Spring is 2027."""
    terms = {t.label: t.calendar for t in
             term_sequence("2026-27", 4, use_summer=True, use_winter=True)}
    assert terms["Y1 Fall"] == "Fall 2026"
    assert terms["Y1 Winter"] == "Winter 2027"
    assert terms["Y1 Spring"] == "Spring 2027"
    assert terms["Y1 Summer"] == "Summer 2027"
    assert terms["Y2 Fall"] == "Fall 2027"     # CLAUDE.md's worked example
    assert terms["Y4 Spring"] == "Spring 2030"

    assert start_year("2026-27") == 2026
    assert calendar_year(2026, 2, "Fall") == 2027
    assert calendar_year(2026, 2, "Spring") == 2028


def test_summer_and_winter_appear_only_when_the_student_wants_them():
    assert "Y1 Summer" not in labels(term_sequence("2026-27", 4))
    assert "Y1 Summer" in labels(term_sequence("2026-27", 4, use_summer=True))
    assert "Y1 Winter" not in labels(term_sequence("2026-27", 4, use_summer=True))

    both = labels(term_sequence("2026-27", 1, use_summer=True, use_winter=True))
    assert both == ["Y1 Fall", "Y1 Winter", "Y1 Spring", "Y1 Summer"]


def test_transfer_sorts_before_the_first_term():
    terms = term_sequence("2026-27", 4, include_transfer=True)
    assert terms[0].label == "Transfer"
    assert terms[0].is_transfer and not terms[0].is_regular
    assert terms[0].calendar == "Before HKUST"
    assert labels(terms) == sorted(labels(terms), key=sort_key)


def test_the_documented_ordering_holds():
    """Transfer < Y1 Fall < Y1 Winter < Y1 Spring < Y1 Summer < Y2 Fall."""
    order = ["Transfer", "Y1 Fall", "Y1 Winter", "Y1 Spring", "Y1 Summer",
             "Y2 Fall"]
    assert sorted(reversed(order), key=sort_key) == order


def test_a_term_label_that_makes_no_sense_sorts_last_rather_than_crashing():
    """The LLM writes these labels, so a bad one must not take the run down."""
    assert sort_key("next spring") > sort_key("Y5 Summer")
    assert not is_regular("next spring")
    with pytest.raises(ValueError):
        parse_label("next spring")


def test_only_fall_and_spring_are_regular_terms():
    """AR 9.1: the 12-18 credit limits apply to Regular Terms only."""
    assert is_regular("Y1 Fall") and is_regular("Y4 Spring")
    assert not is_regular("Y2 Summer")
    assert not is_regular("Y2 Winter")
    assert not is_regular("Transfer")


def test_in_residence_counts_regular_terms_once_each():
    """What an every_term rule such as COMP 4900 is measured against."""
    plan_terms = ["Transfer", "Y1 Fall", "Y1 Fall", "Y1 Summer", "Y1 Spring"]
    assert in_residence(plan_terms) == ["Y1 Fall", "Y1 Spring"]
    assert len(in_residence(label_range("2026-27", 4))) == 8


def test_final_term_ignores_the_transfer_block():
    terms = term_sequence("2026-27", 4, use_summer=True, include_transfer=True)
    assert final_term(terms).label == "Y4 Summer"
    assert final_term(term_sequence("2026-27", 4)).label == "Y4 Spring"


def test_a_five_year_sequence_is_generated_even_though_it_is_unsupported():
    """DECISIONS.md drops 5-year support, but terms.py takes `years` so the
    capability is cheap to restore. Nothing downstream is built for it."""
    terms = term_sequence("2026-27", years=5)
    assert len(terms) == 10
    assert terms[-1].label == "Y5 Spring"
    assert terms[-1].calendar == "Spring 2031"


def test_a_cohort_that_is_not_a_cohort_is_refused():
    for bad in ("2026", "26-27", "", "2026/27"):
        with pytest.raises(ValueError):
            start_year(bad)
    with pytest.raises(ValueError):
        term_sequence("2026-27", years=0)
