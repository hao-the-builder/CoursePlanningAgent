"""Build one .xlsx per path: Course Plan + Progress (Phase 5).

Matches samples/sample_course_plan_v4.xlsx: term blocks, term totals, the
programme total line, the legend, statuses, colours, the status dropdown and a
frozen header. The programme total label adapts to a 4- or 5-year plan.

All numbers are Excel formulas, preferring SUMIFS and SUMPRODUCT. No XLOOKUP,
no FILTER, no dynamic arrays -- the file has to open in Google Sheets too.
Formula ranges must exclude term header and term total rows from the Progress
calculations by filtering on Status.

"Things to check" is filled from the path ValidationReport.
"""


def build_workbook(path, profile, report, out_path):
    raise NotImplementedError("Phase 5")
