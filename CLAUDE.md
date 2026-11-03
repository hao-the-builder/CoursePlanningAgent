# CLAUDE.md — HKUST Course Planning Agent

> Read this file fully before every task. Work on **one phase at a time**, only when asked
> ("Do Phase N"). Stop at the end of each phase, run its "Done when" checks, and report results.
> Do not start the next phase on your own.

---

## 1. Project overview

**What:** An AI agent that helps HKUST undergraduates plan their courses from now until graduation,
including transfer credits, exchange terms and how they want to spread their workload.

**Users:** HKUST undergraduates of any major (start with the 2026-27 intake cohort) who struggle
to turn scattered official requirement PDFs, the course catalog and Common Core rules into a
term-by-term plan.

**Autonomy dial:** The agent only *recommends* and *writes files*. It never registers for courses,
never emails anyone, never submits anything. The student reviews and edits.

### 1.1 Intake — what the agent asks

**Form (structured fields)**

| Field | Notes |
|---|---|
| School, department, major | Dropdown from `program_index.json`, shows data tier |
| Minor / additional major (optional) | Dropdown |
| Intake cohort | **Required.** Requirements differ by cohort |
| Programme length | 4 or 5 years (default from the program; e.g. 5 for some double/extended programmes) |
| Transfer / advanced standing credits | Total credits, plus each mapped HKUST course; allow "unspecified credit" rows (credits only) |
| Courses taken | Multiselect from catalog, with term |
| Courses currently taking | Multiselect from catalog |
| Exchange | No / Yes → candidate term(s), host university if known, what to use it for (major electives / Common Core / minor / free electives) |
| Workload per term | Min–max credits (e.g. 15–18) |
| Workload spread | Even / **Front-loaded** (free up later years) / Back-loaded |
| Term(s) to keep free | e.g. Y4 Spring; or "graduate early if possible" |
| Summer / winter terms | Willing to take courses? Reserve summers for internships? |
| GPA target | Affects workload advice only. Never predict grades |

