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
planner/           terms, tools, validation, allocation, intake, agent loop
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
- [ ] **Phase 6** — Streamlit UI
- [ ] **Phase 7** — testing, test log, deploy

Scope for now: the **2026-27 intake cohort**. Dual degree programmes are marked
unsupported. The agent does not predict grades, does not save plans server-side
and does not scrape any site that disallows it.
