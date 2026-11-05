"""Draft data/programs/{CODE}.json from the requirement PDFs (Phase 2, Part B).

Reads each PDF through pipeline/pdf_to_text.py and maps its rows onto the rule
types in schema.py. The PDFs are regular enough to read deterministically, and
deterministic beats hand-transcription over ~130 files: it cannot mistype a
course code, and anything it does not understand is reported rather than
guessed. Part D (pipeline/check_program.py) is the gate that every draft has
to pass before it is given a tier.

The shapes it recognises, after pdf_to_text has rebuilt the columns:

    Engineering Fundamental Course(s)       a group heading
    COMP | 1023 | Intro to Python | 3       a course row
    MATH | Note: <boolean expression> | 4-6 a choice; the rows under it are
                                            its options, not requirements
    COMP | COMP Electives (5 courses from the specified elective list) | 15
                                            an elective; the rows under it are
                                            its candidate list
    Track Study / <Name> Track              a variant (see below)
    Option(s)  / <Name> Option              a variant

**Variants.** 22 programs offer tracks or options, and a Program holds one flat
list of groups that must *all* be met, so each selectable variant is written as
its own file: the shared requirements plus that one variant's groups, with
`parent` naming the base program (DECISIONS.md records this). Where a PDF says
"students should follow one of the tracks", the base file cannot be completed on
its own and is marked `unsupported` so the agent asks for a track first.

**Caveats vs unparsed_lines.** A line that yields no rule at all goes to
`unparsed_lines`, which Part D treats as disqualifying. A line that yields a
rule but states a refinement no rule type can carry ("at least 3 courses from
one area and at least 2 outside it") yields the rule and records a `caveat`,
which travels to the .docx and the Progress sheet's "Things to check".

Usage:
    python pipeline/extract_programs.py                 # all programs
    python pipeline/extract_programs.py COMP MATH       # just these
    python pipeline/extract_programs.py --dump COMP     # show the parse
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdfplumber  # noqa: E402

from pipeline.fetcher import RAW, REPO, _utf8_stdout  # noqa: E402
from pipeline.pdf_to_text import render  # noqa: E402
from schema import (  # noqa: E402
    Category,
    ChooseN,
    Course,
    CreditsFrom,
    EveryTerm,
    OneOf,
    Program,
    RequirementGroup,
    Required,
    Tier,
)

DATA = REPO / "data"
PROGRAMS = DATA / "programs"
REQUIREMENTS = RAW / "requirements"
INDEX = REQUIREMENTS / "_index" / "manifest.json"
COHORT = "2026-27"
MAX_LEVEL = 5          # the catalog tops out at 5000-level

SECTIONS = {
    "Major Requirements": Category.MAJOR,
    "Minor Requirements": Category.MINOR,
    "Extended Major Requirements": Category.MAJOR,
    "School Requirements": Category.SCHOOL,
}
GROUP_HEADINGS = {
    "Major Pre-requisite course(s)", "Engineering Fundamental Course(s)",
    "Required Course(s)", "Required Courses", "Elective(s)", "Elective Course(s)",
}
# "Others" heads a group of its own in MATH, but in CHEM it heads the tail of an
# elective list, so it only starts a group when no elective list is open.
SOFT_HEADINGS = {"Others", "Other(s)"}
# "Core Area", "Restricted Electives" and the like name a sub-list *inside* an
# elective list, so they must not be mistaken for the start of a new group.
VARIANT_HEADING = re.compile(r"^([A-Z][^|]{2,70}?) (Track|Option)$")
NOTE = re.compile(r"^Note:\s*(.*)$", re.S)
CODE = re.compile(r"[A-Z]{2,6} \d{4}[A-Z]?")
NUMBER_CELL = re.compile(r"^(\d{4}[A-Z]?)\**$")
CREDIT_CELL = re.compile(r"^(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?$")
FOOTER = re.compile(r"^20\d\d-\d\d .*\(\d[YP]?\).*Page \d+$")
PAGE_TITLE = re.compile(r"^(School|Academy|Division) of .+ - ")
EVERY_TERM = re.compile(r"every regular term", re.I)
EXEMPTION = re.compile(r"\bexempted from\b", re.I)
# "Note: Design Fundamentals: ISDN 1001 OR ..." — a label before the expression
NOTE_LABEL = re.compile(r"^([A-Z][\w &/'-]{2,40}):\s+(?=[A-Z]{2,6} ?\d{4}|[(\[])")
ANY_N_COURSES = re.compile(r"\bany (\d+|one|two|three|four|five|six) courses?\b", re.I)
# "Any SOSC courses", "Any ELEC courses at 3000-level"
ANY_SUBJECT = re.compile(r"^(?:any|all) ([A-Z]{2,6})\b[\w ]*courses?\b", re.I)

# Elective wordings, in the order they are tried.
LEVEL_ELECTIVE = re.compile(
    r"\b([A-Z]{2,6})\s+((?:\d000-?/?)+)\s*level( or above)?")
# "Mathematics courses at 1000- and 2000- level", "... at 3000- level or above"
LEVEL_RANGE = re.compile(r"(\d)000-?\s*(?:level)?", re.I)
LEVEL_OR_ABOVE = re.compile(r"(\d)000-?\s*level or above", re.I)
LIST_ELECTIVE = re.compile(
    r"\b(?:any\s+)?(\d+|one|two|three|four|five|six)\s+courses?\s+from the specified",
    re.I)
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


# ------------------------------------------------------------ expressions --

def to_options(expression: str) -> list[list[str]] | None:
    """A boolean course expression as a list of alternatives (its DNF).

    "[(MATH 1013 OR MATH 1023) AND (MATH 1014 OR MATH 1024)] OR [MATH 1020]"
    becomes [[1013,1014], [1013,1024], [1023,1014], [1023,1024], [1020]].
    Returns None if the text is not a pure expression over course codes.
    """
    tokens = re.findall(r"[A-Z]{2,6} \d{4}[A-Z]?|\bAND\b|\bOR\b|[()\[\]]", expression)
    if not tokens or not any(CODE.fullmatch(t) for t in tokens):
        return None
    if re.sub(r"[A-Z]{2,6} \d{4}[A-Z]?|\bAND\b|\bOR\b|[()\[\],/.\s]", "", expression):
        return None                       # prose left over: not a pure expression

    def parse_any(i: int) -> tuple[list[list[str]], int]:
        options, i = parse_all(i)
        while i < len(tokens) and tokens[i] == "OR":
            right, i = parse_all(i + 1)
            options = options + right
        return options, i

    def parse_all(i: int) -> tuple[list[list[str]], int]:
        options, i = parse_one(i)
        while i < len(tokens) and tokens[i] == "AND":
            right, i = parse_one(i + 1)
            options = [a + b for a in options for b in right]
        return options, i

    def parse_one(i: int) -> tuple[list[list[str]], int]:
        if i >= len(tokens):
            raise ValueError("expression ends early")
        if tokens[i] in "([":
            options, i = parse_any(i + 1)
            if i >= len(tokens) or tokens[i] not in ")]":
                raise ValueError("unbalanced bracket")
            return options, i + 1
        if not CODE.fullmatch(tokens[i]):
            raise ValueError(f"unexpected {tokens[i]!r}")
        return [[tokens[i]]], i + 1

    try:
        options, i = parse_any(0)
    except (ValueError, IndexError):
        return None
    return options if i == len(tokens) else None


def split_note(text: str) -> tuple[str, str]:
    """A Note's expression and its trailing prose qualifier, if any."""
    for opener, closer in (("[", "]"), ("(", ")")):
        depth = 0
        for pos, ch in enumerate(text):
            depth += (ch == opener) - (ch == closer)
            if depth == 1 and ch == opener and re.search(
                    r"[a-z]{4}", text[pos:]) and not CODE.search(
                    text[pos:pos + 12]):
                return text[:pos].strip(), text[pos:].strip()
    return text.strip(), ""


