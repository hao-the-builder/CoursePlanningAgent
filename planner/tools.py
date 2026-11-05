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

from schema import Course, Program  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
PROGRAMS = DATA / "programs"

CODE = re.compile(r"\b[A-Z]{2,6} ?\d{4}[A-Z]?\b")


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
