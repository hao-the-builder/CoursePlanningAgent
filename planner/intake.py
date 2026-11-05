"""StudentProfile and follow-up question logic (Phase 3 model, Phase 4 logic).

The model covers every field in CLAUDE.md section 1.1. It lands in Phase 3
rather than Phase 4 because `validate_plan(plan, profile)` cannot be written
without it; Phase 4 adds the agent's follow-up questions on top.

`missing_required(profile)` returns the required fields that are empty.
Cohort and major are required because requirements differ by intake year and
by program, and hard rule 4 says to ask rather than guess.

Two notes on how section 1.1 maps onto the model:

  * Transfer credits come in two kinds. A *mapped* transfer is a PlannedCourse
    with status "transfer" naming the HKUST course it counts as, so its
    credits come from the catalog. An *unspecified* transfer — the Academic
    Regulations call it "credit-only transfer" — has credits but no course, so
    it is a bare number in `unspecified_transfer_credits` and may only ever
    count as free electives (hard rule 6).

  * "Graduate early if possible" is `graduate_early`, separate from
    `free_terms`, because wanting the last term free and wanting to finish
    sooner lead to different plans.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner.terms import parse_label  # noqa: E402
from schema import PlannedCourse  # noqa: E402

Spread = Literal["even", "front", "back"]
ExchangePurpose = Literal["major", "common_core", "minor", "free"]

REQUIRED_FIELDS = {
    "cohort": "which intake year you started in — requirements differ by cohort",
    "major": "your major, so the right requirements can be loaded",
}


class ExchangePlan(BaseModel):
    """An exchange the student wants planned, approved or not."""

    terms: list[str] = []            # term labels, e.g. ["Y3 Fall"]
    host_university: str | None = None
    purposes: list[ExchangePurpose] = []
    note: str = ""

    @field_validator("terms")
    @classmethod
    def _real_terms(cls, terms: list[str]) -> list[str]:
        for term in terms:
            parse_label(term)        # raises if it is not a term label
        return terms


class StudentProfile(BaseModel):
    """Everything the form and the chat collect, in one place."""

    # --- who they are ----------------------------------------------------
    cohort: str | None = None                  # required; "2026-27"
    school: str | None = None
    department: str | None = None
    major: str | None = None                   # required; a program_index code
    minor: str | None = None
    additional_major: str | None = None
    programme_years: int = 4

    # --- what they have already done -------------------------------------
    taken: list[PlannedCourse] = []            # status "taken", with a term
    current: list[PlannedCourse] = []          # status "current"
    transfer_credits: list[PlannedCourse] = []  # status "transfer", mapped
    unspecified_transfer_credits: float = 0.0   # credit-only transfer, AR 6.1

    # --- how they want to study -------------------------------------------
    workload_min: float = 12.0
    workload_max: float = 18.0
    spread: Spread = "even"
    free_terms: list[str] = []
    graduate_early: bool = False
    use_summer: bool = False
    use_winter: bool = False
    reserve_summer_for_internship: bool = False
    exchange: ExchangePlan | None = None
    gpa_target: float | None = None

    # --- what the chat adds ------------------------------------------------
    direction: str = ""           # e.g. "AI", "systems", "finance"
    career_interests: str = ""
    background: str = ""          # IB / HKDSE / A-level, maths, programming
    notes: list[str] = Field(default_factory=list)

    @field_validator("free_terms")
    @classmethod
    def _real_terms(cls, terms: list[str]) -> list[str]:
        for term in terms:
            parse_label(term)
        return terms

    @property
    def exchange_terms(self) -> list[str]:
        return list(self.exchange.terms) if self.exchange else []

    @property
    def total_transfer_credits(self) -> float:
        """Mapped credits are counted by the caller, which has the catalog."""
        return self.unspecified_transfer_credits

    def already_taken(self) -> list[PlannedCourse]:
        """Everything that is done or in progress, in one list."""
        return [*self.taken, *self.current, *self.transfer_credits]


def missing_required(profile: StudentProfile) -> list[str]:
    """Required fields that are still empty. Hard rule 4: ask, do not guess."""
    return [name for name in REQUIRED_FIELDS if not getattr(profile, name, None)]


def follow_up_questions(profile: StudentProfile) -> list[str]:
    """A plain question for each missing required field."""
    return [f"What is {REQUIRED_FIELDS[name]}?" for name in
            missing_required(profile)]
