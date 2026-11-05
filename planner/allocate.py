"""Assign each course to the requirement groups it fills (Phase 3).

This fills the three requirement columns of the Course Plan sheet — Common
Core, Major, Minor — and a course in none of them is a free elective.

Two rules constrain the assignment, and only one of them has a source:

  * **Common Core may not reuse a Major or School course.** Every program
    requirement PDF says so in its preamble, and it is recorded in
    `data/regulations.json` as `common_core_reuse_allowed: false`. So a course
    fills the Major column or the Common Core column, never both.

  * **Major and Minor may double-count, up to a cap.** The minor PDFs state it
    as a floor on single counting ("at least 9 credits ... should be
    single-counted within the minor"), which Phase 2 turned into
    `Program.max_double_count_credits`. Where a minor does not state it the
    cap is `None`, and `validate.py` says "verify" rather than inventing one
    (hard rule 11).

**The greedy order**, which CLAUDE.md asks to have written down. Courses are
placed one at a time, most constrained first:

  1. fewest candidate groups first — a course that can only fill one thing has
     no decision to make, and making it first stops a flexible course from
     taking that slot;
  2. then most credits first, so a 4-credit course lands on a requirement that
     needs 4 rather than being spent on one that needed 3;
  3. then by course code, so the result never depends on dictionary order.

Within a course, the candidate group with the largest unmet demand wins. This
is a heuristic, not an optimum: a pathological plan can leave a group short
when a different assignment would have filled it. `evaluate()` in schema.py is
what finally decides whether a requirement is met, and it does not depend on
this assignment.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    RequirementGroup,
    Required,
    _matches,
)

# Which column of the Course Plan sheet a category belongs to.
COLUMNS = {
    Category.COMMON_CORE: "common_core",
    Category.MAJOR: "major",
    Category.SCHOOL: "major",        # School requirements share the Major column
    Category.UNIVERSITY: "major",
    Category.MINOR: "minor",
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """One place a course could count."""
    column: str                 # "common_core" | "major" | "minor"
    group: str                  # the group's name, for the demand ledger
    label: str                  # what the spreadsheet cell shows


@dataclass
class Fill:
    """Where one course ended up. All three None means a free elective."""
    code: str
    credits: float
    common_core: str | None = None
    major: str | None = None
    minor: str | None = None

    @property
    def is_free_elective(self) -> bool:
        return not (self.common_core or self.major or self.minor)

    @property
    def double_counted(self) -> bool:
        return bool(self.major and self.minor)


@dataclass
class Allocation:
    """The assignment, plus the facts validate.py turns into errors."""
    fills: dict[str, Fill] = field(default_factory=dict)
    double_counted_credits: float = 0.0
    double_count_cap: float | None = None
    cap_known: bool = False
    blocked_by_cap: list[str] = field(default_factory=list)
    unfilled_groups: list[str] = field(default_factory=list)

    @property
    def over_cap(self) -> bool:
        """Did the cap actually bite?

        The assignment never *exceeds* the cap — the spreadsheet has to show a
        legal allocation. It records instead which courses the minor wanted
        but could not have, which is the same fact stated usefully: those
        courses have to be replaced with single-counted ones.
        """
        return bool(self.blocked_by_cap)

    @property
    def free_elective_credits(self) -> float:
        return sum(f.credits for f in self.fills.values() if f.is_free_elective)

    def column(self, code: str, column: str) -> str | None:
        fill = self.fills.get(code)
        return getattr(fill, column) if fill else None


# --------------------------------------------------------- what fits where --

def _area_label(rule, course: Course) -> str | None:
    """The Common Core area a course actually fills for this rule."""
    if isinstance(rule, CommonCoreArea):
        return rule.area if rule.area in course.common_core_areas else None
    if isinstance(rule, NAreas):
        hits = [a for a in rule.areas if a in course.common_core_areas]
        return hits[0] if hits else None
    return None


def fits(rule, code: str, course: Course) -> bool:
    """Could this course count toward this rule?"""
    if isinstance(rule, Required):
        return code in rule.courses
    if isinstance(rule, OneOf):
        return any(code in option for option in rule.options)
    if isinstance(rule, ChooseN):
        return code in rule.courses
    if isinstance(rule, CreditsFrom):
        return (code not in rule.exclude
                and any(_matches(code, p) for p in rule.patterns))
    if isinstance(rule, (CommonCoreArea, NAreas)):
        return _area_label(rule, course) is not None
    if isinstance(rule, EveryTerm):
        return code == rule.course
    return False


def group_demand(group: RequirementGroup, catalog: dict[str, Course]) -> float:
    """Roughly what this group is worth in credits, for ranking candidates."""
    def cost(code: str) -> float:
        return catalog[code].credits if code in catalog else 0.0

    total = 0.0
    for rule in group.rules:
        if isinstance(rule, Required):
            total += sum(cost(c) for c in rule.courses)
        elif isinstance(rule, OneOf):
            total += min(sum(cost(c) for c in o) for o in rule.options)
        elif isinstance(rule, ChooseN):
            total += sum(sorted((cost(c) for c in rule.courses))[:rule.n])
        elif isinstance(rule, (CreditsFrom, CommonCoreArea, NAreas)):
            total += rule.min_credits
        elif isinstance(rule, EveryTerm):
            total += cost(rule.course)
    return total


def candidates(code: str, course: Course,
               programs: dict[str, Program | None]) -> list[Candidate]:
    """Every group, in every program, that this course could count toward."""
    out: list[Candidate] = []
    for key, program in programs.items():
        if program is None:
            continue
        for group in program.groups:
            column = COLUMNS.get(group.category, "major")
            if key == "minor":
                column = "minor"
            elif key == "common_core":
                column = "common_core"
            for rule in group.rules:
                if not fits(rule, code, course):
                    continue
                label = _area_label(rule, course) or group.name
                out.append(Candidate(column=column, group=f"{key}:{group.name}",
                                     label=label))
                break
    return out


# ------------------------------------------------------------- the greedy --

def allocate(plan: list[PlannedCourse], programs: dict[str, Program | None],
             catalog: dict[str, Course] | None = None) -> Allocation:
    """Place every planned course. See the module docstring for the order."""
    if catalog is None:
        from planner.tools import catalog as load_catalog
        catalog = load_catalog()

    demand: dict[str, float] = {}
    for key, program in programs.items():
        if program is not None:
            for group in program.groups:
                demand[f"{key}:{group.name}"] = group_demand(group, catalog)

    minor = programs.get("minor")
    cap = minor.max_double_count_credits if minor else None
    allocation = Allocation(double_count_cap=cap,
                            cap_known=minor is not None and cap is not None)

    # Each course once, however many terms it appears in.
    unique: dict[str, Course] = {}
    for entry in plan:
        if entry.code in catalog and entry.code not in unique:
            unique[entry.code] = catalog[entry.code]

    options = {code: candidates(code, course, programs)
               for code, course in unique.items()}
    order = sorted(unique, key=lambda c: (len(options[c]) or 99,
                                          -unique[c].credits, c))

    for code in order:
        course = unique[code]
        fill = Fill(code=code, credits=course.credits)
        by_column: dict[str, list[Candidate]] = {}
        for candidate in options[code]:
            by_column.setdefault(candidate.column, []).append(candidate)

        def best(column: str) -> Candidate | None:
            picks = by_column.get(column) or []
            return max(picks, key=lambda c: demand.get(c.group, 0.0)) if picks \
                else None

        major = best("major")
        if major:
            fill.major = major.label
            demand[major.group] = max(0.0, demand[major.group] - course.credits)
        else:
            # Common Core only when the course is not already a Major course:
            # a Major or School course may not be reused for the Common Core.
            core = best("common_core")
            if core:
                fill.common_core = core.label
                demand[core.group] = max(0.0, demand[core.group] - course.credits)

        minor_pick = best("minor")
        if minor_pick:
            would_double = bool(fill.major)
            room = (cap is None
                    or allocation.double_counted_credits + course.credits <= cap)
            if not would_double or room or not allocation.cap_known:
                fill.minor = minor_pick.label
                demand[minor_pick.group] = max(
                    0.0, demand[minor_pick.group] - course.credits)
                if would_double:
                    allocation.double_counted_credits += course.credits
            else:
                allocation.blocked_by_cap.append(code)

        allocation.fills[code] = fill

    allocation.unfilled_groups = sorted(g for g, left in demand.items()
                                        if left > 0)
    return allocation
