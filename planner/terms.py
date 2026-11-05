"""Term sequence generation (Phase 3).

`term_sequence(cohort, years, use_summer, use_winter)` returns the terms of a
programme in order, each with the label a plan uses (`Y2 Fall`) and the
calendar name a spreadsheet shows (`Fall 2027`).

The calendar years come from the Academic Regulations' glossary: an academic
year runs 1 September to 31 August, and holds four terms — Fall (early
September to late December), Winter, Spring (early February to late May) and
Summer (late June to mid-August). So for the 2026-27 cohort, Y1 Fall is Fall
2026 while Y1 Winter, Spring and Summer all fall in 2027.

Ordering. `sort_key` puts a term where the plan expects it:

    Transfer < Y1 Fall < Y1 Winter < Y1 Spring < Y1 Summer < Y2 Fall < ...

Transfer sorts before everything because transferred credits were earned
before the programme started.

`years` is a parameter rather than a constant, but only 4-year programmes are
supported — see DECISIONS.md. A 5-year sequence is generated correctly; no
validator, profile or output label is built for one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Season = Literal["Fall", "Winter", "Spring", "Summer"]

# Within an academic year, in the order a student meets them.
SEASONS: tuple[Season, ...] = ("Fall", "Winter", "Spring", "Summer")
REGULAR: frozenset[Season] = frozenset({"Fall", "Spring"})   # AR 9.1
TRANSFER = "Transfer"

LABEL = re.compile(r"^Y(\d+)\s+(Fall|Winter|Spring|Summer)$", re.I)
COHORT = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass(frozen=True, slots=True)
class Term:
    """One term of a programme."""

    label: str                 # "Y2 Fall", or "Transfer"
    calendar: str              # "Fall 2027", or "Before HKUST"
    year: int                  # 1-based; 0 for Transfer
    season: Season | None      # None for Transfer
    calendar_year: int | None  # None for Transfer

    @property
    def is_regular(self) -> bool:
        """A Regular Term, the only kind the 12-18 credit limits apply to."""
        return self.season in REGULAR

    @property
    def is_transfer(self) -> bool:
        return self.season is None

    def __str__(self) -> str:
        return self.label


def start_year(cohort: str) -> int:
    """"2026-27" -> 2026. The first calendar year of the academic year."""
    match = COHORT.match(cohort.strip())
    if not match:
        raise ValueError(f"cohort should look like '2026-27', got {cohort!r}")
    return int(match.group(1))


def calendar_year(cohort_start: int, year: int, season: Season) -> int:
    """Fall sits in the first calendar year of its academic year; the rest
    sit in the second, because an academic year starts on 1 September."""
    return cohort_start + year - 1 + (0 if season == "Fall" else 1)


def term_sequence(cohort: str, years: int = 4, use_summer: bool = False,
                  use_winter: bool = False,
                  include_transfer: bool = False) -> list[Term]:
    """Every term of the programme, in order.

    Fall and Spring are always present. Winter and Summer appear only when the
    student is willing to study in them, because an unused term should not
    show up as an empty block in the plan.
    """
    if years < 1:
        raise ValueError(f"a programme needs at least one year, got {years}")

    wanted = [s for s in SEASONS
              if s in REGULAR or (s == "Winter" and use_winter)
              or (s == "Summer" and use_summer)]

    start = start_year(cohort)
    terms: list[Term] = []
    if include_transfer:
        terms.append(Term(label=TRANSFER, calendar="Before HKUST", year=0,
                          season=None, calendar_year=None))
    for year in range(1, years + 1):
        for season in wanted:
            cal = calendar_year(start, year, season)
            terms.append(Term(label=f"Y{year} {season}",
                              calendar=f"{season} {cal}",
                              year=year, season=season, calendar_year=cal))
    return terms


def parse_label(label: str) -> tuple[int, Season | None]:
    """"Y2 Fall" -> (2, "Fall"); "Transfer" -> (0, None)."""
    text = label.strip()
    if text.casefold() == TRANSFER.casefold():
        return 0, None
    match = LABEL.match(text)
    if not match:
        raise ValueError(
            f"{label!r} is not a term label; expected 'Transfer' or "
            f"'Y<n> Fall|Winter|Spring|Summer'")
    season = match.group(2).capitalize()
    return int(match.group(1)), season       # type: ignore[return-value]


def sort_key(label: str) -> tuple[int, int]:
    """Order terms by label, with Transfer first. Unknown labels sort last.

    Used wherever a plan's own term strings have to be put in order, which is
    most places — a plan is a flat list of PlannedCourse and carries no
    sequence of its own.
    """
    try:
        year, season = parse_label(label)
    except ValueError:
        return (10**6, 0)
    return (year, SEASONS.index(season) if season else -1)


def is_regular(label: str) -> bool:
    """Does the AR 5.4 credit load limit apply to this term?"""
    try:
        _, season = parse_label(label)
    except ValueError:
        return False
    return season in REGULAR


def in_residence(labels: list[str]) -> list[str]:
    """The Regular Terms a student is actually at HKUST for.

    What an `every_term` rule counts against — COMP 4900 is required "for
    every regular term in which they are in residency", so Transfer, Winter
    and Summer do not count.
    """
    return sorted({t for t in labels if is_regular(t)}, key=sort_key)


def final_term(terms: list[Term]) -> Term:
    """The last term of the programme, the one a free term may displace."""
    return max((t for t in terms if not t.is_transfer),
               key=lambda t: sort_key(t.label))


def label_range(cohort: str, years: int = 4) -> list[str]:
    """Every label a 4-year plan could legally use, summer and winter included."""
    return [t.label for t in term_sequence(cohort, years, use_summer=True,
                                           use_winter=True,
                                           include_transfer=True)]
