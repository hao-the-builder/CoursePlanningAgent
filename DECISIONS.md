# Decisions

Choices the developer made that `CLAUDE.md` does not already settle, or that
override it. Newest first. Each one names the phase it affects, so a later
phase does not silently contradict a decision taken earlier.

---

## 2026-11-10 — A Dify backend, with the data and the verdict kept here

**Decision.** The agentic workflow can run on Dify. `dify/course-planner.yml`
is the workflow as a DSL export, `service/tool_api.py` puts the deterministic
tools on HTTP so Dify can reach them, and `planner/dify.py` drives a run and
judges the result. This adds a path CLAUDE.md §4 does not list; the two
`LLM_BACKEND` backends are unchanged and remain the default.

**Why it is not a third `LLM_BACKEND`.** `planner/llm.py` wraps a chat
primitive — one question, one answer, a tool loop around it. Dify exposes
nothing that shape: its Service API runs a whole app server-side and never
hands a tool call back to the caller (the only pause is a Human Input node,
for a person filling a form). So the Dify workflow replaces the *agent loop*,
making it a sibling of `planner/agent.py`, not a backend underneath it. A
`dify` entry in `BACKENDS` would have had to pretend to a contract it cannot
keep.

**What does not move.** The catalog is not uploaded to Dify — the workflow
asks the tool service for every code, credit and rule, so there stays one copy
of the data and it is the one in `data/`. And `planner/dify.py` re-runs
`validate_plan` locally on whatever comes back: the workflow validates its own
work, which is how its repair pass works, but no plan is presented on the
strength of a remote check (hard rule 2). A disagreement between the two
verdicts is reported, because it means the workflow is reading a different
service or stale data.

**The retry loop is unrolled to one pass.** A Dify workflow graph is a DAG.
A conditional loop back to an earlier node needs a `loop` node whose DSL shape
could not be verified against any real export, and hand-authoring one from
prose docs would ship a file that may not import. So the graph always runs one
repair pass, with the model told to return the plan untouched when the verdict
is already clean. `planner/agent.py` keeps the five-retry version.

**The DSL is declared `0.1.5`, not `0.7.0`.** Every node shape in the file was
copied from a real `0.1.x` export; no real export at Dify's current `0.7.0`
could be found. Declaring the current version would claim shapes that were
never seen, so the file imports one minor version behind and lets Dify migrate
it, which costs a "completed with warnings" notice on import.

**No secret in the artifact.** The YAML is what gets handed in, so the tool
service's URL and token are Start-node inputs supplied at run time rather than
values in the file. Dify environment variables were the alternative and were
rejected: their export semantics around secret values are documented but their
`value_type` string could not be verified, and a wrong guess would have put a
token in a submitted file.

**New dependency:** `pyyaml`, so `tests/test_dify_workflow.py` can read the
DSL and check it. `starlette` and `uvicorn` were already arriving with
streamlit and are now named explicitly.

---

## 2026-11-09 — Five programs are `verified`, and the tier carries a date

**Decision.** The developer checked `data/VERIFY.pdf` against the official
PDFs and reported all five correct, so `COMP`, `MATH-AM`, `FINA`, `GCS-SS` and
`IDT` are `tier: verified`. Phase 2's "at least 5 programs verified" is met.

**The tier now carries a date.** `Program.verified_on` records the day of the
check (an additive field — hard rule 9 permits that). `tier: verified` is a
claim about a *particular document*, not about a program: `source_url` names
the PDF and `raw/_manifest.jsonl` records when it was downloaded, so without a
date the claim would survive a refetch for another cohort in total silence and
nothing would show that it had gone stale. The date is shown wherever the tier
is — the app's badge, the workbook legend, the document's "Data and limits".

**What this does not change.** 92 programs are still `auto_extracted` and 32
`unsupported`; most of the catalog shows the amber badge, which is correct.
Verification here means the extracted rules match the PDF, not that the plan
is right for any student — every output still says to check with an advisor.

**Why the badge tests no longer name a program.** They ask the index for a
program at the tier under test, because a test that names one breaks on the
day someone verifies it — the one day the suite should stay green.

---

## 2026-11-08 — The app is restyled in place, and gains a plan-aware assistant

**Streamlit stays.** A React front end would give total design freedom and
cost a FastAPI layer over `planner/`, a second deploy target, and a rewrite of
the eleven headless UI tests. The look was the problem, not the framework, so
the fix is a stylesheet (`ui/style.py`) and HTML fragments
(`ui/components.py`) written against Streamlit's own `data-testid` hooks, with
`app.py` left as a reading of the flow.

