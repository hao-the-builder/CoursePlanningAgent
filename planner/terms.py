"""Term sequence generation (Phase 3).

term_sequence(cohort, years, use_summer, use_winter) -> list[Term], each with a
label (Y2 Fall) and a calendar name (Fall 2027). Supports 4- and 5-year
programmes.

Also provides the ordering helper so that
Transfer < Y1 Fall < Y1 Winter < Y1 Spring < Y1 Summer < Y2 Fall < ...
"""


def term_sequence(cohort: str, years: int, use_summer: bool, use_winter: bool):
    raise NotImplementedError("Phase 3")