**Chat (open-ended, agent asks follow-ups)**
- Direction within the major (e.g. AI, systems, finance)
- Career interests (industry, grad school, startup, specific pathways like HKUST's bachelor–master)
- Background (IB / HKDSE / A-level, strong maths, programming experience)
- Anything the form left ambiguous (e.g. "front-loaded" but also 15-credit max)

### 1.2 Outputs

For **each path** (the agent proposes 2–3), one `.xlsx` with exactly two sheets, plus **one `.docx`**
covering all paths.

**Reference implementation of the target layout:** `samples/sample_course_plan_v4.xlsx`
(built by `samples/build_sample_v4.py`). Match it unless told otherwise.

**Sheet 1 — `Course Plan`**
- Row 1: data banner (tier, cohort, "verify with your advisor")
- Row 2: plan settings line (programme length, workload spread, exchange term, free term(s), transfer credits, target load)
- Header: `Semester | Course Code | Course Name | Credits | Status | Common Core | Major Requirements | Minor Requirements | Notes`
- **Term blocks, in order:** `Transfer` block first (if any), then every term from Y1 Fall to the
  final term (Y4 Spring or Y5 Spring), including summer/winter terms only if used. Each block:
  1. Term header row (e.g. `YEAR 2 · FALL 2027`; exchange terms say `✈️ EXCHANGE (host …)`)
  2. One row per course. The three requirement columns show the **group name** the course fills
     (e.g. `HAIC`, `Core`, `Depth Elective (AI)`, `Elective`); blank in all three = free elective.
     A course may fill two columns (double-count) if the rules allow it.
  3. **Term total row:** total credits; credits counting toward CC / Major / Minor; load tag
     (`🔴 Heavy` ≥18, `🟡 Light — check minimum load` <12, `Normal`, `🟢 Free term`,
     `✈️ Exchange: credits pending approval`, `Earned before HKUST`)
- Free terms appear as a block with "No courses — free term" and a 0 total.
- **Programme total line** at the bottom: `N-year plan · <first term> → <last term> · graduation needs 120`,
  total credits, ✅/❌ vs 120, CC / Major / Minor credits, and `Transfer X · Exchange Y · HKUST Z`.
- Legend under the table.
- Status values: `Taken`, `Current`, `Transfer`, `Planned`, `Exchange` (dropdown).
- Common Core and free-elective choices the student hasn't made are **slots**, e.g. `CC — Arts /
  Common Core Arts course (you choose)`; the `.docx` suggests 2–3 real options for each slot.
  Major requirements use real course codes.
- Exchange rows: code `Host course`, name `<host title>  ≈ <HKUST requirement>`, note `Pending … approval`.

**Sheet 2 — `Progress`**
- Columns: `Requirement | Required | Done | Planned | Exchange (pending) | Remaining | Status`
- Sections: **Major** (one row per requirement group + subtotal), **Common Core** (one row per
  area + subtotal), **Minor** (if any, + subtotal), **Graduation — 120 credits** (each course counted
  once; info rows: transfer credits, free electives, credits double-counted Major + Minor).
- Done = Taken + Current + Transfer. Planned = Planned. Exchange counted separately.
- Status: `✅ On track` (Done+Planned ≥ Required), `⚠️ Needs exchange approval` (only met if exchange
  credits count), `❌ Short`.
- **Things to check** section: every validator warning for this path, in plain English.
- All numbers on both sheets are **Excel formulas** over the Course Plan rows (so the student can edit
  the plan and progress updates). Requirement inputs (Required column, 120) in blue.

**Document (.docx)**
- Title, student summary (inputs echoed back)
- One section per path: overview; why it fits (each reason quotes a stated goal); term-by-term
  workload summary; exchange handling; how the front/back-loading or free term is achieved;
  suggested options for every slot; risks/trade-offs
- "Data and limits": tier, source URLs, cohort, unresolved warnings, "verify with your academic advisor"
- LLM writes only prose; all tables and numbers come from code

---

## 2. Core principle: LLM vs code

| Job | Done by |
|---|---|
| Understanding goals, choosing paths, writing explanations, suggesting slot options | LLM |
| Course codes, credits, prerequisites, exclusions, offerings, requirement rules | Structured data (JSON) |
| Credit totals, requirement checks, prerequisite order, workload/term checks | Deterministic Python |
| Spreadsheet numbers | Excel formulas written by Python (never LLM arithmetic) |

The LLM must never be the source of truth for any fact that exists in the data.

---

## 3. Hard rules (never break these)

1. **Never invent course codes, credits, or requirements.** Every HKUST course in any output must exist in `data/catalog.json`. Slots and exchange rows are explicitly labelled as such.
2. **Never output a plan that failed validation** unless the failures are listed visibly in the `.docx` and the Progress sheet's "Things to check".
3. **Every program JSON must cite its source URL and cohort.** Every output shows the data tier and source year.
4. **If a required input is missing** (cohort, major), ask a follow-up question. Do not guess.
5. **Unsupported programs:** say plainly the program can't be planned reliably yet. Do not produce a plan.
6. **Exchange and unspecified transfer credits are never shown as ✅** until `mapping_approved = true`.
7. **No scraping of pages whose robots.txt disallows it.** If data is only on such a page, stop and ask the developer to download/export it manually.
8. **Never put secrets in code or git.** API keys go in `.env` (local) or Streamlit secrets (deployed).
9. **Do not modify `schema.py` rule types without asking.** Adding fields is OK; changing semantics is not.
10. Keep raw source files unchanged in `raw/`. All derived data goes in `data/`.
11. Facts about HKUST regulations used by validators (minimum/maximum credit load, FYP duration, double-count cap, exchange rules) must come from an official source recorded in `data/regulations.json` with URL. If unknown, the check emits a warning saying "verify", never a made-up threshold.

---

## 4. Tech stack

- Python 3.11+
- `pydantic`, `pdfplumber`, `httpx` + `beautifulsoup4`
- `openpyxl` (.xlsx), `python-docx` (.docx), LibreOffice headless for recalculation checks in tests
- `streamlit` (UI), `pytest` (tests)
- LLM: two interchangeable backends behind one wrapper (Phase 4):
  - `subscription` — local development, developer's Claude plan via the Claude Agent SDK
  - `api` — deployed demo, `anthropic` SDK with `ANTHROPIC_API_KEY`
  - Selected by env var `LLM_BACKEND`. Check current official docs for both SDKs before implementing; do not rely on memory.

---

## 5. Repo layout

```
course-planner/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .env.example                # LLM_BACKEND=subscription|api, ANTHROPIC_API_KEY=, MODEL_FAST=, MODEL_STRONG=
├── schema.py                   # rule schema + evaluator + PlannedCourse (data contract)
├── samples/
│   ├── sample_course_plan_v4.xlsx   # target spreadsheet layout
│   └── build_sample_v4.py           # how it was built (reference only)
├── raw/
│   ├── requirements/           # official requirement PDFs, untouched
│   ├── catalog/                # raw catalog HTML per subject
│   ├── common_core/            # Common Core course list PDF(s)
│   ├── regulations/            # academic regulations pages/PDFs (credit load, exchange, FYP)
│   └── SOURCES.md              # URL + download date for every raw file
├── data/
│   ├── catalog.json            # {code: Course}
│   ├── offerings.json          # {code: ["Fall","Spring",...]} (may be partial)
│   ├── programs/{CODE}.json    # one Program per major/minor, cohort 2026-27
│   ├── common_core.json        # Common Core Program for the cohort
│   ├── regulations.json        # load limits, double-count cap, FYP rules, exchange rules — each with source URL
│   └── program_index.json      # code, title, kind, school, tier, default_years
├── pipeline/
│   ├── fetch_requirements.py
│   ├── fetch_catalog.py
│   ├── parse_catalog.py
│   ├── pdf_to_text.py
│   ├── check_program.py        # auto-checks + tier assignment
│   └── build_index.py
├── planner/
│   ├── llm.py                  # backend-agnostic LLM wrapper
│   ├── terms.py                # term sequence generation (Y1 Fall … Y5 Spring, summers/winters, calendar years)
│   ├── tools.py                # deterministic tools exposed to the agent
│   ├── validate.py             # full plan validation
│   ├── allocate.py             # assigns each course to requirement groups (double-count rules)
│   ├── intake.py               # StudentProfile model + follow-up question logic
│   ├── agent.py                # agent loop
│   ├── prompts/                # system + task prompts as .md files
│   └── logging.py              # JSONL action log
├── outputs/
│   ├── xlsx_builder.py
│   └── docx_builder.py
├── app.py                      # Streamlit UI
├── scripts/run_eval.py
├── logs/                       # runs/{timestamp}.jsonl (gitignored)
└── tests/
    ├── test_schema.py
    ├── test_terms.py
    ├── test_tools.py
    ├── test_validate.py
    ├── test_outputs.py
    ├── profiles/               # test student profiles (JSON)
    └── expected/               # hand-calculated expected results
```

---

## 6. Phases

Each phase lists **Goal → Tasks → Done when.** Commit at the end of each phase with message
`Phase N: <summary>`.

---

### Phase 0 — Project setup

**Goal:** Empty but runnable project.

**Tasks**
1. Create the repo layout above (empty modules with docstrings are fine).
2. Keep `schema.py`, `samples/sample_course_plan_v4.xlsx` and `samples/build_sample_v4.py` unchanged.
3. `requirements.txt` with pinned major versions.
4. `.env.example` and `.gitignore` (ignore `.env`, `logs/`, `__pycache__/`, generated outputs).
5. `README.md`: what it is, install, run tests, switch backends.
6. `tests/test_schema.py` runs the example in `schema.py` and asserts: `COMP 9999` is flagged unknown;
   depth electives rule is unmet; programming core is met; `PlannedCourse(status="exchange")` validates.

**Done when**
- `pip install -r requirements.txt` works in a fresh venv
- `pytest` passes
- `python schema.py` prints the example output

---

### Phase 1 — Collect raw data

**Goal:** All official source material saved locally with provenance.

**Tasks**
1. **Requirement PDFs** → `raw/requirements/`
   - Known URL pattern (verified for 2025-26): `https://ugadmin.hkust.edu.hk/prog_crs/ug/202526/pdf/25-26comp.pdf`
   - For the 2026-27 cohort, find the correct pattern from the official Program & Course Catalog
     (`https://prog-crs.hkust.edu.hk/ugprog/2026-27/...`). Do not guess.
   - Build the list of all majors and minors for the cohort from the catalog index page.
   - `pipeline/fetch_requirements.py` downloads each, skips existing files, sleeps between requests, respects robots.txt.
2. **Course catalog** → `raw/catalog/{SUBJECT}.html` from `https://prog-crs.hkust.edu.hk/ugcourse/2026-27/{SUBJECT}`,
   every subject listed on `https://prog-crs.hkust.edu.hk/ugcourse`.
3. **Common Core list** → `raw/common_core/` from `https://uce.ust.hk/web/resources/Active_Course_List_30-credit.pdf`
   (and any cohort-specific list on uce.ust.hk).
4. **Regulations** → `raw/regulations/`: find official HKUST pages for credit load limits per term,
   double-counting between Major/Minor/Common Core, credit transfer/advanced standing, exchange credit
   transfer, and graduation requirements. Save them and list them in `SOURCES.md`. If not findable,
   list as TODO for the developer.
5. **Term offerings:** the class schedule site (`w5.ab.ust.hk/wcq`) disallows automated access.
   **Do not scrape it.** Leave `data/offerings.json` empty and add a TODO in `SOURCES.md`.
6. Write every URL + download date to `raw/SOURCES.md`.

**Done when**
- `raw/requirements/` has one PDF per major and minor in the cohort list (report count and any missing)
- `raw/catalog/` has one file per subject
- `raw/regulations/` has what could be found; gaps listed as TODOs
- `raw/SOURCES.md` complete; nothing in `raw/` hand-edited

---

### Phase 2 — Build structured data

**Goal:** `catalog.json`, `common_core.json`, `regulations.json`, one `programs/{CODE}.json` per program, each with a tier.

**Part A — Catalog (deterministic, no LLM)**
1. `pipeline/parse_catalog.py` parses each `raw/catalog/*.html` into `Course` objects:
   code, title, credits, prereq_expr (raw text), exclusions.
2. Tag Common Core areas from the Common Core list into `common_core_areas`.
3. Write `data/catalog.json`. Report: total courses, courses with no credits parsed, parse failures.

**Part B — Program extraction (done by Claude Code itself, not via API)**
1. `pipeline/pdf_to_text.py {file}` prints clean text (keep table rows on one line where possible).
2. For each program, Claude Code reads the text and writes `data/programs/{CODE}.json` as a `Program`:
   - Map every requirement line to one of the 6 rule types in `schema.py`
   - Exact PDF sentence in `source_quote` for each group
   - Anything that doesn't fit → `unparsed_lines`. **Never silently drop text**
   - Fill `stated_total_credits` and `max_double_count_credits` if stated
   - Add `default_years` (4 or 5) to the index if the PDF states programme duration
   - `tier = auto_extracted` (Part C may downgrade)
3. Batches of ~5 programs; report after each batch.
4. Common Core requirements the same way → `data/common_core.json` (kind = `common_core`).

**Part C — Regulations**
- Extract from `raw/regulations/` into `data/regulations.json`, each value with `source_url` and
  `source_quote`: min/max credits per regular term, overload rules, summer/winter limits, double-count
  caps, transfer/exchange credit rules, FYP duration (per program if stated). Missing values = `null`.

**Part D — Auto-checks** (`pipeline/check_program.py`)
For each program JSON:
- Loads as a valid `Program`
- Every course code in every rule exists in `catalog.json`
- Sum of required credits is consistent with `stated_total_credits` (documented tolerance for choose-type rules)
- `unparsed_lines` is empty
- Pass → `auto_extracted`; fail → `unsupported` + reasons in `data/programs/{CODE}.issues.md`

**Part E — Index**: `pipeline/build_index.py` → `data/program_index.json`.

**Part F — Human verification (the developer does this)**
- Claude Code writes `data/VERIFY.md` for 5 programs, one per school (SENG, SSCI, SBM, HSS, AIS):
  each rule side by side with its `source_quote`.
- The developer checks each against the PDF and tells Claude Code which to mark `verified`.

**Done when**
- Report table: program | tier | issues count
- `regulations.json` exists with sources; nulls listed
- At least 5 programs `verified` (after human check)
- `pytest` passes, including tests that load every program JSON

---

### Phase 3 — Deterministic tools and validation

**Goal:** Every fact-check the agent needs is plain Python with tests.

**Tasks**
1. `planner/terms.py`
   - `term_sequence(cohort, years, use_summer, use_winter) -> list[Term]` with labels (`Y2 Fall`) and
     calendar names (`Fall 2027`). Supports 4- and 5-year programmes.
   - Ordering helper so `Transfer` < `Y1 Fall` < `Y1 Winter` < `Y1 Spring` < `Y1 Summer` < `Y2 Fall` …
2. `planner/tools.py`
   - `get_program(code)`, `list_programs(kind=None)`
   - `search_courses(query, subject=None, level=None)` — keyword search over catalog
   - `parse_prereq(expr) -> boolean tree`; unparseable → flag, don't fail
3. `planner/validate.py` — each check returns errors (blocking) and warnings (non-blocking), each with
   a plain-English message plus the course/term it refers to:
   - `unknown_courses` — HKUST codes not in catalog (slots and exchange rows exempt) → **error**
   - `check_prereqs` — prereqs taken in an **earlier** term, or transfer → **error**
   - `check_exclusions` — no two mutually exclusive courses → **error**
   - `check_offering` — offered in that term; no data → **warning** "verify on class schedule"
   - `check_load` — per regular term within the student's min–max → outside = **error**; outside
     `regulations.json` limits = **error**; regulation unknown and term <12 credits → **warning** "check minimum load"
   - `check_heavy_terms` — terms ≥18 credits combined with a high GPA target → **warning**
   - `check_exchange` — no HKUST courses in exchange terms; exchange credits listed as pending;
     every-term-in-residence courses (e.g. `every_term` rules like COMP 4900) not required in exchange
     terms; requirements met only via exchange → **warning** "needs exchange approval"
   - `check_free_terms` — terms the student asked to keep free contain no courses → **error**; if a
     free final term means graduating early, say so → **info**
   - `check_spread` — front-loaded: credits in the first half ≥ second half; back-loaded the reverse;
     even: no term differs from the mean by more than 4 credits → **warning** if not met
   - `check_fyp` — FYP placement vs regulation (e.g. must span two terms if stated); unknown → **warning**
   - `check_transfer` — unspecified transfer credits counted only as free electives; mapped transfers
     must exist in catalog → **error** if not
   - `check_every_term` — `every_term` rules satisfied for all terms in residence
   - `evaluate` + `total_credits >= 120` (and programme-specific totals) → **error** if short
     (exchange-pending shortfall → **warning**)
4. `planner/allocate.py` — assign each course to requirement groups, respecting
   `max_double_count_credits`. Greedy first, documented. Exceeding the cap → **error**.
5. `validate_plan(plan, profile) -> ValidationReport` runs everything above.

**Tests**
Hand-write test plans in `tests/profiles/` with expected results in `tests/expected/`:
1. Correct 4-year plan
2. Prereq out of order
3. Overloaded term
4. Hallucinated course
5. Double-count overflow
6. Front-loaded with Y4 Spring free (should pass; info "graduate early")
7. Exchange term containing an HKUST course (error) and a requirement met only by exchange (warning)
8. 5-year programme term sequence
9. 24 transfer credits incl. 6 unspecified

**Done when**
- `pytest` passes for all cases
- `validate_plan` returns exactly the expected errors/warnings for each

---

### Phase 4 — LLM wrapper and agent loop

**Goal:** An agent that turns a profile into 2–3 validated paths.

**Tasks**
1. `planner/llm.py`: one interface, e.g. `chat(messages, tools, model)`, backends selected by `LLM_BACKEND`
   (`subscription` → Claude Agent SDK with the developer's plan, local only; `api` → `anthropic` SDK).
   Check current official docs first. `MODEL_FAST` for intake and retries, `MODEL_STRONG` for planning and the doc.
2. `planner/intake.py`: `StudentProfile` pydantic model with **every field in Section 1.1**, including
   `programme_years`, `transfer_credits: list[PlannedCourse]`, `exchange: ExchangePlan | None`
   (terms, host, purposes), `workload_min/max`, `spread: Literal["even","front","back"]`,
   `free_terms: list[str]`, `use_summer`, `use_winter`, `gpa_target`.
   `missing_required(profile)` returns empty required fields (cohort, major at minimum).
3. `planner/prompts/`: system prompt (role, hard rules from Section 3, autonomy limits) and planning prompt.
   The planning prompt must tell the LLM the term sequence, free terms, exchange terms and spread, and
   to make the 2–3 paths **meaningfully different** (e.g. with vs without exchange, AI depth vs systems depth).
4. `planner/agent.py` loop:
   1. If `missing_required` → return follow-up questions, stop
   2. Load program(s); any `unsupported` → explain and stop
   3. LLM drafts 2–3 paths as JSON (`PlannedCourse` lists + short rationale + slot suggestions), using
      `search_courses` / `get_program` as tools
   4. `validate_plan` each path
   5. Errors → send report back to the LLM to fix; max 5 iterations
   6. Return paths + final reports (including unresolved errors)
5. `planner/logging.py`: every step to `logs/runs/{timestamp}.jsonl` (inputs, tool calls, validation
   results, iterations, final status). Evidence for the test log.

**Done when**
- `python -m planner.agent tests/profiles/<verified-major>.json` produces 2–3 paths, zero blocking errors
- The front-loaded + free Y4 Spring + exchange profile produces a valid plan that respects all three
- Missing cohort → follow-up question; unsupported major → refusal message
- A JSONL log exists for each run

---

### Phase 5 — Output files

**Goal:** The `.xlsx` and `.docx` the student downloads, matching Section 1.2.

**Tasks**
1. `outputs/xlsx_builder.py`
   - One workbook per path: `Course Plan` + `Progress`, matching `samples/sample_course_plan_v4.xlsx`
     (term blocks, term totals, programme total line, legend, statuses, colours, dropdown, frozen header)
   - All numbers as Excel formulas; prefer `SUMIFS` / `SUMPRODUCT` (no XLOOKUP/FILTER/dynamic arrays)
   - Formula ranges must exclude term header and term total rows from Progress calculations (filter by Status)
   - "Things to check" filled from the path's `ValidationReport`
   - Programme total label adapts to 4 or 5 years
2. `outputs/docx_builder.py` — per Section 1.2; LLM writes prose only.
3. Tests: generate files for test profiles 1, 6, 7, 8; recalculate with LibreOffice headless; reopen
   with `data_only=True` and assert: zero formula errors; programme total = sum of term totals;
   Progress numbers match `tests/expected/`; exchange requirements show ⚠️; every HKUST code exists in the catalog.

**Done when**
- Files open correctly in Excel / Google Sheets / Word
- Numbers match hand-calculated expected values
- `pytest` passes

---

### Phase 6 — Streamlit UI

**Goal:** A usable web app.

**Tasks**
1. `app.py` flow:
   1. **Form** — all Section 1.1 form fields. Transfer credits as an editable table (code or
      "unspecified" + credits). Exchange section shown only if "Yes". Free-term picker built from `term_sequence`.
   2. **Chat** — direction, career interests, background; agent asks follow-ups
   3. **Generate** — spinner; for each path show summary, credits-per-term mini chart, validation status
   4. **Download** — one `.xlsx` per path + one `.docx` (or a zip)
2. Tier badge and "verify with your advisor" note shown prominently.
3. Abuse limits: max generations per session, max chat turns.
4. Works at phone width.

**Done when**
- Full flow works locally with `LLM_BACKEND=subscription`
- Unsupported major and missing-cohort cases show the right messages

---

### Phase 7 — Testing, test log, deploy

**Goal:** Ready for peer review.

**Tasks**
1. 10–15 profiles in `tests/profiles/` across the verified majors, including: transfer credits (incl.
   unspecified), exchange term, front-loaded with free final term, back-loaded, 5-year programme,
   overloaded workload request, missing cohort, unsupported major, a minor, out-of-scope request
   ("register me for COMP 3711"), prompt injection in a chat field.
2. `scripts/run_eval.py` runs all profiles → `logs/eval_report.md`:
   profile | outcome | blocking errors | warnings | iterations | pass/fail vs expected.
3. Draft `TEST_LOG.md` (~300 words) **from the eval report only**: cases run, what broke, what was
   fixed, what wasn't and why. The developer edits it. Do not invent results.
4. Deploy to Streamlit Community Cloud with `LLM_BACKEND=api`, key in Streamlit secrets. The developer
   sets a spend limit in the Claude Console.
5. Draft `SAMPLE_QUERIES.md` with 3–5 reviewer scenarios (core value, exchange + front-loading,
   one graceful refusal).

**Done when**
- Public link works from a fresh browser and a phone
- Eval report shows all expected outcomes
- `TEST_LOG.md` and `SAMPLE_QUERIES.md` exist for the developer to review

---

## 7. Out of scope (do not build unless asked)

- User accounts or saving plans server-side
- Registering for courses or contacting anyone
- Grade prediction
- Cohorts other than 2026-27
- Dual degree programmes (mark as unsupported for now)
- Looking up which host-university courses map to which HKUST courses (student enters them; agent marks them pending)
- Scraping any site that disallows it

---

## 8. Commands

```bash
pip install -r requirements.txt
pytest
python schema.py
python pipeline/check_program.py --all
python -m planner.agent tests/profiles/<file>.json
streamlit run app.py
python scripts/run_eval.py
```

## 9. How to report at the end of each phase

- What was built (files)
- "Done when" checks: pass/fail each
- Anything skipped, assumed, or needing the developer's decision
- Suggested commit message
