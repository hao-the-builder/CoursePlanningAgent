"""Full plan validation (Phase 3).

Every check returns `Issue`s. An **error** blocks: the plan is wrong and the
agent must fix it. A **warning** does not block but must be shown — it ends up
in the Progress sheet's "Things to check" and in the `.docx`. **info** is
neither, just something worth saying.

Thresholds come from `data/regulations.json`, each with a source URL. Where
HKUST does not publish one the check says "verify" and names what to check
against; it never invents a number (hard rule 11). Two thresholds here are
*not* regulations and are marked as such in the code: the GPA level at which a
heavy term is worth mentioning, and how far a term may sit from the mean
before a plan stops counting as evenly spread. Both only ever produce advice.

Slots and exchange rows. A plan may contain a course the student has not
chosen yet, written `SLOT:<anything>` — "SLOT:CC-A" for a Common Core Arts
course. Slots are exempt from the course checks because there is no course
yet. Exchange rows name the HKUST requirement they are meant to cover and
carry `mapping_approved`; until that is true they are never treated as met
(hard rule 6).
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner.allocate import Allocation, allocate  # noqa: E402
from planner.intake import StudentProfile  # noqa: E402
from planner.terms import in_residence, is_regular, sort_key, term_sequence  # noqa: E402
from planner.tools import (  # noqa: E402
    courses_in,
    parse_prereq,
    regulation,
    regulation_source,
    satisfied_by,
)
from schema import (  # noqa: E402
    Course,
    EveryTerm,
    PlannedCourse,
    Program,
    RuleResult,
    evaluate,
)

Severity = Literal["error", "warning", "info"]

SLOT = re.compile(r"^SLOT:", re.I)
LEADING_CODE = re.compile(r"^([A-Z]{2,6} \d{4}[A-Z]?)\b")
FYP_TITLE = re.compile(r"final year (project|thesis)|capstone", re.I)

# Not regulations — advice thresholds, used only to decide whether to mention
# something. HKUST publishes neither.
HIGH_GPA_TARGET = 3.3          # above this, an 18-credit term is worth a word
EVEN_SPREAD_TOLERANCE = 4.0    # CLAUDE.md's own number for "evenly spread"


@dataclass(frozen=True, slots=True)
class Issue:
    severity: Severity
    check: str
    message: str
    course: str | None = None
    term: str | None = None

    def __str__(self) -> str:
        where = " · ".join(x for x in (self.term, self.course) if x)
        return f"[{self.severity}] {self.message}" + (f" ({where})" if where else "")


@dataclass
class CreditSummary:
    earned: float = 0.0          # taken + current + mapped transfer
    planned: float = 0.0
    exchange_pending: float = 0.0
    unspecified_transfer: float = 0.0

    @property
    def confirmed(self) -> float:
        """Everything except credits that still need someone's approval."""
        return self.earned + self.planned + self.unspecified_transfer

    @property
    def with_exchange(self) -> float:
        return self.confirmed + self.exchange_pending


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)
    credits: CreditSummary = field(default_factory=CreditSummary)
    per_term: dict[str, float] = field(default_factory=dict)
    rule_results: list[RuleResult] = field(default_factory=list)
    allocation: Allocation | None = None

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def infos(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "info"]

    @property
    def ok(self) -> bool:
        """No blocking errors. Warnings still have to be shown."""
        return not self.errors

    def checks(self) -> set[str]:
        return {i.check for i in self.issues}


# ------------------------------------------------------------- small bits --

def is_slot(code: str) -> bool:
    return bool(SLOT.match(code))


def real_courses(plan: list[PlannedCourse]) -> list[PlannedCourse]:
    """Rows that name an actual HKUST course the student will sit."""
    return [p for p in plan if not is_slot(p.code) and p.status != "exchange"]


SLOT_CREDITS = re.compile(r"-(\d+(?:\.\d+)?)CR$", re.I)