# ------------------------------------------------------------------ model --

@dataclass
class Pending:
    """A Note or elective row whose course rows have not been read yet."""
    line: str
    kind: str                      # "note" | "elective"
    text: str
    credits: tuple[float, float | None] | None
    courses: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)


def level_patterns(subject: str, text: str) -> list[str]:
    """Code patterns for a candidate line written as levels, not codes.

    "MATH | Mathematics courses at 3000- level or above" -> MATH 3xxx..5xxx
    "MATH | Mathematics courses at 1000- and 2000- level" -> MATH 1xxx, 2xxx
    """
    above = LEVEL_OR_ABOVE.search(text)
    if above:
        return [f"{subject} {n}xxx"
                for n in range(int(above.group(1)), MAX_LEVEL + 1)]
    levels = sorted({int(m.group(1)) for m in LEVEL_RANGE.finditer(text)})
    return [f"{subject} {n}xxx" for n in levels]


@dataclass
class Variant:
    name: str                      # "" for the base program
    kind: str                      # "base" | "track" | "option"
    groups: list[RequirementGroup] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)


def cells_of(line: str) -> list[str]:
    return [c.strip() for c in line.split(" | ")]


def course_row(cells: list[str]) -> str | None:
    """The course code a table row names, in catalog spelling, or None.

    Three spellings occur: the code split over two cells, written whole, or
    written without its space ("HUMA1000", in the SHSS minor lists).
    """
    if len(cells) >= 3 and re.fullmatch(r"[A-Z]{2,6}", cells[0]):
        number = NUMBER_CELL.match(cells[1])
        if number:
            return f"{cells[0]} {number.group(1)}"
    if len(cells) >= 2:
        whole = re.match(r"([A-Z]{2,6}) ?(\d{4}[A-Z]?)\**(.*)$", cells[0])
        if whole and not whole.group(3).strip().lower().startswith("-level"):
            return f"{whole.group(1)} {whole.group(2)}"
    return None


