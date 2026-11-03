"""Agent loop: student profile in, 2-3 validated paths out (Phase 4).

  1. missing_required non-empty -> return follow-up questions and stop
  2. load the program(s); any unsupported tier -> explain and stop
  3. the LLM drafts 2-3 meaningfully different paths as JSON (PlannedCourse
     lists, a short rationale, slot suggestions), using search_courses and
     get_program as tools
  4. validate_plan each path
  5. errors -> hand the report back to the LLM to fix, at most 5 iterations
  6. return the paths plus their final reports, unresolved errors included

Usage: python -m planner.agent tests/profiles/FILE.json

The agent only recommends and writes files. It never registers for courses,
never emails anyone, never submits anything.
"""


def main() -> None:
    raise NotImplementedError("Phase 4")


if __name__ == "__main__":
    main()