def slot_credits(code: str) -> float | None:
    """A slot's size, when its code states it: "SLOT:FREE-7-3CR" is 3 credits.

    Written into the code because a plan may come back from a model that was
    asked for code, term and status and returned exactly that. The row's own
    `credits` is used first; this is what makes the loss survivable.
    """
    found = SLOT_CREDITS.search(code)
    return float(found.group(1)) if found else None


def slot_label(code: str) -> str:
    """What a slot is, in words, for anything that shows one to a person.

    A bare "SLOT:FREE-7" is a placeholder the student cannot act on, and every
    builder was writing its own version of this sentence.
    """
    kind = SLOT_CREDITS.sub("", code.split(":", 1)[1] if ":" in code else "any")
    if kind.upper().startswith("FREE"):
        return "Free elective (you choose)"
    return f"Common Core {kind} course (you choose)"


def credits_of(code: str, catalog: dict[str, Course]) -> float:
    course = catalog.get(code)
    return course.credits if course else 0.0


def row_credits(entry: PlannedCourse, catalog: dict[str, Course]) -> float:
    """What one plan row is worth.

    A slot carries its own credits, because its code is a placeholder and the
    catalog has nothing to look up. Every real course reads from the catalog,
    so a row cannot quietly disagree with it: `credits` is only consulted when
    the code is not a real one.
    """
    if entry.code in catalog:
        return credits_of(entry.code, catalog)
    if entry.credits is not None:
        return float(entry.credits)
    from_code = slot_credits(entry.code)
    return from_code if from_code is not None else 0.0


def term_credits(plan: list[PlannedCourse],
                 catalog: dict[str, Course]) -> dict[str, float]:
    """Credits per term, counting a course once per term it appears in."""
    totals: dict[str, float] = defaultdict(float)
    seen: set[tuple[str, str]] = set()
    for entry in plan:
        key = (entry.term, entry.code)
        if key in seen:
            continue
        seen.add(key)
        totals[entry.term] += row_credits(entry, catalog)
    return dict(totals)


# ---------------------------------------------------------------- checks --

def unknown_courses(plan: list[PlannedCourse],
                    catalog: dict[str, Course]) -> list[Issue]:
    """Hard rule 1. Slots and exchange rows are exempt; everything else must
    be a course that exists."""
    out = []
    for code in sorted({p.code for p in real_courses(plan)}):
        if code not in catalog:
            out.append(Issue("error", "unknown_courses",
                             f"{code} is not in the {len(catalog)}-course "
                             f"catalog for this cohort, so it cannot be "
                             f"planned.", course=code))
    return out


def check_prereqs(plan: list[PlannedCourse],
                  catalog: dict[str, Course]) -> list[Issue]:
    """Prerequisites must sit in an earlier term, or come from transfer."""
    out: list[Issue] = []
    by_term: dict[str, set[str]] = defaultdict(set)
    for entry in plan:
        by_term[entry.term].add(entry.code)

    ordered = sorted(by_term, key=sort_key)
    before: set[str] = set()
    flagged: set[str] = set()

    for term in ordered:
        for code in sorted(by_term[term]):
            course = catalog.get(code)
            if not course or not course.prereq_expr:
                continue
            tree = parse_prereq(course.prereq_expr)
            met, unverifiable = satisfied_by(tree, before)
            if not met:
                needed = sorted(courses_in(tree) - before)
                out.append(Issue(
                    "error", "check_prereqs",
                    f"{code} needs {course.prereq_expr}, and none of that is "
                    f"finished before {term}."
                    + (f" Missing: {', '.join(needed[:6])}." if needed else ""),
                    course=code, term=term))
            elif unverifiable and code not in flagged:
                flagged.add(code)
                out.append(Issue(
                    "warning", "check_prereqs",
                    f"{code} has a prerequisite the plan cannot check — "
                    f"\"{unverifiable[0]}\". Verify you meet it.",
                    course=code, term=term))
        before |= by_term[term]
    return out


def _requires(a: str, b: str, catalog: dict[str, Course]) -> bool:
    """Is b one of the courses a's prerequisite sentence accepts?"""
    course = catalog.get(a)
    return bool(course and course.prereq_expr
                and b in courses_in(parse_prereq(course.prereq_expr)))


