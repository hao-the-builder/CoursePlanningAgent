"""StudentProfile and follow-up question logic (Phase 4).

StudentProfile is a pydantic model covering every field in CLAUDE.md section
1.1, including programme_years, transfer_credits (list[PlannedCourse]),
exchange (ExchangePlan or None: terms, host, purposes), workload_min and
workload_max, spread (even | front | back), free_terms, use_summer, use_winter
and gpa_target.

missing_required(profile) returns the empty required fields -- cohort and major
at minimum. A missing required field becomes a follow-up question; it is never
guessed.
"""


def missing_required(profile) -> list[str]:
    raise NotImplementedError("Phase 4")
