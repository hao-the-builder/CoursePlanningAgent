# Decisions

Choices the developer made that `CLAUDE.md` does not already settle, or that
override it. Newest first. Each one names the phase it affects, so a later
phase does not silently contradict a decision taken earlier.

---

## 2026-11-05 - Four additions to `schema.py`, agreed one at a time

Hard rule 9 forbids changing the six rule types' semantics and allows adding
fields. Everything below is additive; the six rule types are untouched and
`python schema.py` still prints exactly what it printed in Phase 0.

| Added | Why |
|---|---|
| `Course.credits_max` | 150 catalog courses have a credit *range* ("1-4 Credit(s)"): UROP, independent study, special topics. `credits` holds the minimum, `credits_max` the top, `None` when fixed. Collapsing to the minimum would understate term load and the 120-credit total. |
| the `n_areas` rule type | The Common Core Broadening requirement is "12 credits from 4 different non-home areas" where 5 areas are usually eligible. `cc_area` pins one area and a `RequirementGroup` requires *all* its rules, so the choice could not be expressed. `evaluate()` gained one branch and a `_spread` helper; no existing branch changed. |
| `Program.caveats` | A line that yields a rule but states a refinement no rule type can carry - COMP's "at least 3 courses from 1 area and at least 2 outside" - would otherwise land in `unparsed_lines` and, under Part D, make COMP and most large majors `unsupported` over refinements that were read correctly. `unparsed_lines` keeps its strict meaning; a caveat means "checked, but not this part of it" and travels to the `.docx` and the Progress sheet's "Things to check". 463 of them. |
| `Program.parent` | Names the base program when a file is a track or option variant (see the next decision). |

---

## 2026-11-05 - Tracks and options become one program file each

**Decision.** 22 of the 68 requirement PDFs define tracks ("students should
follow one of the tracks and complete all requirements") or options (optional
add-ons, often behind a CGA bar). A `Program` holds one flat list of groups
that must all be met, so each selectable variant is written as its own file:
the shared requirements plus that variant's groups, with `parent` naming the
base. 68 programs become **129 files**, 60 of them variants.

**Consequences.**

- The intake dropdown in Phase 6 lists variants, which is the choice a student
  actually faces: "BSc in Mathematics - Statistics Track", not "BSc in
  Mathematics".
- Where the track choice is mandatory (`BIOT`, `CHEM`, `DASC`, `GCS`, `MATH`)
  the **base** program is not a complete curriculum, so it is marked
  `unsupported` and the agent asks for a track before planning (hard rule 5).
- `program_index.json` gained `parent`, and each variant inherits the base
  program's Common Core home areas.

---

## 2026-11-05 - 74 courses are read from the requirement PDFs, not the catalog

**Decision.** `data/catalog.json` holds 1,649 courses: 1,575 from the course
pages, plus 74 the requirement PDFs offer as electives but the 2026-27 course
pages do not list - 5000-level postgraduate courses, and lettered sections of
a parent course (`COMP 4901B Large Language Models`, where the catalog has
only `COMP 4901 Special Topics, 0-4 credits`). Each is printed in the PDF with
its own title and credit value.

**Why.** Hard rule 1 requires every course in an output to exist in
`catalog.json`. Leaving these out would drop 27 of COMP's elective options and
22 of CPEG's without making anything safer, and nothing is invented: the
requirement PDFs are an official source already recorded in `raw/SOURCES.md`.
`data/CATALOG_SOURCES.md` lists which course came from which PDF.

**The other direction.** 34 courses that a PDF's own remarks call deleted, last
offered in an earlier year, or "subject to approval" are **not** added. Every
rule that named one has it removed and says so in a caveat.

---

## 2026-11-05 - Part D's credit tolerance is 12 credits

**Decision.** Part D asks for "a documented tolerance for choose-type rules".
`pipeline/check_program.py` computes a *floor* - the fewest credits that can
satisfy every rule, each course counted once - and fails a program when
`floor + 30` (the Common Core) exceeds the stated degree total by more than
**12 credits**. Between 0 and 12 over is a note, not a failure.

