"""
HKUST Course Planner — generic requirement schema + evaluator.

One schema for every major/minor/Common Core. The LLM extractor fills these
models from the official requirement PDFs; plain code evaluates them.

Run:  python schema.py   (runs the built-in example)
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- catalog --

class Course(BaseModel):
    code: str                      # "COMP 2011"
    title: str
    credits: float                 # the minimum, when the catalog gives a range
    credits_max: float | None = None  # top of the range; None when fixed
    prereq_expr: str | None = None   # raw text from catalog, e.g. "COMP 1021 OR COMP 1022P"
    exclusions: list[str] = []
    terms_offered: list[Literal["Fall", "Winter", "Spring", "Summer"]] = []
    common_core_areas: list[str] = []  # e.g. ["HAIC"], ["S"], ["E-Comm"]


# ------------------------------------------------------------------ rules --
# Every requirement line in every program reduces to one of these.

class Required(BaseModel):
    """All of these courses must be taken."""
    type: Literal["required"] = "required"
    courses: list[str]


class OneOf(BaseModel):
    """Exactly one option (each option = a set of courses) must be completed.
    e.g. (COMP 2011 AND COMP 2012) OR COMP 2012H"""
    type: Literal["one_of"] = "one_of"
    options: list[list[str]]


class ChooseN(BaseModel):
    """Pick at least n courses from a list."""
    type: Literal["choose_n"] = "choose_n"
    n: int
    courses: list[str]


class CreditsFrom(BaseModel):
    """At least min_credits from courses matching a pattern.
    Patterns: "COMP 3xxx", "COMP 4xxx", "MATH 2xxx", "*" (any course)."""
    type: Literal["credits_from"] = "credits_from"
    patterns: list[str]
    min_credits: float
    exclude: list[str] = []


class CommonCoreArea(BaseModel):
    """At least min_credits from courses tagged with a Common Core area."""
    type: Literal["cc_area"] = "cc_area"
    area: str          # "HAIC", "S", "H", "E-Comm", ...
    min_credits: float


class EveryTerm(BaseModel):
    """Must be taken every regular term in residence (e.g. COMP 4900)."""
    type: Literal["every_term"] = "every_term"
    course: str


class NAreas(BaseModel):
    """min_credits spread over at least n_areas different Common Core areas.

    The Common Core Broadening requirement: "12 credits from 4 different
    non-home common core areas", where more areas are eligible than must be
    used (an SSCI student picks 4 of A/H/T/SA/SUS). cc_area pins one area, so
    it cannot express the choice.
    """
    type: Literal["n_areas"] = "n_areas"
    areas: list[str]           # eligible areas, e.g. ["A", "H", "T", "SA", "SUS"]
    n_areas: int               # how many of them must be used
    min_credits: float


Rule = Annotated[
    Union[Required, OneOf, ChooseN, CreditsFrom, CommonCoreArea, EveryTerm, NAreas],
    Field(discriminator="type"),
]


# --------------------------------------------------------------- programs --

class Category(str, Enum):
    MAJOR = "Major"
    COMMON_CORE = "Common Core"
    MINOR = "Minor"
    SCHOOL = "School"
    UNIVERSITY = "University"


class Tier(str, Enum):
    VERIFIED = "verified"            # hand-checked by the team
    AUTO = "auto_extracted"          # passed auto-checks only
    UNSUPPORTED = "unsupported"      # failed auto-checks


class RequirementGroup(BaseModel):
    name: str                        # "Engineering Fundamentals", "Depth Electives"
    category: Category
    rules: list[Rule]
    source_quote: str = ""           # exact line from the PDF, for traceability


class Program(BaseModel):
    code: str                        # "COMP"
    title: str
    kind: Literal["major", "minor", "common_core"]
    cohort: str                      # "2026-27" — requirements differ by intake year
    groups: list[RequirementGroup]
    stated_total_credits: float | None = None   # used for the auto-check
    max_double_count_credits: float | None = None
    source_url: str
    tier: Tier = Tier.AUTO
    unparsed_lines: list[str] = []   # anything the extractor couldn't map → forces review
    caveats: list[str] = []          # mapped, but a stated refinement is not enforced
    parent: str | None = None        # base program, when this is a track/option variant


# ---------------------------------------------------------------- student --

class PlannedCourse(BaseModel):
    code: str                        # HKUST code; for exchange rows, the HKUST requirement slot it maps to
    term: str                        # "Transfer", "Y1 Fall", "Y1 Spring", "Y3 Summer", "Y1 Winter", ... "Y5 Spring"
    status: Literal["taken", "current", "planned", "transfer", "exchange"]
    host_course: str | None = None   # exchange only: host university course title
    host_university: str | None = None
    mapping_approved: bool = False   # exchange/transfer mapping confirmed by HKUST
    note: str = ""


# -------------------------------------------------------------- evaluator --

def _matches(code: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    regex = "^" + re.escape(pattern).replace("x", r"\d") + r"H?$"
    return re.match(regex, code) is not None


def _spread(courses: list[str], areas: list[str], catalog: dict[str, Course]) -> int:
    """How many of `areas` these courses can cover, one course to one area.

    Greedy: a course tagged "S, T" can serve S or T but not both, so courses
    with the fewest eligible areas are placed first. Good enough for a
    pass/fail check; planner/allocate.py does the authoritative assignment.
    """
    pool = sorted(
        ([a for a in areas if a in catalog[c].common_core_areas] for c in courses
         if c in catalog and any(a in areas for a in catalog[c].common_core_areas)),
        key=len)
    used: set[str] = set()
    for options in pool:
        free = [a for a in options if a not in used]
        if free:
            used.add(free[0])
    return len(used)


class RuleResult(BaseModel):
    group: str
    category: Category
    rule_type: str
    satisfied: bool
    detail: str


def evaluate(program: Program, plan: list[PlannedCourse],
             catalog: dict[str, Course], terms_in_residence: int = 8) -> list[RuleResult]:
    codes = [p.code for p in plan]
    have = set(codes)
    cred = lambda c: catalog[c].credits if c in catalog else 0
    out: list[RuleResult] = []

    for g in program.groups:
        for r in g.rules:
            if isinstance(r, Required):
                missing = [c for c in r.courses if c not in have]
                ok, d = not missing, f"missing: {missing}" if missing else "all taken"
            elif isinstance(r, OneOf):
                hit = [o for o in r.options if all(c in have for c in o)]
                ok, d = bool(hit), f"via {hit[0]}" if hit else f"need one of {r.options}"
            elif isinstance(r, ChooseN):
                got = [c for c in r.courses if c in have]
                ok, d = len(got) >= r.n, f"{len(got)}/{r.n}"
            elif isinstance(r, CreditsFrom):
                got = sum(cred(c) for c in have
                          if c not in r.exclude and any(_matches(c, p) for p in r.patterns))
                ok, d = got >= r.min_credits, f"{got:g}/{r.min_credits:g} credits"
            elif isinstance(r, CommonCoreArea):
                got = sum(cred(c) for c in have
                          if c in catalog and r.area in catalog[c].common_core_areas)
                ok, d = got >= r.min_credits, f"{got:g}/{r.min_credits:g} credits"
            elif isinstance(r, EveryTerm):
                n = codes.count(r.course)
                ok, d = n >= terms_in_residence, f"{n}/{terms_in_residence} terms"
            elif isinstance(r, NAreas):
                eligible = [c for c in have if c in catalog
                            and any(a in r.areas for a in catalog[c].common_core_areas)]
                got, n = sum(cred(c) for c in eligible), _spread(eligible, r.areas, catalog)
                ok = got >= r.min_credits and n >= r.n_areas
                d = f"{got:g}/{r.min_credits:g} credits over {n}/{r.n_areas} areas"
            out.append(RuleResult(group=g.name, category=g.category,
                                  rule_type=r.type, satisfied=ok, detail=d))
    return out


def total_credits(plan: list[PlannedCourse], catalog: dict[str, Course]) -> float:
    return sum(catalog[c].credits for c in {p.code for p in plan} if c in catalog)


def unknown_courses(plan: list[PlannedCourse], catalog: dict[str, Course]) -> list[str]:
    """Validator check #1: every course the LLM put in the plan must exist."""
    return sorted({p.code for p in plan if p.code not in catalog})


