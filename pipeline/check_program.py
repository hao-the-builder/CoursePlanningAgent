"""Auto-check every program JSON and assign its tier (Phase 2, Part D).

Four checks, in the order Part D lists them:

  1. the file loads as a valid Program;
  2. every course code any rule names exists in data/catalog.json;
  3. the credits the rules add up to are consistent with the credits the
     program says it needs;
  4. unparsed_lines is empty.

Pass -> `auto_extracted`. Fail -> `unsupported`, and the reasons are written to
data/programs/{CODE}.issues.md so the developer can see what to fix. A tier of
`verified` is only ever set by hand, after Part F, and is never downgraded here.

**The tolerance on check 3.** A program's rules state a *floor*: the fewest
credits that can satisfy them. A one_of is costed at its cheapest option, a
choose_n at its n cheapest courses, a credits_from at its min_credits. That
floor plus the 30-credit Common Core must fit inside the degree total (120), or
the extraction has counted something twice. The other direction is a warning,
not a failure: a major whose floor leaves more than `--slack` credits of free
electives is suspicious but legal, since some programs really are that open.

Usage:
    python pipeline/check_program.py --all
    python pipeline/check_program.py COMP MATH-STA
    python pipeline/check_program.py --all --write     # update the tiers
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.fetcher import REPO, _utf8_stdout  # noqa: E402
from schema import (  # noqa: E402
    ChooseN,
    CommonCoreArea,
    Course,
    CreditsFrom,
    EveryTerm,
    NAreas,
    OneOf,
    Program,
    Required,
    Tier,
    _matches,
)

DATA = REPO / "data"
PROGRAMS = DATA / "programs"
COMMON_CORE_CREDITS = 30     # data/common_core.json, cohort 2026-27
DEFAULT_SLACK = 60           # free-elective credits before check 3 complains
# How far over the degree total the floor may sit before it counts as evidence
# of double counting. The floor is approximate in three directions: a
# variable-credit course is costed at its minimum, a one_of at its cheapest
# option, and an Option variant is extra study layered on a complete degree.
# Twelve credits is four courses' worth of that slop.
DEFAULT_TOLERANCE = 12


def cited_courses(program: Program) -> set[str]:
    """Every concrete course code the rules name (patterns are not codes)."""
    out: set[str] = set()
    for group in program.groups:
        for rule in group.rules:
            if isinstance(rule, Required):
                out |= set(rule.courses)
            elif isinstance(rule, OneOf):
                out |= {c for option in rule.options for c in option}
            elif isinstance(rule, ChooseN):
                out |= set(rule.courses)
            elif isinstance(rule, CreditsFrom):
                out |= {p for p in rule.patterns if "x" not in p and p != "*"}
            elif isinstance(rule, EveryTerm):
                out.add(rule.course)
    return out


def credit_floor(program: Program, catalog: dict[str, Course]) -> float:
    """The fewest credits that can satisfy every rule, counting each course once.

    Two kinds of overlap make a naive sum far too large. A School Requirement
    and its Major often name the same foundation course, and an elective list
    produces both a choose_n ("5 courses") and a credits_from ("15 credits")
    over the same courses. So the named courses are gathered into one set
    first, and a credit target only adds whatever that set does not already
    cover.
    """
    def cost(code: str) -> float:
        return catalog[code].credits if code in catalog else 0.0

    named: set[str] = set()
    choices: list = []
    targets: list[tuple[float, list[str]]] = []

    for group in program.groups:
        for rule in group.rules:
            if isinstance(rule, Required):
                named |= set(rule.courses)
            elif isinstance(rule, EveryTerm):
                named.add(rule.course)
            elif isinstance(rule, (OneOf, ChooseN)):
                choices.append(rule)
            elif isinstance(rule, CreditsFrom):
                targets.append((rule.min_credits, rule.patterns))
            elif isinstance(rule, (CommonCoreArea, NAreas)):
                targets.append((rule.min_credits, []))

    # Resolve the choices only once the fixed courses are known, so that a
    # School rule and a Major rule offering the same alternatives (ECON 2103 OR
    # ECON 2113, twice) settle on one course rather than one each.
    def new_cost(code: str) -> float:
        return 0.0 if code in named else cost(code)

    for rule in choices:
        if isinstance(rule, OneOf):
            named |= set(min(rule.options,
                             key=lambda o: sum(new_cost(c) for c in o)))
        else:
            named |= set(sorted(rule.courses, key=new_cost)[:rule.n])

    total = sum(cost(c) for c in named)
    for min_credits, patterns in targets:
        covered = sum(cost(c) for c in named
                      if any(_matches(c, p) for p in patterns))
        total += max(0.0, min_credits - covered)
    return total


def check(path: Path, catalog: dict[str, Course], slack: float,
          tolerance: float) -> tuple[Program | None, list[str], list[str]]:
    """One program: (the program, blocking failures, non-blocking notes)."""
    try:
        program = Program.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        return None, [f"the file is not a valid Program: {exc}"], []

    failures: list[str] = []
    notes: list[str] = []

    missing = sorted(cited_courses(program) - set(catalog))
    if missing:
        failures.append(
            f"{len(missing)} course(s) named in a rule are not in "
            f"data/catalog.json: {', '.join(missing)}")

    if program.unparsed_lines:
        failures.append(
            f"{len(program.unparsed_lines)} line(s) of the requirement PDF "
            f"could not be mapped to a rule:\n  - "
            + "\n  - ".join(line.replace("\n", " ") for line in
                            program.unparsed_lines))

    floor = credit_floor(program, catalog)
    stated = program.stated_total_credits
    if stated and program.kind == "minor":
        # A minor states what the minor itself is worth, not a degree total,
        # so the Common Core does not enter and the rules should land on it.
        if abs(floor - stated) > tolerance:
            failures.append(
                f"the rules need {floor:g} credits but the minor states "
                f"{stated:g}, a gap of {abs(floor - stated):g} beyond the "
                f"{tolerance:g}-credit tolerance.")
        elif floor != stated:
            notes.append(f"the rules need {floor:g} credits against the "
                         f"{stated:g} the minor states, within tolerance.")
    elif stated:
        with_core = floor + COMMON_CORE_CREDITS
        if with_core > stated + tolerance:
            failures.append(
                f"the rules need at least {floor:g} credits, which with the "
                f"{COMMON_CORE_CREDITS}-credit Common Core is {with_core:g} — "
                f"more than the {stated:g} the program states, by more than "
                f"the {tolerance:g}-credit tolerance. Something is counted twice.")
        elif with_core > stated:
            notes.append(
                f"the rules need {floor:g} credits, which with the Common Core "
                f"is {with_core:g} — {with_core - stated:g} over the stated "
                f"{stated:g}, within tolerance. Expected for an Option, worth "
                f"a look otherwise.")
        elif stated - with_core > slack:
            notes.append(
                f"the rules need only {floor:g} credits, leaving "
                f"{stated - with_core:g} credits of free electives after the "
                f"Common Core. Legal, but worth checking the extraction.")
    elif program.groups:
        notes.append(f"no stated total to check {floor:g} credits of rules against")

    if not program.groups and not failures:
        failures.append("the program has no requirement groups")

    return program, failures, notes


def write_issues(program: Program, failures: list[str], notes: list[str]) -> None:
    path = PROGRAMS / f"{program.code}.issues.md"
    if not failures and not notes:
        path.unlink(missing_ok=True)
        return
    lines = [f"# {program.code} — {program.title}", "",
             "Written by `pipeline/check_program.py`. Do not edit by hand; fix the",
             "extraction in `pipeline/extract_programs.py` and re-run it.", "",
             f"Source: <{program.source_url}>", ""]
    if failures:
        lines += [f"## Why this program is `unsupported` ({len(failures)})", ""]
        lines += [f"{i}. {f}" for i, f in enumerate(failures, 1)] + [""]
    if notes:
        lines += ["## Worth a look, but not disqualifying", ""]
        lines += [f"- {n}" for n in notes] + [""]
    if program.caveats:
        lines += [f"## Stated conditions this data does not enforce "
                  f"({len(program.caveats)})", ""]
        lines += [f"- {c}" for c in program.caveats] + [""]
    path.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------- the human verification list --

VERIFY_DEFAULT = ["COMP", "MATH-AM", "FINA", "GCS-SS", "IDT"]


def describe(rule, catalog: dict[str, Course]) -> str:
    """One rule, in the plainest English that does not lose anything."""
    def title(code: str) -> str:
        course = catalog.get(code)
        return f"{code} ({course.title}, {course.credits:g} cr)" if course else code

    if isinstance(rule, Required):
        return "must take " + "; ".join(title(c) for c in rule.courses)
    if isinstance(rule, OneOf):
        return "must take one of: " + "  **OR**  ".join(
            " + ".join(title(c) for c in option) for option in rule.options)
    if isinstance(rule, ChooseN):
        return (f"must take {rule.n} of these {len(rule.courses)}: "
                + ", ".join(rule.courses))
    if isinstance(rule, CreditsFrom):
        return (f"at least {rule.min_credits:g} credits from "
                + ", ".join(rule.patterns)
                + (f" (excluding {', '.join(rule.exclude)})" if rule.exclude else ""))
    if isinstance(rule, CommonCoreArea):
        return f"at least {rule.min_credits:g} credits in Common Core area {rule.area}"
    if isinstance(rule, NAreas):
        return (f"at least {rule.min_credits:g} credits over {rule.n_areas} "
                f"different areas of " + ", ".join(rule.areas))
    if isinstance(rule, EveryTerm):
        return f"must take {title(rule.course)} in every term in residence"
    return repr(rule)


def write_verify(codes: list[str], catalog: dict[str, Course]) -> Path:
    """data/VERIFY.md — each rule beside the PDF sentence it came from."""
    out = [
        "# Verify these five against the official PDFs",
        "",
        "Phase 2, Part F. One program per school, the largest in each, chosen in",
        "`DECISIONS.md`. Every rule is printed next to the exact line of the",
        "requirement PDF it was read from, so a check needs the PDF and this file",
        "and nothing else.",
        "",
        "**What to do.** Open each program's `Source` link, read down the table, and",
        'say which programs are right. Claude Code then sets `"tier": "verified"`',
        "in those `data/programs/{CODE}.json` files — nothing else sets that tier,",
        "together with the date of the check in `verified_on`. A program whose",
        "`Tier` line below already reads `verified` has been through this once;",
        "its date is in its JSON, and re-reading it re-checks that same claim.",
        "",
        "One exception to the `Source` link: the School Requirements are published",
        "in a separate PDF, so that group names its own URL and is not in the",
        "program's PDF at all.",
        "",
        "Two of the five are track variants rather than the base program, because",
        "`BSc in Mathematics` and `BSc in Global China Studies` both require the",
        "student to choose a track, so the base on its own is not a plannable",
        "program (`tier: unsupported`). `MATH-AM` and `GCS-SS` stand in for them.",
        "",
        "A `caveat` is a condition the PDF states that no rule type can enforce; it",
        "is shown to the student rather than checked. Worth reading, but it is not",
        "a mistake in the extraction.",
        "",
        "---",
        "",
    ]

    for code in codes:
        path = PROGRAMS / f"{code}.json"
        if not path.exists():
            out += [f"## {code} — **missing**", ""]
            continue
        program = Program.model_validate_json(path.read_text(encoding="utf-8"))
        floor = credit_floor(program, catalog)
        out += [
            f"## {program.code} — {program.title}",
            "",
            f"Source: <{program.source_url}>  ",
            f"Tier: `{program.tier.value}` · {len(program.groups)} groups · "
            f"{sum(len(g.rules) for g in program.groups)} rules · "
            f"at least {floor:g} credits · states {program.stated_total_credits:g} "
            f"for the degree",
            "",
        ]
        for group in program.groups:
            out += [f"### {group.name}  _({group.category.value})_", ""]
            if group.source_url and group.source_url != program.source_url:
                # The School Requirements are published in their own PDF, and
                # looking for them in the program's PDF finds nothing.
                out += [f"Read this group against <{group.source_url}>, not "
                        f"the program's own PDF.", ""]
            out += ["| # | What the data says | The line it came from |",
                    "|---|---|---|"]
            # One rule's quote can itself span lines, so rules are separated
            # by a blank line (see Builder.flush in extract_programs.py).
            quotes = group.source_quote.split("\n\n")
            for i, rule in enumerate(group.rules, 1):
                quote = quotes[i - 1] if i - 1 < len(quotes) else ""
                out.append(f"| {i} | {describe(rule, catalog)} | "
                           f"`{quote.strip()[:300]}` |")
            out.append("")
        if program.caveats:
            out += [f"### Caveats ({len(program.caveats)}) — shown, not checked", ""]
            out += [f"- {c}" for c in program.caveats] + [""]
        if program.unparsed_lines:
            out += [f"### Not mapped ({len(program.unparsed_lines)})", ""]
            out += [f"- `{u.replace(chr(10), ' ')}`" for u in program.unparsed_lines]
            out += [""]
        out += ["---", ""]

    target = DATA / "VERIFY.md"
    target.write_text("\n".join(out), encoding="utf-8")
    return target


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--write", action="store_true", help="save the tiers back")
    ap.add_argument("--slack", type=float, default=DEFAULT_SLACK)
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    ap.add_argument("--verify", nargs="*", metavar="CODE",
                    help="also write data/VERIFY.md for these programs "
                         "(default: one per school, see DECISIONS.md)")
    args = ap.parse_args()

    catalog = {code: Course.model_validate(c) for code, c in
               json.loads((DATA / "catalog.json").read_text(encoding="utf-8")).items()}

    paths = sorted(PROGRAMS.glob("*.json"))
    if args.codes:
        wanted = set(args.codes)
        paths = [p for p in paths if p.stem in wanted]
    elif not args.all:
        ap.error("give one or more program codes, or --all")

    rows, tally = [], {Tier.VERIFIED: 0, Tier.AUTO: 0, Tier.UNSUPPORTED: 0}
    for path in paths:
        program, failures, notes = check(path, catalog, args.slack,
                                         args.tolerance)
        if program is None:
            print(f"!! {path.name}: {failures[0]}")
            continue
        if program.tier is not Tier.VERIFIED:
            program.tier = Tier.UNSUPPORTED if failures else Tier.AUTO
        tally[program.tier] += 1
        write_issues(program, failures, notes)
        if args.write:
            path.write_text(program.model_dump_json(indent=1) + "\n",
                            encoding="utf-8")
        rows.append((program, len(failures), len(notes),
                     credit_floor(program, catalog)))

    print(f"{'program':16} {'tier':15} {'floor':>6} {'fail':>4} {'note':>4} "
          f"{'cav':>4}  title")
    for program, failures, notes, floor in rows:
        mark = "!" if program.tier is Tier.UNSUPPORTED else " "
        print(f"{mark}{program.code:15} {program.tier.value:15} {floor:6g} "
              f"{failures:4} {notes:4} {len(program.caveats):4}  "
              f"{program.title[:44]}")
    print()
    if args.verify is not None:
        target = write_verify(args.verify or VERIFY_DEFAULT, catalog)
        print(f"wrote {target.relative_to(REPO).as_posix()} for "
              f"{', '.join(args.verify or VERIFY_DEFAULT)}")
        print()

    print(f"{len(rows)} programs: "
          f"{tally[Tier.VERIFIED]} verified, {tally[Tier.AUTO]} auto_extracted, "
          f"{tally[Tier.UNSUPPORTED]} unsupported"
          f"{'' if args.write else '  (--write to save these tiers)'}")


if __name__ == "__main__":
    main()
