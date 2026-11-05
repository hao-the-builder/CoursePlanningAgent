"""Deterministic tools exposed to the agent (Phase 3).

Everything here reads `data/` and nothing else — no network, no LLM. These are
the only way the agent is allowed to learn a course code, a credit value or a
requirement, so that section 2's split holds: the LLM chooses, the data knows.

  get_program(code)      one Program, variants included ("MATH-STA")
  list_programs(kind)    the index rows, for a dropdown
  search_courses(...)    keyword search over the catalog
  parse_prereq(expr)     the raw catalog sentence as a boolean tree

**Prerequisites.** The catalog states them as prose that is *mostly* boolean:
"(COMP 1021 OR COMP 1023) AND (MATH 2111 OR MATH 2121)". But it also says
things no code can check — "Level 4 in HKDSE English Language", "Grade A- or
above in PHYS 1111", "(Note: students with sufficient background may enroll
upon approval by the instructor)". Those become `Other` nodes rather than
parse failures, so a plan is never blocked by a condition the data cannot see;
`satisfied_by` reports them separately and `check_prereqs` warns instead of
erroring. A sentence that cannot be parsed at all comes back as a single
`Other`, which is the same promise kept more bluntly.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner.terms import is_regular, sort_key  # noqa: E402
from schema import (  # noqa: E402
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
    _matches,
)

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
PROGRAMS = DATA / "programs"

CODE = re.compile(r"\b[A-Z]{2,6} ?\d{4}[A-Z]?\b")

# Courses that belong at the home university, whatever the exchange is meant
# to cover. A final year project done at a host university is not the same
# qualification, and an industrial placement is arranged by HKUST.
STAY_HOME = re.compile(
    r"final year (project|thesis)|capstone|industrial experience|co-op"
    r"|undergraduate research|independent (study|work)", re.I)


# ------------------------------------------------------------ data access --

@lru_cache(maxsize=1)
def catalog() -> dict[str, Course]:
    raw = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    return {code: Course.model_validate(c) for code, c in raw.items()}


@lru_cache(maxsize=1)
def index() -> dict:
    return json.loads((DATA / "program_index.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def regulations() -> dict:
    return json.loads((DATA / "regulations.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def common_core() -> Program:
    return Program.model_validate_json(
        (DATA / "common_core.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=256)
def get_program(code: str) -> Program:
    """One program by its index code. Raises KeyError if there is no such code."""
    path = PROGRAMS / f"{code}.json"
    if not path.exists():
        raise KeyError(f"no program {code!r} in data/programs/")
    return Program.model_validate_json(path.read_text(encoding="utf-8"))


def list_programs(kind: str | None = None, school: str | None = None,
                  tier: str | None = None) -> list[dict]:
    """Index rows, for the intake dropdown. Each carries its tier."""
    rows = index()["programs"]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if school:
        rows = [r for r in rows if r["school"] == school]
    if tier:
        rows = [r for r in rows if r["tier"] == tier]
    return rows


def program_row(code: str) -> dict:
    """The index row for a program: tier, school, home_areas, parent."""
    for row in index()["programs"]:
        if row["code"] == code:
            return row
    raise KeyError(f"no program {code!r} in data/program_index.json")


def home_areas(code: str) -> list[str]:
    """The Common Core areas this program counts as its own."""
    return program_row(code)["home_areas"]


def regulation(name: str):
    """One regulation's value, or None when HKUST does not publish it."""
    rule = regulations()["rules"].get(name)
    return rule["value"] if rule else None


def regulation_source(name: str) -> str:
    """The URL behind a regulation, for the "verify" messages."""
    rule = regulations()["rules"].get(name) or {}
    source = regulations()["sources"].get(rule.get("source") or "", {})
    return source.get("url", "")