def credits_of(cells: list[str]) -> tuple[float, float | None] | None:
    match = CREDIT_CELL.match(cells[-1])
    if not match:
        return None
    return float(match.group(1)), float(match.group(2)) if match.group(2) else None


# ------------------------------------------------------------- the parser --

class Builder:
    """Collects rules into groups, flushing when the heading changes."""

    def __init__(self) -> None:
        self.groups: list[RequirementGroup] = []
        self.name: str | None = None
        self.category = Category.MAJOR
        self.rules: list = []
        self.quotes: list[str] = []

    def heading(self, name: str | None, category: Category | None = None) -> None:
        self.flush()
        if name is not None:
            self.name = name
        if category:
            self.category = category

    def add(self, rule, quote: str) -> None:
        if self.name is None:
            self.name = "Requirements"
        self.rules.append(rule)
        self.quotes.append(quote)

    def flush(self) -> None:
        if self.name and self.rules:
            self.groups.append(RequirementGroup(
                name=self.name, category=self.category, rules=self.rules,
                source_quote="\n\n".join(self.quotes)))
        self.rules, self.quotes = [], []


def _elective_rules(pending: Pending) -> tuple[list, str]:
    """Rules for an elective row, plus a caveat if the wording says more."""
    low = pending.credits[0] if pending.credits else 0.0
    caveat = ""

    if pending.patterns and not pending.courses:
        caveat = (f"{pending.text.strip()} -- the elective list is given as "
                  f"course levels rather than codes, so any exclusions it "
                  f"names are not applied. Confirm the list with your advisor.")
        return [CreditsFrom(patterns=list(dict.fromkeys(pending.patterns)),
                            min_credits=low)], caveat

    level = LEVEL_ELECTIVE.search(pending.text)
    if level and not pending.courses:
        subject = level.group(1).upper()
        levels = sorted({int(d) for d in re.findall(r"(\d)000", level.group(2))})
        if level.group(3):                       # "... or above"
            levels = list(range(levels[0], MAX_LEVEL + 1))
        patterns = [f"{subject} {n}xxx" for n in levels]
        return [CreditsFrom(patterns=patterns, min_credits=low)], caveat

    if pending.courses:
        unique = list(dict.fromkeys(pending.courses))
        rules: list = [CreditsFrom(patterns=unique, min_credits=low)]
        count = LIST_ELECTIVE.search(pending.text)
        if count:
            n = WORDS.get(count.group(1).lower()) or int(count.group(1))
            rules.insert(0, ChooseN(n=n, courses=unique))
        if re.search(r"at least .*(?:area|each)|may not be reused|at most one",
                     pending.text, re.I):
            caveat = (f"{pending.text.strip()} -- the credits and the course "
                      f"count are checked, but the extra condition in this "
                      f"sentence is not. Confirm it with your advisor.")
        return rules, caveat

    # "Any SOSC courses", "Any ELEC courses at 3000-level": the eligible set is
    # named by subject and level rather than listed. Worth keeping even when no
    # credit minimum is stated, because allocate.py needs to know what fills it.
    subject = ANY_SUBJECT.match(pending.text)
    if subject:
        name = subject.group(1).upper()
        patterns = level_patterns(name, pending.text) or [
            f"{name} {n}xxx" for n in range(1, MAX_LEVEL + 1)]
        if low == 0:
            caveat = (f"{pending.text.strip()} -- the requirement PDF states no "
                      f"credit minimum here, so nothing is enforced; the courses "
                      f"that count are recorded.")
        return [CreditsFrom(patterns=patterns, min_credits=low)], caveat

    return [], caveat


