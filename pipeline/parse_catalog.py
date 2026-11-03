"""Parse raw/catalog/*.html into data/catalog.json (Phase 2, Part A).

Deterministic, no LLM. Produces one schema.Course per course: code, title,
credits, prereq_expr (raw text), exclusions, plus common_core_areas tagged from
the Common Core course list.

Reports total courses, courses with no credits parsed, and parse failures.
"""


def main() -> None:
    raise NotImplementedError("Phase 2")


if __name__ == "__main__":
    main()
