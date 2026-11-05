"""Phase 2 tests: the derived data in data/ is well formed and complete.

Everything here reads the committed artefacts rather than re-fetching, so the
suite stays offline. Tests that need a file which a later part of Phase 2 will
write skip until it exists, so the suite is green at every checkpoint.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.parse_catalog import (  # noqa: E402
    area_applies,
    expand_code_range,
    parse_credits,
    split_items,
)
from schema import Course  # noqa: E402

CATALOG = REPO / "data" / "catalog.json"
PROGRAMS = REPO / "data" / "programs"


@pytest.fixture(scope="module")
def catalog() -> dict[str, Course]:
    if not CATALOG.exists():
        pytest.skip("data/catalog.json not built yet — run pipeline/parse_catalog.py")
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {code: Course.model_validate(c) for code, c in raw.items()}


# ------------------------------------------------- the parser's small parts --

def test_credit_ranges_become_a_minimum_and_a_maximum():
    assert parse_credits("3 Credit(s)") == (3.0, None)
    assert parse_credits("1-4 Credit(s)") == (1.0, 4.0)
    assert parse_credits("0 Credit(s)") == (0.0, None)
    with pytest.raises(ValueError):
        parse_credits("Credit(s)")


def test_code_ranges_expand_to_every_code_they_cover():
    assert expand_code_range("SOSC 1000-1010") == [f"SOSC {n}" for n in
                                                   range(1000, 1011)]
    assert expand_code_range("COMP 2012H") == ["COMP 2012H"]


def test_exclusion_lists_keep_their_qualifiers_and_free_text():
    assert split_items("LANG 1120 (prior to 2022-23), COMP 1023") == [
        "LANG 1120 (prior to 2022-23)", "COMP 1023"]
    assert split_items("ISOM 2010, any COMP courses of 2000-level or above") == [
        "ISOM 2010", "any COMP courses of 2000-level or above"]
    assert split_items("") == []


def test_an_area_that_ended_before_the_cohort_is_dropped():
    """CIVL 1190 was a T course until 2024-25; a 2026-27 student cannot use it."""
    assert area_applies("", "2026-27")[0]
    assert area_applies("From 2025-26 Fall for 2025-26 and 2026-27 cohorts.",
                        "2026-27")[0]
    assert not area_applies("From 2022-23 Spring to 2024-25 Summer.", "2026-27")[0]
    assert not area_applies("From 2023-24 Fall for 2023-24 and 2024-25 cohorts.",
                            "2026-27")[0]
    assert area_applies("This is a common core course with effect from "
                        "2026-27 Fall.", "2026-27")[0]


# -------------------------------------------------------------- catalog.json --

def test_every_catalog_entry_is_a_valid_course(catalog):
    assert len(catalog) > 1500
    for code, course in catalog.items():
        assert course.code == code
        assert re.fullmatch(r"[A-Z]{2,6} \d{4}[A-Z]?", code), code
        assert course.title, code
        assert course.credits >= 0, code
        assert course.credits_max is None or course.credits_max > course.credits


def test_known_courses_carry_the_values_the_official_pages_state(catalog):
    """Spot checks against prog-crs.hkust.edu.hk/ugcourse/2026-27, read by hand."""
    assert catalog["COMP 2012H"].credits == 5
    assert catalog["COMP 4900"].credits == 0
    assert catalog["MATH 1020"].credits == 4
    assert catalog["UROP 2100"].credits_max is None
    assert catalog["TEMG 4950"].credits == 3
    assert catalog["TEMG 4950"].credits_max == 5
    assert catalog["MATH 1020"].exclusions == ["MATH 1013", "MATH 1014",
                                               "MATH 1023", "MATH 1024"]
    assert catalog["UROP 2100"].prereq_expr == "UROP 1100"


def test_common_core_areas_match_the_published_curriculum(catalog):
    """The 2026-27 areas, and a few tags read off the Common Core course list."""
    allowed = {"HAIC", "HMW", "CTDL", "E-Comm", "C-Comm",
               "A", "H", "S", "T", "SA", "SUS", "UxOP"}
    tagged = [c for c in catalog.values() if c.common_core_areas]
    assert len(tagged) > 200
    for course in tagged:
        assert set(course.common_core_areas) <= allowed, course.code

    assert catalog["AISC 1000"].common_core_areas == ["HAIC"]
    assert catalog["HUMA 3810"].common_core_areas == ["C-Comm", "H"]   # cross-listed
    assert catalog["CIVL 1210"].common_core_areas == ["T", "SUS"]
    # T applied only from 2022-23 Spring to 2024-25 Summer, so not for this cohort
    assert catalog["CIVL 1190"].common_core_areas == ["S", "SUS"]
    assert catalog["COMP 3711"].common_core_areas == []


def test_no_course_offerings_are_claimed(catalog):
    """Hard rule 7: the class schedule disallows scraping, so there is no data."""
    assert all(not c.terms_offered for c in catalog.values())


# ------------------------------------------------------------ program JSONs --

def _program_files() -> list[Path]:
    return sorted(PROGRAMS.glob("*.json")) if PROGRAMS.exists() else []


@pytest.mark.skipif(not _program_files(), reason="Phase 2 Part B not run yet")
@pytest.mark.parametrize("path", _program_files(), ids=lambda p: p.stem)
def test_every_program_json_loads_and_cites_its_source(path, catalog):
    from schema import Program

    from schema import Tier

    program = Program.model_validate_json(path.read_text(encoding="utf-8"))
    assert program.code == path.stem
    assert program.cohort == "2026-27"
    # a few official PDF links are published over plain http
    assert program.source_url.startswith(("https://", "http://"))
    if program.tier is Tier.UNSUPPORTED:
        assert program.unparsed_lines, "an unsupported program must say why"
    else:
        assert program.groups, "a program with no requirement groups says nothing"
    if program.parent:
        assert (PROGRAMS / f"{program.parent}.json").exists()


@pytest.mark.skipif(not _program_files(), reason="Phase 2 Part B not run yet")
@pytest.mark.parametrize("path", _program_files(), ids=lambda p: p.stem)
def test_every_course_a_rule_names_is_in_the_catalog(path, catalog):
    """Hard rule 1, at the data layer: a rule may not cite a course that
    does not exist, because the planner would then put it in a plan."""
    from schema import ChooseN, CreditsFrom, EveryTerm, OneOf, Program, Required

    program = Program.model_validate_json(path.read_text(encoding="utf-8"))
    cited: set[str] = set()
    for group in program.groups:
        for rule in group.rules:
            if isinstance(rule, Required):
                cited |= set(rule.courses)
            elif isinstance(rule, OneOf):
                cited |= {c for option in rule.options for c in option}
            elif isinstance(rule, ChooseN):
                cited |= set(rule.courses)
            elif isinstance(rule, CreditsFrom):
                cited |= {p for p in rule.patterns if "x" not in p and p != "*"}
            elif isinstance(rule, EveryTerm):
                cited.add(rule.course)
    assert sorted(cited - set(catalog)) == []


# ------------------------------------------------------- common_core.json --

@pytest.fixture(scope="module")
def common_core():
    from schema import Program

    path = REPO / "data" / "common_core.json"
    if not path.exists():
        pytest.skip("data/common_core.json not written yet")
    return Program.model_validate_json(path.read_text(encoding="utf-8"))


def test_common_core_adds_up_to_the_published_thirty_credits(common_core):
    """Foundations 18 + Broadening 12 + Experiencing 0, per the published table."""
    assert common_core.kind == "common_core"
    assert common_core.stated_total_credits == 30
    per_area = {g.name: sum(r.min_credits for r in g.rules)
                for g in common_core.groups}
    assert per_area["Foundations - Human-AI Co-Creation and Data Literacy (HAIC)"] == 6
    assert per_area["Foundations - Habits, Mindsets, and Wellness (HMW)"] == 3
    assert per_area["Foundations - English Communication (E-Comm)"] == 6
    assert per_area["Foundations - Chinese Communication (C-Comm)"] == 3
    assert per_area["Broadening"] == 12
    assert per_area["Experiencing (UxOP)"] == 0
    assert sum(per_area.values()) == common_core.stated_total_credits


def test_broadening_asks_for_four_areas_out_of_six(common_core):
    from schema import NAreas

    rule = next(r for g in common_core.groups for r in g.rules
                if isinstance(r, NAreas))
    assert rule.n_areas == 4
    assert rule.min_credits == 12
    assert sorted(rule.areas) == ["A", "H", "S", "SA", "SUS", "T"]
    assert any("home area" in c for c in common_core.caveats), (
        "the rule lists every area, so something must say to remove the "
        "student's home areas first")


def test_the_haic_shortfall_is_recorded_not_papered_over(common_core, catalog):
    """6 credits are required but only one HAIC course is published."""
    haic = [c for c in catalog.values() if "HAIC" in c.common_core_areas]
    assert sum(c.credits for c in haic) < 6
    assert any("HAIC" in c and "verify" in c.lower() for c in common_core.caveats)


# ------------------------------------------------------- regulations.json --

@pytest.fixture(scope="module")
def regulations() -> dict:
    path = REPO / "data" / "regulations.json"
    if not path.exists():
        pytest.skip("data/regulations.json not written yet")
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_regulation_with_a_value_cites_a_source(regulations):
    """Hard rule 11: a threshold a validator uses must come from an official
    source recorded with its URL, or be null."""
    for name, rule in regulations["rules"].items():
        if rule["value"] is None:
            assert rule["source"] is None, name
            assert rule["note"], f"{name} is null and must say why"
        else:
            assert rule["source"] in regulations["sources"], name
            assert rule["source_quote"].strip(), name
            assert regulations["sources"][rule["source"]]["url"].startswith("http")


def test_the_load_limits_are_the_ones_the_regulations_state(regulations):
    rules = regulations["rules"]
    assert rules["min_credits_regular_term"]["value"] == 12
    assert rules["max_credits_regular_term"]["value"] == 18
    assert rules["graduation_total_credits"]["value"] == 120
    assert rules["min_hkust_credits"]["value"] == 60
    assert rules["regular_terms"]["value"] == ["Fall", "Spring"]


def test_the_unknown_regulations_stay_null(regulations):
    """Summer/winter limits, the overload ceiling, the double-count cap, the
    exchange rules and FYP duration were not found in Phase 1; a validator
    must warn "verify" rather than invent a threshold."""
    for name in ("max_credits_summer_term", "max_credits_winter_term",
                 "major_minor_double_count_cap", "exchange_credit_rules",
                 "fyp_duration_terms"):
        assert regulations["rules"][name]["value"] is None, name
    assert regulations["rules"]["overload_approval"][
        "max_credits_with_approval"] is None
    assert len(regulations["gaps"]) == 5


# ----------------------------------------------------- program_index.json --

@pytest.fixture(scope="module")
def index() -> dict:
    path = REPO / "data" / "program_index.json"
    if not path.exists():
        pytest.skip("data/program_index.json not built yet")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_index_covers_every_program_file(index):
    listed = {row["code"] for row in index["programs"]}
    assert listed == {p.stem for p in _program_files()}
    assert index["cohort"] == "2026-27"
    assert index["default_years"] == 4


def test_every_variant_points_at_a_base_that_is_listed(index):
    listed = {row["code"] for row in index["programs"]}
    for row in index["programs"]:
        if row["parent"]:
            assert row["parent"] in listed, row["code"]
            assert row["parent"] != row["code"]


def test_every_major_has_home_areas_or_says_why_not(index):
    """Broadening cannot be checked without them, so a blank needs a reason."""
    allowed = {"A", "H", "S", "T", "SA", "SUS"}
    for row in index["programs"]:
        if row["kind"] != "major":
            continue
        assert set(row["home_areas"]) <= allowed, row["code"]
        assert row["home_areas"] or row["home_areas_note"], row["code"]


def test_home_areas_match_the_published_table(index):
    """Spot checks against the curriculum page and the program-specific PDF."""
    by_code = {row["code"]: row for row in index["programs"]}
    assert by_code["COMP"]["home_areas"] == ["T"]
    assert by_code["MATH-AM"]["home_areas"] == ["S"]       # inherits from MATH
    assert by_code["FINA"]["home_areas"] == ["SA"]
    assert by_code["GCS-SS"]["home_areas"] == ["H", "SA"]
    assert by_code["IDT"]["home_areas"] == ["T"]
    assert by_code["BIEN"]["home_areas"] == ["S", "T"]
    assert by_code["EVMT"]["home_areas"] == ["SA", "SUS"]
    assert by_code["MINOR-MATH"]["home_areas"] == []


def test_an_unsupported_program_always_explains_itself(index):
    from schema import Program

    for row in index["programs"]:
        if row["tier"] != "unsupported":
            continue
        program = Program.model_validate_json(
            (PROGRAMS / f"{row['code']}.json").read_text(encoding="utf-8"))
        assert program.unparsed_lines, row["code"]
        assert row["issues_file"], row["code"]
        assert (PROGRAMS / row["issues_file"]).exists()