def _forced(program: Program | None) -> set[str]:
    """Courses the program requires outright, with no alternative offered."""
    if program is None:
        return set()
    from schema import Required

    out: set[str] = set()
    for group in program.groups:
        for rule in group.rules:
            if isinstance(rule, Required):
                out |= set(rule.courses)
            elif isinstance(rule, EveryTerm):
                out.add(rule.course)
    return out


def check_exclusions(plan: list[PlannedCourse], catalog: dict[str, Course],
                     program: Program | None = None) -> list[Issue]:
    """No two mutually exclusive courses in one plan.

    Two kinds of pair are reported as warnings rather than errors, because in
    both the official sources contradict each other and picking a winner would
    be inventing a fact:

      * one course is a **prerequisite** of the other. The catalog says
        MATH 1014 requires MATH 1013 and, two rows up, that MATH 1013 excludes
        MATH 1014. 17 pairs in the 2026-27 catalog read like this.
      * the program **requires both outright**, as ISOM 2500 and MATH 2411 are
        in two programs, while the catalog says they exclude each other.

    Anything else is an error, and it is actionable: an excluded pair that came
    from a `one_of` can be fixed by taking the other option.
    """
    out: list[Issue] = []
    codes = {p.code for p in real_courses(plan)}
    forced = _forced(program)
    reported: set[tuple[str, str]] = set()
    subjects = {c.split()[0] for c in codes}

    for code in sorted(codes):
        course = catalog.get(code)
        if not course:
            continue
        for exclusion in course.exclusions:
            match = LEADING_CODE.match(exclusion)
            if not match:
                named = {w for w in re.findall(r"\b[A-Z]{2,6}\b", exclusion)}
                if named & subjects:
                    out.append(Issue(
                        "warning", "check_exclusions",
                        f"{code} excludes \"{exclusion}\", which names no "
                        f"specific course, so it was not checked against your "
                        f"plan. Verify it.", course=code))
                continue

            other = match.group(1)
            pair = (code, other) if code < other else (other, code)
            if other not in codes or other == code or pair in reported:
                continue
            reported.add(pair)
            qualifier = exclusion[len(other):].strip()
            tail = f" {qualifier}" if qualifier else ""

            if _requires(code, other, catalog) or _requires(other, code, catalog):
                out.append(Issue(
                    "warning", "check_exclusions",
                    f"The catalog lists {pair[0]} and {pair[1]} as excluding "
                    f"each other, yet one is a prerequisite of the other. The "
                    f"two statements cannot both hold, so this was not treated "
                    f"as a clash. Verify with your department.", course=code))
            elif {code, other} <= forced:
                out.append(Issue(
                    "warning", "check_exclusions",
                    f"The catalog says {pair[0]} and {pair[1]} exclude each "
                    f"other, but your program's requirement PDF requires both. "
                    f"The two official sources disagree; verify with your "
                    f"department.", course=code))
            else:
                out.append(Issue(
                    "error", "check_exclusions",
                    f"{pair[0]} and {pair[1]} exclude each other, so only one "
                    f"can count toward your degree{tail}.", course=code))
    return out


def check_offering(plan: list[PlannedCourse],
                   catalog: dict[str, Course]) -> list[Issue]:
    """Is each course offered in the term it is planned for?

    There is no offering data at all: the class schedule disallows automated
    access (hard rule 7), so `data/offerings.json` is empty. Rather than
    repeat the same warning for forty courses, this says it once.
    """
    if any(catalog[p.code].terms_offered for p in plan if p.code in catalog):
        return []        # some data exists; per-course checking would go here
    return [Issue("warning", "check_offering",
                  "No term-offering data exists — the HKUST class schedule "
                  "disallows automated access, so no course in this plan has "
                  "been checked against the terms it is actually offered in. "
                  "Verify each one on the class schedule.")]