def _note_rules(pending: Pending) -> tuple[list, str, str]:
    """Rules for a Note row: (rules, caveat, unparsed)."""
    expression, qualifier = split_note(pending.text)

    if EVERY_TERM.search(pending.text):
        found = CODE.findall(pending.text)
        if len(found) == 1:
            return [EveryTerm(course=found[0])], "", ""
        return [], "", pending.line

    label = NOTE_LABEL.match(expression)
    if label:
        expression = expression[label.end():]

    options = to_options(expression)
    if options is None:
        if EXEMPTION.search(pending.text):
            return [], (f"{pending.text.strip()} -- an exemption, not a "
                        f"requirement; it is not applied automatically."), ""
        return [], "", pending.line

    pick = ANY_N_COURSES.search(qualifier)
    if pick and all(len(o) == 1 for o in options):
        n = WORDS.get(pick.group(1).lower()) or int(pick.group(1))
        return ([ChooseN(n=n, courses=[o[0] for o in options])],
                "" if n > 1 else qualifier, "")

    rule = Required(courses=options[0]) if len(options) == 1 else OneOf(options=options)
    caveat = f"{expression} -- {qualifier}" if qualifier else ""
    return [rule], caveat, ""


def parse(lines: list[str]) -> tuple[list[Variant], bool, list[str]]:
    """Variants of one program, whether its track choice is mandatory, remarks."""
    base = Variant("", "base")
    variants = [base]
    builders = {"": Builder()}
    current = base
    pending: Pending | None = None
    started = False
    mandatory = False
    remarks: list[str] = []
    prose: list[str] = []
    in_remarks = False

    def close() -> None:
        nonlocal pending
        if pending is None:
            return
        held, pending = pending, None
        if held.kind == "note":
            rules, caveat, bad = _note_rules(held)
        else:
            rules, caveat = _elective_rules(held)
            bad = ""
        for rule in rules:
            builders[current.name].add(rule, held.line)
        if caveat:
            current.caveats.append(caveat)
        if bad or (not rules and not caveat):
            current.unparsed.append(held.line)

    def flush_prose() -> None:
        """A wrapped paragraph of programme rules: a CGA bar, a declaration
        deadline, a no-reuse clause. Real conditions, but not course
        requirements, so they travel as caveats rather than blocking a tier."""
        if prose:
            current.caveats.append(" ".join(prose))
            prose.clear()

    for line in lines:
        cells = cells_of(line)
        text = line.strip()

        if text.startswith("**Remarks"):
            in_remarks = True
            continue
        if in_remarks:
            remarks.append(re.sub(r"^[-|\s]+", "", text).replace(" | ", " "))
            continue
        if FOOTER.match(text) or PAGE_TITLE.match(text):
            continue

        heading_row = len(cells) == 1 or (
            len(cells) == 2 and cells[1] in {"Minimum", "credit(s)", "required"})
        if heading_row:
            head = cells[0]
            if head in SECTIONS:
                close()
                flush_prose()
                started = True
                builders[current.name].heading(None, SECTIONS[head])
                continue
            if not started:
                continue
            if head in SOFT_HEADINGS and pending is not None and (
                    pending.kind == "elective"):
                pending.line += f"\n  [{head}]"
                continue
            if head in GROUP_HEADINGS or head in SOFT_HEADINGS:
                close()
                flush_prose()
                prefix = f"{current.name} - " if current.name else ""
                builders[current.name].heading(f"{prefix}{head}")
                continue
            variant = VARIANT_HEADING.match(head)
            if variant and head not in {"Track Study", "Option(s)"}:
                close()
                flush_prose()
                builders[current.name].flush()
                current = Variant(head, variant.group(2).lower())
                variants.append(current)
                builders[head] = Builder()
                builders[head].category = builders[""].category
                continue
            if "follow one of the" in head:
                mandatory = True
                continue
            if head in {"Track Study", "Option(s)"}:
                close()
                continue
            found = CODE.findall(head)
            if re.search(r"should also take|are required to take", head) and found:
                close()
                builders[current.name].add(Required(courses=found), head)
                continue
            if pending is not None and pending.kind == "elective":
                pending.line += f"\n  [{head}]"     # an area inside the list
            elif len(head) > 40:
                prose.append(head)                   # joined up after the loop
            continue

        flush_prose()
        code = course_row(cells)
        note = NOTE.match(cells[1]) if len(cells) > 1 else None

        if note:
            close()
            pending = Pending(line=line, kind="note", text=note.group(1),
                              credits=credits_of(cells))
            continue

        if code:
            if pending and pending.kind == "note" and code in pending.text:
                continue                      # an option the Note already named
            if pending and pending.kind == "elective":
                pending.courses.append(code)
                continue
            close()
            if started:
                builders[current.name].add(Required(courses=[code]), line)
            continue

        if started and len(cells) >= 2:
            body = " ".join(cells[1:-1]) if credits_of(cells) else " ".join(cells[1:])
            if pending and pending.kind == "elective" and not credits_of(cells):
                subject = ANY_SUBJECT.match(body)
                if subject:
                    found = level_patterns(subject.group(1).upper(), body)
                    pending.patterns += found or [
                        f"{subject.group(1).upper()} {n}xxx"
                        for n in range(1, MAX_LEVEL + 1)]
                    pending.line += f"\n  {line.strip()}"
                    continue
                if re.search(r"\d000", body):
                    pending.patterns += level_patterns(cells[0], body)
                    pending.line += f"\n  {line.strip()}"
                    continue
            close()
            pending = Pending(line=line, kind="elective", text=body or cells[1],
                              credits=credits_of(cells))
            continue

    close()
    flush_prose()
    for variant in variants:
        builders[variant.name].flush()
        variant.groups = builders[variant.name].groups
    return variants, mandatory, remarks


