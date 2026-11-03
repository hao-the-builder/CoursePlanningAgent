"""Deterministic tools exposed to the agent (Phase 3).

get_program(code), list_programs(kind=None),
search_courses(query, subject=None, level=None) -- keyword search over the
catalog, and parse_prereq(expr) -> boolean tree.

An unparseable prerequisite expression is flagged, never a hard failure.
"""


def get_program(code: str):
    raise NotImplementedError("Phase 3")


def list_programs(kind: str | None = None):
    raise NotImplementedError("Phase 3")


def search_courses(query: str, subject: str | None = None, level: int | None = None):
    raise NotImplementedError("Phase 3")


def parse_prereq(expr: str):
    raise NotImplementedError("Phase 3")
