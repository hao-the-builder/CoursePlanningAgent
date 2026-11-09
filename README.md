# HKUST Course Planning Agent

An AI agent that helps HKUST undergraduates turn scattered requirement PDFs, the
course catalog and Common Core rules into a term-by-term plan from now until
graduation — including transfer credits, an exchange term and how they want to
spread their workload.

For each of 2–3 proposed paths it writes one `.xlsx` (a `Course Plan` sheet and a
live-formula `Progress` sheet), plus one `.docx` explaining all the paths.

**The agent only recommends and writes files.** It never registers for courses,
never emails anyone and never submits anything. Every output carries its data
tier and a "verify with your academic advisor" note.

## How it is built

The split that keeps it honest:

| Job | Done by |
|---|---|
| Understanding goals, choosing paths, writing explanations, suggesting options for open slots | LLM |
| Course codes, credits, prerequisites, exclusions, offerings, requirement rules | Structured JSON under `data/` |
| Credit totals, requirement checks, prerequisite order, workload checks | Deterministic Python |
| Every number in the spreadsheet | Excel formulas written by Python |

The LLM is never the source of truth for a fact that exists in the data, and no
course appears in an output unless it exists in `data/catalog.json`.

## Install

Python 3.11 or newer (developed on 3.14).

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
cp .env.example .env          # then edit .env
```

## Run

```bash
pytest                                        # tests
python schema.py                              # the data-contract example
python pipeline/parse_catalog.py              # raw/catalog  -> data/catalog.json
python pipeline/extract_programs.py           # raw/requirements -> data/programs
python pipeline/check_program.py --all --write   # re-check and re-tier
python pipeline/build_index.py                # -> data/program_index.json
python pipeline/pdf_to_text.py raw/requirements/COMP.pdf  # read one PDF
python -m planner.agent tests/profiles/X.json # one plan from one profile
streamlit run app.py                          # the UI
python scripts/run_eval.py                    # all profiles -> logs/eval_report.md
```

## The app

Four steps down one column — about you, how you want to study, anything to
add, generate — then the plan, an assistant, and the downloads.

**The assistant** (`planner/assistant.py`) is the chat beside a finished
plan. It answers questions about that plan using the same tools the planner
used, so a claim about a prerequisite is read from the data rather than
recalled. It also makes changes: *move the exchange to Y3 Fall*, *swap the
FYP for co-op*, *make my final year lighter*. A revision is parsed into real
course rows, validated in full, and **applied only if it is no worse than the
plan it replaces** — one that breaks a prerequisite or overruns a term is
reported and discarded, and the student keeps what they had. The list of
changes shown is computed by comparing the two plans, never taken from the
model's description of its own work.

**The look** follows the `apple-design` skill in `D:/Skills for AI`:
size-specific tracking, hierarchy from weight and leading rather than size
alone, feedback on the press rather than the release, one translucent layer
for the top bar with a soft scroll edge instead of a rule, and an answer for
each of `prefers-reduced-motion`, `prefers-reduced-transparency` and
`prefers-contrast`. The term strip colours each term by what its load *means*
— heavy, light, free, exchange — using the same thresholds the workbook's
load-tag formula uses, so the browser and the spreadsheet cannot disagree.

## Deploying

Streamlit Community Cloud, pointed at this repository with `app.py` as the
entry point. Three things to set up, in this order:

1. **Set a spend limit in the Claude Console** before anything else. The two
   model runs recorded in `TEST_LOG.md` cost about $1.25 each.
2. Paste `.streamlit/secrets.toml.example` into the app's **Secrets** box and
   fill in the key. `app.py` copies those into the environment on startup,
   because Streamlit Cloud supplies them through `st.secrets` rather than the
   environment, and `planner/llm.py` reads the environment. The real
   `.streamlit/secrets.toml` is gitignored and must never be committed.
3. `LLM_BACKEND=api` there; `subscription` only works where the `claude` CLI
   is installed and signed in, which it is not on Cloud.

The clone stays small — raw PDFs are not committed (see `DECISIONS.md`), so
a deploy pulls about 3 MB.

## Switching LLM backends

One wrapper, `planner/llm.py`, two interchangeable backends chosen by the
`LLM_BACKEND` environment variable in `.env`:

| `LLM_BACKEND` | Uses | For |
|---|---|---|
| `subscription` | Claude Agent SDK, the developer's Claude plan | local development |
| `api` | `anthropic` SDK with `ANTHROPIC_API_KEY` | the deployed demo |

`MODEL_FAST` handles intake and retries; `MODEL_STRONG` handles planning and the
document prose. Deployed on Streamlit Community Cloud the key lives in Streamlit
secrets, never in the repo.

## Layout

```
schema.py          rule schema + evaluator + PlannedCourse — the data contract
samples/           the target spreadsheet layout, and the script that built it
raw/               official PDFs and HTML, untouched, with SOURCES.md provenance
data/              derived JSON: catalog.json (1,649 courses),
                   programs/{CODE}.json (129, incl. track/option variants),
                   program_index.json, common_core.json, regulations.json
pipeline/          fetch and parse raw sources into data/
planner/           terms, tools, validation, allocation, intake, agent loop,
                   and assistant.py — the chat that answers about a finished
                   plan and revises it
ui/                the app's stylesheet and HTML fragments
outputs/           the .xlsx and .docx builders
tests/             tests, student profiles, hand-calculated expected results
```

Raw source files stay unchanged in `raw/`; everything derived goes in `data/`.

## Status

Built in phases, one at a time — see `CLAUDE.md` for the plan and the rules.

- [x] **Phase 0** — project setup
- [x] **Phase 1** — collect raw data
- [x] **Phase 2** — build structured data
- [x] **Phase 3** — deterministic tools and validation
- [x] **Phase 4** — LLM wrapper and agent loop
- [x] **Phase 5** — output files
- [x] **Phase 6** — Streamlit UI
- [x] **Phase 7** — testing, test log, deploy *(all but the deploy itself)*

### What needs a human

`data/VERIFY.pdf` — 17 pages, built by `python scripts/make_verify_pdf.py`
from `data/VERIFY.md` — is the pack for the one job no test can do: checking a
program against its official PDF, one tick box per rule, with the rows worth a
second look shaded. That check came back on **2026-11-09** for all five
programs in the pack, so `COMP`, `MATH-AM`, `FINA`, `GCS-SS` and `IDT` are
tier `verified` and carry that date in `verified_on`. The other 92 readable
programs are `auto_extracted` and show the amber badge; to build a pack for
any of them, run `python pipeline/check_program.py --verify CODE …` and then
`python scripts/make_verify_pdf.py`.

Two jobs are still open: the deploy, and looking at the app on a phone.

### Checked by eye, not by test

`tests/test_app.py` drives the real Streamlit widgets headlessly, so the
flow, the refusals and the session limits are tested. **Phone width is not**:
a headless screenshot of a Streamlit page never settles before the capture,
so the layout at 390px has to be looked at. The app uses a single centred
column and full-width buttons, which is the layout that survives a phone, but
that is a design choice rather than a verified result — open the deployed
link on a phone to confirm it.

Scope for now: the **2026-27 intake cohort**. Dual degree programmes are marked
unsupported. The agent does not predict grades, does not save plans server-side
and does not scrape any site that disallows it.