# ------------------------------------------------- courses that do not exist --
# A PDF may still offer a course the 2026-27 catalog no longer has: one its own
# remarks call deleted, or one that was simply dropped. Hard rule 1 forbids
# naming it in an output, so it is removed from the rule and the omission is
# recorded as a caveat. An alternative disappearing from a one_of is harmless;
# a required course disappearing is not, and leaves the group unparsed.


def load_catalog() -> set[str]:
    path = DATA / "catalog.json"
    if not path.exists():
        raise SystemExit("data/catalog.json is missing — run pipeline/parse_catalog.py")
    return set(json.loads(path.read_text(encoding="utf-8")))


def prune(rule, catalog: set[str]) -> tuple[object | None, list[str]]:
    """The rule with unknown courses removed, and the codes that were removed."""
    if isinstance(rule, Required):
        gone = [c for c in rule.courses if c not in catalog]
        kept = [c for c in rule.courses if c in catalog]
        return (Required(courses=kept) if kept else None), gone

    if isinstance(rule, OneOf):
        gone = sorted({c for o in rule.options for c in o if c not in catalog})
        kept = [o for o in rule.options if all(c in catalog for c in o)]
        if not kept:
            return None, gone
        return (Required(courses=kept[0]) if len(kept) == 1
                else OneOf(options=kept)), gone

    if isinstance(rule, ChooseN):
        gone = [c for c in rule.courses if c not in catalog]
        kept = [c for c in rule.courses if c in catalog]
        if len(kept) < rule.n:
            return None, gone
        return ChooseN(n=rule.n, courses=kept), gone

    if isinstance(rule, CreditsFrom):
        gone = [p for p in rule.patterns if CODE.fullmatch(p) and p not in catalog]
        kept = [p for p in rule.patterns if p not in gone]
        if not kept:
            return None, gone
        return CreditsFrom(patterns=kept, min_credits=rule.min_credits,
                           exclude=rule.exclude), gone

    if isinstance(rule, EveryTerm) and rule.course not in catalog:
        return None, [rule.course]
    return rule, []