def check_load(plan: list[PlannedCourse], profile: StudentProfile,
               catalog: dict[str, Course]) -> list[Issue]:
    """Credits per term, against the student's range and the regulations."""
    out: list[Issue] = []
    low = regulation("min_credits_regular_term")
    high = regulation("max_credits_regular_term")
    source = regulation_source("max_credits_regular_term")
    exchange = set(profile.exchange_terms)
    free = set(profile.free_terms)

    for term, credits in sorted(term_credits(plan, catalog).items(),
                                key=lambda kv: sort_key(kv[0])):
        if term in free or term in exchange or not is_regular(term):
            continue
        if credits == 0:
            continue
        if high is not None and credits > high:
            out.append(Issue("error", "check_load",
                             f"{term} has {credits:g} credits; the Academic "
                             f"Regulations cap a Regular Term at {high:g} "
                             f"without the Dean's approval ({source}).",
                             term=term))
        if low is not None and credits < low:
            out.append(Issue("error", "check_load",
                             f"{term} has only {credits:g} credits; the "
                             f"Academic Regulations require at least {low:g} "
                             f"in a Regular Term ({source}).", term=term))
        if credits > profile.workload_max:
            out.append(Issue("error", "check_load",
                             f"{term} has {credits:g} credits, above the "
                             f"{profile.workload_max:g} you asked for.",
                             term=term))
        if credits < profile.workload_min:
            out.append(Issue("error", "check_load",
                             f"{term} has only {credits:g} credits, below the "
                             f"{profile.workload_min:g} you asked for.",
                             term=term))

    # Summer and Winter are not Regular Terms and HKUST publishes no limit.
    for term, credits in sorted(term_credits(plan, catalog).items(),
                                key=lambda kv: sort_key(kv[0])):
        if is_regular(term) or term == "Transfer" or credits == 0:
            continue
        if regulation("max_credits_summer_term") is None:
            out.append(Issue("warning", "check_load",
                             f"{term} has {credits:g} credits. HKUST does not "
                             f"publish a credit limit for Winter or Summer "
                             f"terms, so this was not checked — verify it with "
                             f"your department.", term=term))
    return out


def check_heavy_terms(plan: list[PlannedCourse], profile: StudentProfile,
                      catalog: dict[str, Course]) -> list[Issue]:
    """A heavy term alongside a high GPA target is worth mentioning."""
    if not profile.gpa_target or profile.gpa_target < HIGH_GPA_TARGET:
        return []
    heavy = regulation("max_credits_regular_term") or 18
    return [Issue("warning", "check_heavy_terms",
                  f"{term} carries {credits:g} credits, and you are aiming for "
                  f"a GPA of {profile.gpa_target:g}. That is a heavy term to "
                  f"do well in.", term=term)
            for term, credits in sorted(term_credits(plan, catalog).items(),
                                        key=lambda kv: sort_key(kv[0]))
            if credits >= heavy and is_regular(term)]