def search_courses(query: str, subject: str | None = None,
                   level: int | None = None, limit: int = 40) -> list[Course]:
    """Keyword search over code and title, best matches first."""
    words = [w for w in re.split(r"\W+", query.lower()) if w]
    results: list[tuple[int, str, Course]] = []

    for code, course in catalog().items():
        if subject and not code.startswith(f"{subject.upper()} "):
            continue
        if level and not code.split()[1].startswith(str(level)):
            continue
        haystack = f"{code} {course.title}".lower()
        if words and not all(w in haystack for w in words):
            continue
        # an exact code match first, then a title-word match, then the rest
        score = 0 if code.lower() == query.lower().strip() else (
            1 if any(w in course.title.lower() for w in words) else 2)
        results.append((score, code, course))

    results.sort(key=lambda r: (r[0], r[1]))
    return [course for _, _, course in results[:limit]]


# ------------------------------------------------------------ prereq trees --

@dataclass(frozen=True, slots=True)
class CourseReq:
    """A specific course must have been completed."""
    code: str

    def to_dict(self) -> dict:
        return {"course": self.code}


@dataclass(frozen=True, slots=True)
class Other:
    """A condition the data cannot check: a public exam level, a grade bar,
    an instructor's approval. Never a failure, always a flag."""
    text: str

    def to_dict(self) -> dict:
        return {"other": self.text}


@dataclass(frozen=True, slots=True)
class All:
    terms: tuple = field(default=())

    def to_dict(self) -> dict:
        return {"and": [t.to_dict() for t in self.terms]}


@dataclass(frozen=True, slots=True)
class Any_:
    terms: tuple = field(default=())

    def to_dict(self) -> dict:
        return {"or": [t.to_dict() for t in self.terms]}


Node = CourseReq | Other | All | Any_

# Only the structural pieces are matched; whatever lies between two of them is
# prose. Scanning the other way round — prose as its own alternative — lets a
# lazy text match swallow the course code that follows it.
_STRUCT = re.compile(r"[(\[]|[)\]]|\bAND\b|\bOR\b|/|[A-Z]{2,6} ?\d{4}[A-Z]?")
_KINDS = {"(": "open", "[": "open", ")": "close", "]": "close",
          "AND": "and", "OR": "or", "/": "or"}