def prune_groups(groups: list[RequirementGroup],
                 catalog: set[str]) -> tuple[list[RequirementGroup], list[str], list[str]]:
    """Groups with unknown courses removed, plus caveats and unparsed lines."""
    out, caveats, unparsed = [], [], []
    for group in groups:
        rules, dropped = [], []
        for rule in group.rules:
            kept, gone = prune(rule, catalog)
            dropped += gone
            if kept is not None:
                rules.append(kept)
            elif gone:
                unparsed.append(
                    f"{group.name}: this requirement names only course(s) that "
                    f"are not in the {COHORT} catalog ({', '.join(gone)}), so it "
                    f"could not be checked.")
        if dropped:
            caveats.append(
                f"{group.name}: {', '.join(sorted(set(dropped)))} "
                f"{'is' if len(set(dropped)) == 1 else 'are'} named in the "
                f"requirement PDF but not in the {COHORT} course catalog, so "
                f"{'it was' if len(set(dropped)) == 1 else 'they were'} left "
                f"out of this check.")
        if rules:
            out.append(RequirementGroup(name=group.name, category=group.category,
                                        rules=rules, source_quote=group.source_quote))
    return out, caveats, unparsed

# ----------------------------------------------------------- the programs --

SMALL_WORDS = {"and", "of", "the", "in", "for", "with", "to", "a", "an", "&"}
OUT_OF_SCOPE = {
    "T&M-DDP": "Dual degree programs are out of scope for this cohort "
               "(CLAUDE.md section 7).",
}


def suffix(name: str) -> str:
    """A short, stable code for a track or option name."""
    words = [w for w in re.findall(r"[A-Za-z]+", name)
             if w.lower() not in SMALL_WORDS and w not in {"Track", "Option"}]
    if not words:
        return "VAR"
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0] for w in words).upper()


# Two numbers the minor PDFs state only in prose, both of which Phase 3 needs:
# the credits the minor is worth, and how many of them must be *single*-counted
# (so the rest may double-count against the major). Part B asks for
# stated_total_credits and max_double_count_credits "if stated"; this is where
# they are stated.
STATED_TOTAL = re.compile(r"minimum total of (\d+) credits", re.I)
SINGLE_COUNTED = re.compile(r"at least (\d+) credits.{0,140}?single-counted",
                            re.I | re.S)


def stated_numbers(lines: list[str]) -> tuple[float | None, float | None]:
    """(total credits, credits that may be double-counted), from the prose."""
    text = " ".join(lines)
    total = STATED_TOTAL.search(text)
    single = SINGLE_COUNTED.search(text)
    if not total:
        return None, None
    stated = float(total.group(1))
    if not single:
        return stated, None
    return stated, max(0.0, stated - float(single.group(1)))