def check_exchange(plan: list[PlannedCourse], profile: StudentProfile,
                   programs: list[Program | None],
                   catalog: dict[str, Course]) -> list[Issue]:
    """Exchange terms hold no HKUST courses, and nothing counts until approved."""
    out: list[Issue] = []
    exchange_terms = set(profile.exchange_terms)
    if not exchange_terms and not any(p.status == "exchange" for p in plan):
        return out

    for entry in plan:
        if entry.term in exchange_terms and entry.status != "exchange":
            out.append(Issue(
                "error", "check_exchange",
                f"{entry.code} is an HKUST course placed in {entry.term}, "
                f"which you are spending on exchange.",
                course=entry.code, term=entry.term))
        if entry.status == "exchange" and entry.term not in exchange_terms:
            out.append(Issue(
                "warning", "check_exchange",
                f"{entry.code} is an exchange row but {entry.term} is not one "
                f"of your exchange terms.", course=entry.code, term=entry.term))

    pending = [p for p in plan if p.status == "exchange" and not p.mapping_approved]
    for entry in pending:
        host = f"{entry.host_course} at {entry.host_university}" \
            if entry.host_course else "the host course"
        out.append(Issue(
            "warning", "check_exchange",
            f"{host} is meant to cover {entry.code}, but the mapping is not "
            f"approved yet, so these credits are not counted as met.",
            course=entry.code, term=entry.term))

    if pending and programs:
        # A requirement is "met only via exchange" when it passes with the
        # exchange rows in the plan and fails without them. Evaluating twice
        # is the only way to know; inspecting the message text is not.
        grounded = [p for p in plan if p.status != "exchange"]
        for program in programs:
            if program is None:
                continue
            with_rows = evaluate(program, plan, catalog, terms_in_residence=1)
            without = evaluate(program, grounded, catalog, terms_in_residence=1)
            for before, after in zip(with_rows, without):
                if before.satisfied and not after.satisfied:
                    out.append(Issue(
                        "warning", "check_exchange",
                        f"{before.category.value} requirement "
                        f"\"{before.group}\" is met only by the exchange "
                        f"courses, so it is not met until the mapping is "
                        f"approved ({after.detail} without them)."))

    if regulation("exchange_credit_rules") is None and pending:
        out.append(Issue(
            "warning", "check_exchange",
            "HKUST publishes no outgoing-exchange credit rule that this plan "
            "could check against, so every exchange mapping here is treated "
            "as pending. Verify with the Study Abroad office."))
    return out


def check_free_terms(plan: list[PlannedCourse], profile: StudentProfile,
                     catalog: dict[str, Course]) -> list[Issue]:
    """A term the student asked to keep free must have nothing in it."""
    out: list[Issue] = []
    totals = term_credits(plan, catalog)
    for term in sorted(profile.free_terms, key=sort_key):
        if totals.get(term, 0.0) > 0:
            courses = sorted({p.code for p in plan if p.term == term})
            out.append(Issue("error", "check_free_terms",
                             f"You asked to keep {term} free, but it has "
                             f"{', '.join(courses)} in it.", term=term))

    used = [t for t, c in totals.items() if c > 0 and t != "Transfer"]
    if used and profile.free_terms:
        last_used = max(used, key=sort_key)
        later_free = [t for t in profile.free_terms if sort_key(t) > sort_key(last_used)]
        if later_free:
            out.append(Issue("info", "check_free_terms",
                             f"Nothing is scheduled after {last_used}, so you "
                             f"would finish before "
                             f"{min(later_free, key=sort_key)} — you can "
                             f"graduate early.", term=last_used))
    return out


def check_spread(plan: list[PlannedCourse], profile: StudentProfile,
                 catalog: dict[str, Course]) -> list[Issue]:
    """Front-loaded, back-loaded or even, as asked for."""
    # The halves come from the programme's own term sequence, not from the
    # terms that happen to have courses in them. Otherwise a deliberately
    # empty final term would shrink the second half out of existence and a
    # front-loaded plan would read as back-loaded.
    counted = term_credits(plan, catalog)
    sequence = [t.label for t in term_sequence(
        profile.cohort or "2026-27", profile.programme_years,
        use_summer=profile.use_summer, use_winter=profile.use_winter)]
    for extra in counted:
        if extra not in sequence and extra != "Transfer":
            sequence.append(extra)
    sequence.sort(key=sort_key)
    totals = {t: counted.get(t, 0.0) for t in sequence}
    if len(totals) < 2 or not sum(totals.values()):
        return []
    ordered = sorted(totals, key=sort_key)
    half = len(ordered) // 2
    first = sum(totals[t] for t in ordered[:half])
    second = sum(totals[t] for t in ordered[half:])

    if profile.spread == "front" and first < second:
        return [Issue("warning", "check_spread",
                      f"You asked for a front-loaded plan, but the first half "
                      f"carries {first:g} credits against {second:g} in the "
                      f"second.")]
    if profile.spread == "back" and second < first:
        return [Issue("warning", "check_spread",
                      f"You asked for a back-loaded plan, but the second half "
                      f"carries {second:g} credits against {first:g} in the "
                      f"first.")]
    if profile.spread == "even":
        used = {t: c for t, c in totals.items()
                if c > 0 or t not in profile.free_terms}
        used = {t: c for t, c in used.items() if c > 0}
        if not used:
            return []
        mean = sum(used.values()) / len(used)
        off = [t for t, c in used.items()
               if abs(c - mean) > EVEN_SPREAD_TOLERANCE]
        if off:
            return [Issue("warning", "check_spread",
                          f"You asked for an even spread, but "
                          f"{', '.join(sorted(off, key=sort_key))} "
                          f"{'differs' if len(off) == 1 else 'differ'} from "
                          f"the {mean:.1f}-credit average by more than "
                          f"{EVEN_SPREAD_TOLERANCE:g} credits.")]
    return []


