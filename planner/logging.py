"""JSONL action log (Phase 4).

Every step of a run goes to logs/runs/{timestamp}.jsonl: inputs, tool calls,
validation results, iteration count, final status. This is the evidence the
test log in Phase 7 is written from.

Imported as planner.logging; it does not shadow the standard library logging
module for absolute imports.
"""


def log_event(run_id: str, event: str, payload: dict) -> None:
    raise NotImplementedError("Phase 4")