def read_pdf(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [line for page in pdf.pages for line in render(page, 3.5, 12.0)]


def school_groups(cache: dict, school: str) -> list[RequirementGroup]:
    """The School Requirements that every program of this school also carries."""
    if school not in cache:
        path = REQUIREMENTS / f"SREQ-{school}.pdf"
        if not path.exists():
            cache[school] = []
        else:
            variants, _, _ = parse(read_pdf(path))
            cache[school] = variants[0].groups
    return cache[school]


def build(entry: dict, cache: dict, catalog: set[str]) -> list[Program]:
    """Every Program file one catalog entry produces: the base and its variants."""
    code, title = entry["code"], entry["title"]
    source = entry.get("pdf_url") or entry["page_url"]
    path = REQUIREMENTS / f"{code}.pdf"

    common = dict(cohort=COHORT, source_url=source,
                  stated_total_credits=entry.get("stated_total_credits"))
    kind = "minor" if entry["kind"] == "minor" else "major"

    if code in OUT_OF_SCOPE or not path.exists():
        reason = OUT_OF_SCOPE.get(
            code, f"No requirement PDF was published for {code} in {COHORT} "
                  f"(see raw/requirements/MISSING.md).")
        return [Program(code=code, title=title, kind=kind, groups=[],
                        tier=Tier.UNSUPPORTED, unparsed_lines=[reason], **common)]

    lines = read_pdf(path)
    variants, mandatory, remarks = parse(lines)
    if kind == "minor":
        total, double = stated_numbers(lines)
        if total is not None:
            common["stated_total_credits"] = total
        if double is not None:
            common["max_double_count_credits"] = double
    base, extras = variants[0], variants[1:]
    shared = school_groups(cache, entry["school"]) if kind == "major" else []
    withdrawn = [r for r in remarks if re.search(r"deleted|subject to approval", r)]

    programs: list[Program] = []
    base_unsupported = mandatory and any(v.kind == "track" for v in extras)
    programs.append(Program(
        code=code, title=title, kind=kind,
        groups=shared + base.groups,
        caveats=base.caveats + withdrawn,
        unparsed_lines=base.unparsed + ([
            "This program requires choosing one of its tracks; the base "
            "requirements alone do not make a complete program. Plan one of "
            f"{', '.join(v.name for v in extras if v.kind == 'track')} instead."
        ] if base_unsupported else []),
        tier=Tier.UNSUPPORTED if base_unsupported else Tier.AUTO, **common))

    used = {code}
    for variant in extras:
        child = f"{code}-{suffix(variant.name)}"
        while child in used:
            child += "X"
        used.add(child)
        programs.append(Program(
            code=child, title=f"{title} - {variant.name}", kind=kind,
            parent=code, groups=shared + base.groups + variant.groups,
            caveats=base.caveats + variant.caveats + withdrawn,
            unparsed_lines=base.unparsed + variant.unparsed, **common))

    for program in programs:
        groups, caveats, unparsed = prune_groups(program.groups, catalog)
        program.groups = groups
        program.caveats += caveats
        program.unparsed_lines += unparsed
    return programs


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("codes", nargs="*", help="program codes; default is all")
    ap.add_argument("--dump", action="store_true",
                    help="print each program's groups instead of writing files")
    args = ap.parse_args()

    entries = json.loads(INDEX.read_text(encoding="utf-8"))["programs"]
    entries = [e for e in entries if e["kind"] != "school_requirement"]
    if args.codes:
        entries = [e for e in entries if e["code"] in set(args.codes)]

    PROGRAMS.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    catalog = load_catalog()
    written, totals = [], collections.Counter()

    for entry in sorted(entries, key=lambda e: e["code"]):
        for program in build(entry, cache, catalog):
            rules = sum(len(g.rules) for g in program.groups)
            totals["programs"] += 1
            totals["rules"] += rules
            totals["unparsed"] += len(program.unparsed_lines)
            totals["caveats"] += len(program.caveats)
            if program.tier is Tier.UNSUPPORTED:
                totals["unsupported"] += 1
            written.append((program, rules))
            if args.dump:
                print(f"\n=== {program.code}  {program.title}")
                for group in program.groups:
                    print(f"  [{group.category.value}] {group.name}")
                    for rule in group.rules:
                        print(f"      {rule.model_dump_json()[:150]}")
                for c in program.caveats:
                    print(f"  caveat:   {c[:120]}")
                for u in program.unparsed_lines:
                    print(f"  UNPARSED: {u[:120]}")
            else:
                (PROGRAMS / f"{program.code}.json").write_text(
                    program.model_dump_json(indent=1) + "\n", encoding="utf-8")

    if args.dump:
        return
    print(f"wrote {totals['programs']} program files to data/programs/ "
          f"({totals['rules']} rules, {totals['caveats']} caveats, "
          f"{totals['unparsed']} unparsed lines, "
          f"{totals['unsupported']} marked unsupported)")
    print()
    print(f"{'program':16} {'rules':>5} {'cav':>4} {'unp':>4}  title")
    for program, rules in written:
        flag = "!" if program.tier is Tier.UNSUPPORTED else " "
        print(f"{flag}{program.code:15} {rules:5} {len(program.caveats):4} "
              f"{len(program.unparsed_lines):4}  {program.title[:52]}")


if __name__ == "__main__":
    main()