def check_fyp(plan: list[PlannedCourse],
              catalog: dict[str, Course]) -> list[Issue]:
    """Final Year Project placement, against a regulation that does not exist."""
    fyp = sorted({p.code for p in plan if p.code in catalog
                  and FYP_TITLE.search(catalog[p.code].title)})
    if not fyp:
        return []
    required = regulation("fyp_duration_terms")
    if required is None:
        return [Issue("warning", "check_fyp",
                      f"{', '.join(fyp)} looks like a final-year project. "
                      f"HKUST publishes no rule on how many terms one must "
                      f"span, so its placement was not checked — verify it "
                      f"with your department.", course=fyp[0])]
    return []


def check_transfer(profile: StudentProfile,
                   catalog: dict[str, Course]) -> list[Issue]:
    """Mapped transfers must be real courses; unspecified ones are free only."""
    out: list[Issue] = []
    for entry in profile.transfer_credits:
        if is_slot(entry.code):
            continue
        if entry.code not in catalog:
            out.append(Issue("error", "check_transfer",
                             f"{entry.code} is listed as a transferred course "
                             f"but is not in the catalog, so it cannot be "
                             f"matched to a requirement.", course=entry.code))
        elif not entry.mapping_approved:
            out.append(Issue("warning", "check_transfer",
                             f"{entry.code} is listed as transferred but the "
                             f"mapping is not approved yet, so it is not "
                             f"counted as met.", course=entry.code))

    if profile.unspecified_transfer_credits:
        out.append(Issue(
            "warning", "check_transfer",
            f"{profile.unspecified_transfer_credits:g} transferred credits are "
            f"unspecified (the Academic Regulations call this credit-only "
            f"transfer). They count toward the 120 only as free electives, "
            f"never toward a named requirement."))

    cap = regulation("min_hkust_credits")
    total = regulation("graduation_total_credits")
    mapped = sum(credits_of(e.code, catalog) for e in profile.transfer_credits)
    brought = mapped + profile.unspecified_transfer_credits
    if cap and total and brought > total - cap:
        out.append(Issue(
            "error", "check_transfer",
            f"{brought:g} transferred credits leaves {total - brought:g} to be "
            f"earned at HKUST, below the {cap:g} the Academic Regulations "
            f"require ({regulation_source('min_hkust_credits')})."))
    return out


def check_every_term(plan: list[PlannedCourse], profile: StudentProfile,
                     program: Program | None) -> list[Issue]:
    """An every_term course is required for each Regular Term in residence —
    which excludes the terms spent on exchange."""
    if program is None:
        return []
    out: list[Issue] = []
    away = set(profile.exchange_terms)
    resident = [t for t in in_residence([p.term for p in plan]) if t not in away]

    for group in program.groups:
        for rule in group.rules:
            if not isinstance(rule, EveryTerm):
                continue
            have = {p.term for p in plan if p.code == rule.course}
            missing = [t for t in resident if t not in have]
            if missing:
                out.append(Issue(
                    "error", "check_every_term",
                    f"{rule.course} must be taken in every Regular Term you "
                    f"are in residence. Missing from "
                    f"{', '.join(missing)}.", course=rule.course))
            stray = sorted(t for t in have if t in away)
            if stray:
                out.append(Issue(
                    "warning", "check_every_term",
                    f"{rule.course} is scheduled in {', '.join(stray)}, which "
                    f"you are spending on exchange; it is not required while "
                    f"you are away.", course=rule.course))
    return out


