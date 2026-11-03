"""Auto-check each data/programs/{CODE}.json and assign its tier (Phase 2, Part D).

Checks per program:
  - loads as a valid schema.Program
  - every course code in every rule exists in data/catalog.json
  - required credits are consistent with stated_total_credits
    (with a documented tolerance for choose-type rules)
  - unparsed_lines is empty

Pass -> tier auto_extracted. Fail -> tier unsupported, with reasons written to
data/programs/{CODE}.issues.md

Usage: python pipeline/check_program.py --all
"""


def main() -> None:
    raise NotImplementedError("Phase 2")


if __name__ == "__main__":
    main()