# ---------------------------------------------------------------- example --
# ILLUSTRATIVE ONLY — structure modelled on the 2025-26 COMP requirement PDF.
# Credits/codes must come from the real catalog in the pipeline, not this file.

if __name__ == "__main__":
    catalog = {c.code: c for c in [
        Course(code="COMP 2011", title="Programming with C++", credits=4),
        Course(code="COMP 2012", title="OOP and Data Structures", credits=4),
        Course(code="COMP 2012H", title="Honors OOP and Data Structures", credits=5),
        Course(code="COMP 3711", title="Design and Analysis of Algorithms", credits=3),
        Course(code="COMP 4211", title="Machine Learning", credits=3),
        Course(code="COMP 4900", title="Academic and Professional Development", credits=0),
        Course(code="AISC 1000", title="Foundations of AI Literacy", credits=3,
               common_core_areas=["HAIC"]),
    ]}

    comp = Program(
        code="COMP", title="BEng in Computer Science", kind="major", cohort="2026-27",
        source_url="https://ugadmin.hkust.edu.hk/prog_crs/ug/202526/pdf/25-26comp.pdf",
        groups=[
            RequirementGroup(name="Programming core", category=Category.MAJOR, rules=[
                OneOf(options=[["COMP 2011", "COMP 2012"], ["COMP 2012H"]]),
                Required(courses=["COMP 3711"]),
            ], source_quote="(COMP 2011 AND COMP 2012) OR COMP 2012H"),
            RequirementGroup(name="Depth electives", category=Category.MAJOR, rules=[
                CreditsFrom(patterns=["COMP 4xxx"], min_credits=6, exclude=["COMP 4900"]),
            ]),
            RequirementGroup(name="Professional development", category=Category.MAJOR, rules=[
                EveryTerm(course="COMP 4900"),
            ]),
            RequirementGroup(name="HAIC", category=Category.COMMON_CORE, rules=[
                CommonCoreArea(area="HAIC", min_credits=3),
            ]),
        ],
    )

    plan = [
        PlannedCourse(code="AISC 1000", term="Y1 Fall", status="current"),
        PlannedCourse(code="COMP 2012H", term="Y1 Spring", status="planned"),
        PlannedCourse(code="COMP 3711", term="Y2 Fall", status="planned"),
        PlannedCourse(code="COMP 4211", term="Y3 Fall", status="planned"),
        PlannedCourse(code="COMP 9999", term="Y3 Spring", status="planned"),  # hallucinated
    ] + [PlannedCourse(code="COMP 4900", term=f"T{i}", status="planned") for i in range(8)]

    print("Unknown courses:", unknown_courses(plan, catalog))
    print("Total credits:", total_credits(plan, catalog), "/ 120")
    for r in evaluate(comp, plan, catalog):
        print(f"[{'OK ' if r.satisfied else 'NO '}] {r.category.value:12} "
              f"{r.group:25} {r.rule_type:13} {r.detail}")
    print("\nJSON schema keys:", list(Program.model_json_schema()["$defs"].keys()))