**The design follows the `apple-design` skill** in `D:/Skills for AI`. The
parts that earn their place in a form-and-tables app are typography (tracking
is size-specific, hierarchy comes from weight and leading, not size alone),
response (feedback on the press, 100ms, never on release), materials (one
translucent layer for the top bar, a gradient scroll edge rather than a 1px
rule), restraint (motion only where it explains something), and the three
accessibility signals — reduced motion, reduced transparency, increased
contrast — each answered with a gentler equivalent rather than nothing.

The generic bar chart is replaced by a term strip that colours each term by
what its load *means*: heavy, light, free, exchange. A bar chart drew a
9-credit term and a free term as the same kind of thing. The thresholds are
the ones the workbook's load-tag formula uses, so the two renderings cannot
disagree in front of a student.

**The assistant may revise, under a gate.** `planner/assistant.py` answers
questions about a finished plan and can change it. The model reads the plan
and the requirement data through the agent's own tools and writes the revised
course list; nothing it writes reaches the student until `validate_plan` has
judged it, and a revision that raises the blocking-error count is discarded
with its errors quoted. That keeps hard rules 1 and 2 true of the chat as
well as of the planner: an invented course cannot survive parsing into
`PlannedCourse` plus `unknown_courses`, and a plan with problems is never
shown as though it had none.

The change list shown to the student is computed by comparing the two plans,
not taken from the model's account of what it did — in testing it will claim
more than it changed. It counts `(course, term)` pairs rather than courses,
because COMP 4900 is required in *every* term in residence and keying by code
would hide a move of one of them.

---

## 2026-11-08 — An option is taken *within* its track, and three extraction fixes

The first round of human verification (Phase 2 Part F) reported two errors in
`data/VERIFY.pdf`. Both were checked against the PDFs and both were wrong:
`ACCT 2010 Principles of Accounting I` is what the SBM School Requirements
state, and `Social Science Track` is a top-level track in the GCS PDF whose
five required courses are exactly what the data holds. Nothing was changed on
either report. Re-reading the PDFs line by line to prove that did turn up
three real defects, fixed here.

**1 · An elective list no longer ends at an "Any SUBJ courses" row.** The IDT
PDF lists `ELEC | Any ELEC courses at 3000-level | 0-4` *inside* the 21-credit
Project-related Electives list. Because the row carries a credit figure the
extractor read it as a new requirement, which closed the list and bound the
remaining 26 candidates to it. A row that names a subject rather than a course
and asks for a minimum of zero credits requires nothing, so it is now absorbed
into the open list. IDT's rule went from 25 of the PDF's 51 courses to all 51,
plus `ELEC 3xxx` and `ELEC 4xxx`.

**2 · A candidate list may hold named courses *and* an open subject.** GCS's
`Others — Any SOSC courses` was recorded in the quote and dropped from the
rule, so the 27-credit requirement demanded all nine courses from the
Restricted list where the PDF asks for at least four. Both now go into
`credits_from`. Where such a list also states a course count, the `choose_n`
rule is replaced by a caveat: a count cannot be checked against a list with no
end, and inventing a bound would be worse than saying so.

**3 · An option inherits the track it is taken within.** The GCS PDF prints
`Option(s)` inside the Integrated Humanities and Social Science Track and says
in words that each option is for "students in the ... Track". The seven option
variants held the base major plus their own electives and not the track's, so
each was about 24 credits short.

Position on the page is not enough to establish this, and a first attempt that
used it was wrong: the PHYS PDF prints `Option(s)` after its IRE Track too,
and those three options stand alone — the PDF says only "students in the
Computational Physics with AI Option should also take ...". So an option
inherits a track only when the option's own prose names it. That keeps the
seven GCS options and the three CHEM ones (whose PDF says "students in the
Core Chemistry Track ... may enroll") and leaves PHYS as it was. Where the
prose offers two routes, as CHEM's does, the data takes the one it names first
and the sentence itself travels as a caveat. They now carry the track's groups, caveats
and its one unparsed line — which moves all seven to `unsupported`. That is
the honest state: they were plannable before only because requirements were
missing. Parsing that line (the elective block that is 24 credits with one
capstone choice and 27 with another) would bring them back, and is not done
here because the PDF states two different requirements and picking one is a
judgment the data should not make quietly.

**Also:** `RequirementGroup` gains `source_url` (additive, hard rule 9), set
for the School Requirements groups, which come from a different PDF than the
program's own. `data/VERIFY.md` prints it. Without it the verification pack
pointed a reader at the program PDF for a row that is not in it — which is
what produced the first of the two mistaken reports.

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