def satisfiable(rule, catalog: dict[str, Course]) -> bool:
    """Could *any* plan satisfy this rule with the courses that exist?

    A requirement nobody can meet is a gap in the data or in what HKUST has
    published, not a mistake in the plan. The Common Core asks for 6 credits
    of HAIC and exactly one HAIC course is published for this cohort, so every
    plan would otherwise carry the same unfixable error.
    """
    from schema import ChooseN, CommonCoreArea, CreditsFrom, NAreas, OneOf, Required

    if isinstance(rule, Required):
        return all(c in catalog for c in rule.courses)
    if isinstance(rule, OneOf):
        return any(all(c in catalog for c in option) for option in rule.options)
    if isinstance(rule, ChooseN):
        return sum(1 for c in rule.courses if c in catalog) >= rule.n
    if isinstance(rule, EveryTerm):
        return rule.course in catalog
    if isinstance(rule, CreditsFrom):
        from schema import _matches
        available = sum(c.credits for code, c in catalog.items()
                        if code not in rule.exclude
                        and any(_matches(code, p) for p in rule.patterns))
        return available >= rule.min_credits
    if isinstance(rule, CommonCoreArea):
        return sum(c.credits for c in catalog.values()
                   if rule.area in c.common_core_areas) >= rule.min_credits
    if isinstance(rule, NAreas):
        pool = [c for c in catalog.values()
                if set(c.common_core_areas) & set(rule.areas)]
        areas = {a for c in pool for a in c.common_core_areas if a in rule.areas}
        return (len(areas) >= rule.n_areas
                and sum(c.credits for c in pool) >= rule.min_credits)
    return True


def check_graduation(summary: CreditSummary, paired: list[tuple[object, RuleResult]],
                     catalog: dict[str, Course]) -> list[Issue]:
    """120 credits, the programme's own total, and every requirement met."""
    out: list[Issue] = []
    needed = regulation("graduation_total_credits") or 120.0
    source = regulation_source("graduation_total_credits")

    if summary.confirmed < needed:
        if summary.with_exchange >= needed:
            out.append(Issue(
                "warning", "check_graduation",
                f"The plan reaches {needed:g} credits only by counting "
                f"{summary.exchange_pending:g} exchange credits that are not "
                f"approved yet ({summary.confirmed:g} without them)."))
        else:
            out.append(Issue(
                "error", "check_graduation",
                f"The plan comes to {summary.with_exchange:g} credits, short "
                f"of the {needed:g} needed to graduate ({source})."))

    for rule, result in paired:
        if result.satisfied:
            continue
        if satisfiable(rule, catalog):
            out.append(Issue(
                "error", "check_graduation",
                f"{result.category.value} requirement \"{result.group}\" is "
                f"not met: {result.detail}."))
        else:
            out.append(Issue(
                "warning", "check_graduation",
                f"{result.category.value} requirement \"{result.group}\" "
                f"({result.detail}) cannot be met by any plan: the published "
                f"courses for this cohort do not add up to it. Verify with "
                f"your department — this is a gap in HKUST's data, not in "
                f"your plan."))
    return out


def check_double_count(allocation: Allocation,
                       minor: Program | None) -> list[Issue]:
    """The Major/Minor double-count cap. Exceeding it is an error."""
    if minor is None:
        return []
    if not allocation.cap_known:
        return [Issue(
            "warning", "check_double_count",
            f"{allocation.double_counted_credits:g} credits count toward both "
            f"your major and {minor.code}, but that minor does not publish how "
            f"many may be shared, so the limit was not checked — verify it "
            f"with the minor programme coordinator.")]
    shared = allocation.double_counted_credits
    if not allocation.over_cap:
        # Within the cap, but the student should still know how much of the
        # minor their major is already paying for.
        return [Issue(
            "info", "check_double_count",
            f"{shared:g} of {minor.code}'s credits also count toward your "
            f"major, out of the {allocation.double_count_cap:g} that may be "
            f"shared.")] if shared else []
    if allocation.over_cap:
        return [Issue(
            "error", "check_double_count",
            f"{minor.code} lets at most "
            f"{allocation.double_count_cap:g} credits count toward both it and "
            f"your major, and this plan has already used them. "
            f"{', '.join(allocation.blocked_by_cap)} would have to count twice "
            f"as well. Take something else toward the minor that your major "
            f"does not already require.")]
    return []