def _tokenize(expr: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    position = 0
    for match in _STRUCT.finditer(expr):
        gap = expr[position:match.start()].strip()
        if gap:
            out.append(("text", gap))
        token = match.group()
        out.append((_KINDS.get(token, "code"), token))
        position = match.end()
    tail = expr[position:].strip()
    if tail:
        out.append(("text", tail))
    return out


def _normalise(code: str) -> str:
    """"COMP1021" and "COMP 1021" are the same course."""
    match = re.fullmatch(r"([A-Z]{2,6}) ?(\d{4}[A-Z]?)", code.strip())
    return f"{match.group(1)} {match.group(2)}" if match else code.strip()


def parse_prereq(expr: str | None) -> Node | None:
    """The catalog's prerequisite sentence as a boolean tree, or None.

    AND binds tighter than OR, matching the way the catalog brackets its
    expressions. "/" is read as OR, which is how the catalog writes a short
    list of alternatives ("COMP 1021 / COMP 1023").
    """
    if not expr or not expr.strip():
        return None
    tokens = _tokenize(expr)
    if not tokens:
        return Other(expr.strip())

    position = 0

    def peek() -> str | None:
        return tokens[position][0] if position < len(tokens) else None

    def parse_or() -> Node:
        terms = [parse_and()]
        while peek() == "or":
            nonlocal position
            position += 1
            terms.append(parse_and())
        return terms[0] if len(terms) == 1 else Any_(tuple(terms))

    def parse_and() -> Node:
        # Two atoms side by side with no operator between them mean both, as in
        # "ISOM 3540 (Note: ... upon approval by the instructor)" and
        # "COMP 1022P (prior to 2025-26)". Reading that as AND keeps the course
        # and leaves its qualifier as an Other beside it.
        terms = [parse_atom()]
        while peek() in {"and", "open", "code", "text"}:
            nonlocal position
            if peek() == "and":
                position += 1
            terms.append(parse_atom())
        return terms[0] if len(terms) == 1 else All(tuple(terms))

    def parse_atom() -> Node:
        nonlocal position
        if position >= len(tokens):
            return Other("")
        kind, value = tokens[position]
        position += 1
        if kind == "open":
            inner = parse_or()
            if peek() == "close":
                position += 1
            return inner
        if kind == "code":
            return CourseReq(_normalise(value))
        if kind == "close":
            return parse_atom()
        return Other(value)

    try:
        tree = parse_or()
    except RecursionError:
        return Other(expr.strip())
    return tree if position >= len(tokens) else All((tree, Other(
        " ".join(v for _, v in tokens[position:]))))


def courses_in(node: Node | None) -> set[str]:
    """Every course code the expression mentions."""
    if node is None:
        return set()
    if isinstance(node, CourseReq):
        return {node.code}
    if isinstance(node, Other):
        return set()
    return {c for term in node.terms for c in courses_in(term)}


def satisfied_by(node: Node | None, done: set[str]) -> tuple[bool, list[str]]:
    """Is the prerequisite met by `done`, and what could not be checked?

    Returns (satisfied, unverifiable). An `Other` is treated as satisfied so
    that a grade bar or an instructor's approval never blocks a plan, but it
    is returned so the caller can say "verify" (hard rule 11's spirit).
    """
    if node is None:
        return True, []
    if isinstance(node, CourseReq):
        return node.code in done, []
    if isinstance(node, Other):
        return True, [node.text]
    if isinstance(node, All):
        results = [satisfied_by(t, done) for t in node.terms]
        return all(ok for ok, _ in results), [u for _, us in results for u in us]

    results = [satisfied_by(t, done) for t in node.terms]
    if any(ok and not us for ok, us in results):
        return True, []                       # a branch is met outright
    met = [us for ok, us in results if ok]
    return bool(met), [u for us in met for u in us]


def common_core_for(program_code: str) -> Program:
    """The Common Core program with this student's home areas removed.

    `data/common_core.json` lists all six Broadening areas, because the rule
    is "12 credits from four different **non-home** areas" and which areas are
    home depends on the program. The home areas are published per program and
    live in `data/program_index.json`; this is where the two meet.
    """
    from schema import NAreas, RequirementGroup

    base = common_core()
    home = set(home_areas(program_code))
    if not home:
        return base

    groups = []
    for group in base.groups:
        rules = []
        for rule in group.rules:
            if isinstance(rule, NAreas):
                rule = NAreas(areas=[a for a in rule.areas if a not in home],
                              n_areas=rule.n_areas, min_credits=rule.min_credits)
            rules.append(rule)
        groups.append(RequirementGroup(name=group.name, category=group.category,
                                       rules=rules,
                                       source_quote=group.source_quote))
    return base.model_copy(update={"groups": groups})


# ------------------------------------------------------------ draft plans --
# A feasible plan, built from the rules by plain code.
#
# Section 2 of CLAUDE.md puts "course codes, credits, prerequisites,
# exclusions, requirement rules" on the data side of the line and "choosing
# paths, writing explanations" on the LLM's. Picking a set of courses that
# satisfies a rule is the first kind of job, so it is done here: the agent
# hands the LLM a feasible skeleton and asks it to vary and explain it, rather
# than asking it to assemble 40 course codes from memory. A plan this builds
# is a starting point, never the answer - validate.py still has the last word.


def _cheapest(option: list[str], chosen: set[str],
              catalog: dict[str, Course]) -> float:
    """What this option adds, counting a course already chosen as free."""
    return sum(0.0 if c in chosen else catalog[c].credits
               for c in option if c in catalog)


def _clashes(code: str, chosen: set[str], catalog: dict[str, Course]) -> bool:
    """Would adding this course break an exclusion with one already chosen?

    Self-contradicting exclusions - where one course is the other's
    prerequisite - are ignored, the same way validate.py reports rather than
    enforces them.
    """
    course = catalog.get(code)
    if not course:
        return True
    for other in chosen:
        pair = (course.exclusions, catalog[other].exclusions if other in catalog else [])
        named = any(e.startswith(other) for e in pair[0]) or \
            any(e.startswith(code) for e in pair[1])
        if not named:
            continue
        if _is_prereq(code, other, catalog) or _is_prereq(other, code, catalog):
            continue
        return True
    return False


def _is_prereq(a: str, b: str, catalog: dict[str, Course]) -> bool:
    course = catalog.get(a)
    return bool(course and course.prereq_expr
                and b in courses_in(parse_prereq(course.prereq_expr)))


def _pick(candidates: list[str], want: float, chosen: set[str],
          catalog: dict[str, Course]) -> list[str]:
    """Take courses until `want` credits are covered, cheapest choice first.

    Courses with no prerequisite come first, because a draft that needs a
    chain of three prerequisites to reach one elective is harder to schedule
    and no better.
    """
    taken: list[str] = []
    have = 0.0
    ordered = sorted(
        (c for c in candidates if c in catalog and c not in chosen),
        key=lambda c: (bool(catalog[c].prereq_expr), -catalog[c].credits, c))
    for code in ordered:
        if have >= want:
            break
        if _clashes(code, chosen, catalog):
            continue
        taken.append(code)
        chosen.add(code)
        have += catalog[code].credits
    return taken


def _area_courses(area: str, catalog: dict[str, Course]) -> list[str]:
    return [code for code, c in catalog.items() if area in c.common_core_areas]


def required_set(program: Program, catalog: dict[str, Course],
                 chosen: set[str] | None = None) -> tuple[set[str], list[str]]:
    """Courses one program's rules call for, and its every-term courses."""
    chosen = set() if chosen is None else chosen
    every_term: list[str] = []
    deferred: list = []

    for group in program.groups:
        for rule in group.rules:
            if isinstance(rule, Required):
                chosen |= {c for c in rule.courses if c in catalog}
            elif isinstance(rule, EveryTerm):
                if rule.course in catalog:
                    every_term.append(rule.course)
            else:
                deferred.append(rule)

    for rule in deferred:
        if isinstance(rule, OneOf):
            best = min(rule.options,
                       key=lambda o: (_cheapest(o, chosen, catalog), o))
            chosen |= {c for c in best if c in catalog}
        elif isinstance(rule, ChooseN):
            have = [c for c in rule.courses if c in chosen]
            _pick([c for c in rule.courses if c not in chosen],
                  sum(catalog[c].credits for c in
                      sorted(rule.courses, key=lambda c: catalog[c].credits
                             if c in catalog else 0)[:max(0, rule.n - len(have))]),
                  chosen, catalog)
        elif isinstance(rule, CreditsFrom):
            matching = [c for c in catalog
                        if c not in rule.exclude
                        and any(_matches(c, p) for p in rule.patterns)]
            covered = sum(catalog[c].credits for c in chosen if c in matching)
            _pick(matching, rule.min_credits - covered, chosen, catalog)
        elif isinstance(rule, CommonCoreArea):
            pool = _area_courses(rule.area, catalog)
            covered = sum(catalog[c].credits for c in chosen if c in pool)
            _pick(pool, rule.min_credits - covered, chosen, catalog)
        elif isinstance(rule, NAreas):
            per = rule.min_credits / rule.n_areas
            for area in rule.areas[:rule.n_areas]:
                pool = _area_courses(area, catalog)
                covered = sum(catalog[c].credits for c in chosen if c in pool)
                _pick(pool, per - covered, chosen, catalog)
    return chosen, every_term


def _depth(code: str, chosen: set[str], catalog: dict[str, Course],
           seen: frozenset[str] = frozenset()) -> int:
    """How many terms of prerequisites sit under this course, within the plan."""
    course = catalog.get(code)
    if not course or not course.prereq_expr or code in seen:
        return 0
    needed = courses_in(parse_prereq(course.prereq_expr)) & chosen
    if not needed:
        return 0
    return 1 + max(_depth(c, chosen, catalog, seen | {code}) for c in needed)


def _height(code: str, chosen: set[str], catalog: dict[str, Course],
            cache: dict[str, int]) -> int:
    """How long a chain of courses waits on this one, inside the plan.

    Scheduling the deepest chains first is what stops a four-link chain such
    as COMP 1023 -> 2011 -> 2611 -> 3511 from being crowded out by free
    electives that could have gone in any term.
    """
    if code in cache:
        return cache[code]
    cache[code] = 0
    best = 0
    for other in chosen:
        course = catalog.get(other)
        if not course or not course.prereq_expr:
            continue
        if code in courses_in(parse_prereq(course.prereq_expr)):
            best = max(best, 1 + _height(other, chosen, catalog, cache))
    cache[code] = best
    return best


def _target(remaining_credits: float, remaining_terms: int, low: float,
            high: float, spread: str) -> float:
    """How many credits to aim for in the next term.

    Recomputed each term from what is left, so a term is never left under the
    minimum load and the last one is never asked to absorb the remainder.
    """
    if remaining_terms <= 0:
        return high
    base = remaining_credits / remaining_terms
    if spread == "front":
        base *= 1.2
    elif spread == "back":
        base *= 0.8
    return min(high, max(low, base))


def draft_plan(profile, major: Program, minor: Program | None = None,
               common_core: Program | None = None,
               catalog: dict[str, Course] | None = None,
               spread: str | None = None) -> list[PlannedCourse]:
    """One feasible plan for this student, or as close as the data allows."""
    from planner.terms import term_sequence
    from schema import PlannedCourse

    if catalog is None:
        catalog = globals()["catalog"]()
    if common_core is None and profile.major:
        common_core = common_core_for(profile.major)

    done = {p.code for p in profile.already_taken()}
    chosen: set[str] = set(done)
    every_term: list[str] = []
    for program in (major, minor, common_core):
        if program is not None:
            chosen, extra = required_set(program, catalog, chosen)
            every_term += extra

    # Free electives up to the degree total.
    needed = regulation("graduation_total_credits") or 120.0
    have = sum(catalog[c].credits for c in chosen if c in catalog)
    have += profile.unspecified_transfer_credits
    if have < needed:
        fillers = [c for c, course in catalog.items()
                   if not course.prereq_expr and course.credits == 3
                   and not course.common_core_areas]
        _pick(sorted(fillers), needed - have, chosen, catalog)

    # Schedule what is left, prerequisites first.
    to_place = sorted(chosen - done - set(every_term),
                      key=lambda c: (_depth(c, chosen, catalog), c))
    terms = [t.label for t in term_sequence(
        profile.cohort or "2026-27", profile.programme_years,
        use_summer=profile.use_summer, use_winter=profile.use_winter)]
    free = set(profile.free_terms)
    away = set(profile.exchange_terms)
    usable = [t for t in terms if t not in free]

    low = regulation("min_credits_regular_term") or 12.0
    high = regulation("max_credits_regular_term") or 18.0
    low, high = max(low, profile.workload_min), min(high, profile.workload_max)

    plan: list[PlannedCourse] = []
    for entry in profile.already_taken():
        plan.append(entry)
    for term in usable:
        for code in every_term:
            if term not in away and is_regular(term):
                plan.append(PlannedCourse(code=code, term=term, status="planned"))

    loaded = {t: 0.0 for t in usable}
    heights: dict[str, int] = {}
    remaining = sorted(
        to_place,
        key=lambda c: (-_height(c, chosen, catalog, heights),
                       _depth(c, chosen, catalog), c))

    def ready(code: str, before: set[str]) -> bool:
        course = catalog.get(code)
        if not course or not course.prereq_expr:
            return True
        met, _ = satisfied_by(parse_prereq(course.prereq_expr), before)
        return met

    def credits_of(code: str) -> float:
        return catalog[code].credits if code in catalog else 0.0

    low_ = low

    # A term on exchange is not an empty term: the student takes courses at
    # the host university and maps them back. Fill it with the requirements
    # the exchange is meant to cover, as rows that are explicitly pending
    # (hard rule 6), choosing courses nothing else depends on so no
    # prerequisite chain is broken by being away.
    for term in sorted(away, key=sort_key):
        if term not in usable:
            continue
        # A term abroad is a full term, not a light one: under-filling it
        # pushes credits back onto the HKUST terms, which is what makes an
        # exchange plus a free final term look impossible when it is not.
        budget = high
        for code in sorted(remaining,
                           key=lambda c: (heights.get(c, 0), -credits_of(c), c)):
            if heights.get(code, 0) or credits_of(code) > budget:
                continue
            if STAY_HOME.search(catalog[code].title if code in catalog else ""):
                continue        # a final year project is not done abroad
            plan.append(PlannedCourse(
                code=code, term=term, status="exchange",
                host_course="(host course to be confirmed)",
                host_university=(profile.exchange.host_university
                                 if profile.exchange else None),
                mapping_approved=False,
                note="Pick a host course that maps to this requirement and "
                     "get the mapping approved before you go."))
            budget -= credits_of(code)
            remaining.remove(code)

    open_terms = [t for t in usable if t not in away]
    for index, term in enumerate(open_terms):
        # A course becomes available when its prerequisite is met by the
        # courses in *earlier* terms, so the set is frozen before filling.
        before = {p.code for p in plan
                  if sort_key(p.term) < sort_key(term)} | done
        left = sum(credits_of(c) for c in remaining)
        target = _target(left, len(open_terms) - index, low, high,
                         spread or profile.spread)
        moved = True
        while moved and remaining:
            moved = False
            for code in list(remaining):
                credits = credits_of(code)
                ceiling = target if loaded[term] >= low else high
                if loaded[term] + credits > min(ceiling, high):
                    continue
                if not ready(code, before):
                    continue
                plan.append(PlannedCourse(code=code, term=term, status="planned"))
                loaded[term] += credits
                remaining.remove(code)
                moved = True

    # A relaxation pass: anything the shaped targets could not take is
    # offered to the emptiest term that is ready for it, up to the
    # regulation ceiling. Going by load rather than by date is what keeps a
    # tight plan - an exchange term plus a free term leaves six terms for a
    # 120-credit degree - from piling the remainder onto the last one.
    for _ in range(len(open_terms) + 1):
        if not remaining:
            break
        moved = False
        for term in sorted(open_terms, key=lambda t: (loaded[t], sort_key(t))):
            before = {p.code for p in plan
                      if sort_key(p.term) < sort_key(term)} | done
            for code in list(remaining):
                credits = credits_of(code)
                if loaded[term] + credits > high or not ready(code, before):
                    continue
                plan.append(PlannedCourse(code=code, term=term,
                                          status="planned"))
                loaded[term] += credits
                remaining.remove(code)
                moved = True
        if not moved:
            break

    # Make room. A term left at 17 of an 18-credit ceiling wastes a credit,
    # and six such terms can leave a whole course unplaceable. For each
    # course still waiting, try moving one already-placed course that nothing
    # depends on into another term, to open a gap big enough.
    def earlier(term: str) -> set[str]:
        return {p.code for p in plan if sort_key(p.term) < sort_key(term)} | done

    for code in list(remaining):
        need = credits_of(code)
        for term in sorted(open_terms, key=lambda t: -loaded[t]):
            if not ready(code, earlier(term)):
                continue
            movable = [p for p in plan if p.term == term
                       and p.status == "planned"
                       and not heights.get(p.code, 0)]
            for row in sorted(movable, key=lambda r: -credits_of(r.code)):
                freed = credits_of(row.code)
                if loaded[term] - freed + need > high:
                    continue
                for other in sorted(open_terms, key=lambda t: loaded[t]):
                    if other == term or loaded[other] + freed > high:
                        continue
                    if not ready(row.code, earlier(other)):
                        continue
                    plan.remove(row)
                    plan.append(PlannedCourse(code=row.code, term=other,
                                              status="planned"))
                    loaded[term] -= freed
                    loaded[other] += freed
                    plan.append(PlannedCourse(code=code, term=term,
                                              status="planned"))
                    loaded[term] += need
                    remaining.remove(code)
                    break
                if code not in remaining:
                    break
            if code not in remaining:
                break

    # Anything still unplaced goes in the emptiest term, where validate.py
    # will object: a draft that will not schedule is a fact about the
    # requirements, not something to bury.
    for code in list(remaining):
        term = min(open_terms, key=lambda t: loaded[t]) if open_terms             else "Y4 Spring"
        plan.append(PlannedCourse(code=code, term=term, status="planned"))
        loaded[term] = loaded.get(term, 0.0) + credits_of(code)
    return plan