**Why 12.** The floor is approximate in three directions, all of them
understating or overstating by about a course at a time: a variable-credit
course is costed at its minimum, a `one_of` at its cheapest option, and an
Option variant is extra study layered on an already complete degree (`RMBI-FT`
sits 10 credits over, legitimately). Twelve credits is four courses' worth of
that slop. A real double-count is far larger: before the floor counted each
course once, `CHEM-PC` came out 32 credits over.

---

## 2026-11-05 - Two of the five verification programs are track variants

**Decision.** The Phase 2 Part F list is **COMP, MATH-AM, FINA, GCS-SS, IDT**,
not `MATH` and `GCS` as recorded on 2026-11-03.

**Why.** Both `MATH` and `GCS` require the student to choose a track, so the
base program is `unsupported` and there is nothing to verify. `MATH-AM`
(Applied Mathematics) and `GCS-SS` (Social Science) are the stand-ins;
`GCS-IHSS` was not chosen because it still has an unparsed line. The other
three are unchanged. `data/VERIFY.md` lays each rule beside its `source_quote`
for these five.

---

## 2026-11-03 — Programme length: 4 years only

**Decision.** Drop 5-year programme support for now. Build and validate 4-year
plans only.

**Why it came up.** The only programme in the 2026-27 catalog with a
"Normative Program Duration" of 5 years is `T&M-DDP`, the Technology &
Management dual degree — which `CLAUDE.md` section 7 already puts out of scope.
The three extended majors (`EXTM-AI`, `EXTM-CADH`, `EXTM-SUST`) state no
duration at all on their catalog pages, so calling them 5-year would be an
assumption rather than sourced data. No in-scope programme therefore needs 5
years.

**Conflicts with CLAUDE.md** — these still say 4 *or* 5, and should be updated
or read as superseded:

- section 1.1, "Programme length | 4 or 5 years"
- section 1.2, "every term from Y1 Fall to the final term (Y4 Spring or Y5 Spring)"
  and "Programme total label adapts to 4 or 5 years"
- Phase 3 task 1, "Supports 4- and 5-year programmes"
- Phase 3 test 8, "5-year programme term sequence"
- Phase 5 task 1, programme total label adapting to 4 or 5 years
- Phase 7 task 1, "a 5-year programme" among the test profiles

**How it is applied.** `planner/terms.py` takes a `years` argument and is not
hardcoded to 4, so the capability is cheap to restore — but no test profile,
validator path or output label is built for 5 years, and the intake form offers
4 only. Revisit if an in-scope 5-year programme appears.

---

## 2026-11-03 — Programs to hand-verify in Phase 2 Part F

**Decision.** Verify the largest programme in each school, so a reviewer is
most likely to land on a `verified` tier.

| School | Program | Title |
|---|---|---|
| SENG | `COMP` | BEng in Computer Science |
| SSCI | `MATH` | BSc in Mathematics |
| SBM | `FINA` | BBA in Finance |
| SHSS | `GCS` | BSc in Global China Studies |
| AIS | `IDT` | BSc in Innovation, Design and Technology |

The specific five within "largest per school" are my picks and are easy to
swap — `BCB` for `MATH`, `ACCT` for `FINA`, `EVMT` for `IDT`. `data/VERIFY.md`
will lay each rule beside its `source_quote` for these five.

---

## 2026-11-03 — Raw PDFs are not committed to git

**Decision.** `.gitignore` excludes `raw/**/*.pdf` and `raw/**/*.jpg`
(~43 MB of the 48 MB collected).

**Why.** They are re-downloadable byte-for-byte with
`python pipeline/fetch_requirements.py` and `fetch_common_core.py`, and
provenance survives without them: `raw/SOURCES.md` and the committed
`raw/_manifest.jsonl` record the URL, size and SHA-256 of all 208 files, so any
re-download is verifiable. Streamlit Community Cloud clones this repo on every
deploy, and 2 MB beats 48 MB.

**To reverse.** Delete those two lines from `.gitignore` and `git add raw/`.

---

## 2026-11-03 — `schema.py` rule types used as provided

The six rule types are `required`, `one_of`, `choose_n`, `credits_from`,
`cc_area`, `every_term` (hard rule 9 pins their semantics). Worth knowing for
Phase 2: an explicit course list is expressible through `credits_from` because
`_matches` accepts an exact code as a pattern, and it tolerates an `H` suffix,
so `COMP 2012` also matches `COMP 2012H`. No new rule type is needed for
"select N credits from the following list".