# ------------------------------------------------------------ the whole lot --

def summarise(plan: list[PlannedCourse], profile: StudentProfile,
              catalog: dict[str, Course]) -> CreditSummary:
    """Credits by where they come from, each course counted once."""
    summary = CreditSummary(
        unspecified_transfer=profile.unspecified_transfer_credits)
    seen: set[str] = set()
    for entry in plan:
        if entry.code in seen:
            continue
        # A slot the student has not filled still has a size: three credits of
        # free elective count toward 120 whichever course ends up in them. A
        # slot with no credits is genuinely unknown and stays uncounted, so a
        # plan cannot reach the total on placeholders alone.
        if (is_slot(entry.code) and entry.credits is None
                and slot_credits(entry.code) is None):
            continue
        seen.add(entry.code)
        credits = row_credits(entry, catalog)
        if entry.status == "exchange":
            summary.exchange_pending += credits
        elif entry.status in ("taken", "current", "transfer"):
            summary.earned += credits
        else:
            summary.planned += credits
    return summary


def validate_plan(plan: list[PlannedCourse], profile: StudentProfile,
                  major: Program | None = None, minor: Program | None = None,
                  common_core: Program | None = None,
                  catalog: dict[str, Course] | None = None) -> ValidationReport:
    """Run every check. Programs default to the ones the profile names."""
    from planner import tools

    if catalog is None:
        catalog = tools.catalog()
    if major is None and profile.major:
        major = tools.get_program(profile.major)
    if minor is None and profile.minor:
        minor = tools.get_program(profile.minor)
    if common_core is None:
        # Broadening is "four different non-home areas", so the student's own
        # home areas have to come out before the rule can be applied.
        common_core = (tools.common_core_for(profile.major) if profile.major
                       else tools.common_core())

    programs = {"major": major, "minor": minor, "common_core": common_core}
    allocation = allocate(plan, programs, catalog)
    summary = summarise(plan, profile, catalog)

    away = set(profile.exchange_terms)
    resident = len([t for t in in_residence([p.term for p in plan])
                    if t not in away]) or 1

    # evaluate() walks groups then rules in order, so zipping its results back
    # onto the rules recovers which rule each result came from.
    results: list[RuleResult] = []
    paired: list[tuple[object, RuleResult]] = []
    for program in (major, minor, common_core):
        if program is None:
            continue
        outcome = evaluate(program, plan, catalog, terms_in_residence=resident)
        rules = [rule for group in program.groups for rule in group.rules]
        results += outcome
        paired += list(zip(rules, outcome))

    issues: list[Issue] = []
    issues += unknown_courses(plan, catalog)
    issues += check_prereqs(plan, catalog)
    issues += check_exclusions(plan, catalog, major)
    issues += check_offering(plan, catalog)
    issues += check_load(plan, profile, catalog)
    issues += check_heavy_terms(plan, profile, catalog)
    issues += check_exchange(plan, profile,
                             [major, minor, common_core], catalog)
    issues += check_free_terms(plan, profile, catalog)
    issues += check_spread(plan, profile, catalog)
    issues += check_fyp(plan, catalog)
    issues += check_transfer(profile, catalog)
    issues += check_every_term(plan, profile, major)
    issues += check_double_count(allocation, minor)
    issues += check_graduation(summary, paired, catalog)

    return ValidationReport(
        issues=issues, credits=summary,
        per_term=term_credits(plan, catalog),
        rule_results=results, allocation=allocation)
