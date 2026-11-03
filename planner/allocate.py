"""Assign each course to the requirement groups it fills (Phase 3).

Fills the three requirement columns of the Course Plan sheet: Common Core,
Major, Minor. A course may fill two columns when the rules allow double
counting, subject to Program.max_double_count_credits.

Greedy, with the order documented. Exceeding the cap is an error, not a warning.
"""


def allocate(plan, programs):
    raise NotImplementedError("Phase 3")
