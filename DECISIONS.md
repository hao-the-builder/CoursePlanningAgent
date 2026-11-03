# Decisions

Choices the developer made that `CLAUDE.md` does not already settle, or that
override it. Newest first. Each one names the phase it affects, so a later
phase does not silently contradict a decision taken earlier.

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
