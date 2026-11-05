# Test plans

The nine cases Phase 3 asks for. Each file here holds a `profile` and a `plan`;
`tests/expected/{same name}.json` holds what `validate_plan` should say about
it, written from the case's intent rather than copied from a run.

| # | File | What it is for |
|---|---|---|
| 1 | `01-comp-correct.json` | A complete, valid four-year BEng Computer Science plan, 121 credits. Must report **no errors at all**. |
| 2 | `02-prereq-out-of-order.json` | `COMP 2012` sits a year before `COMP 2011`, which it requires. Both are 4 credits, so no term total moves and the prerequisite error stands alone. |
| 3 | `03-overloaded-term.json` | Y2 Fall at 24 credits — over the Academic Regulations' 18 **and** over the 18 the student asked for. Two separate errors, because they are two separate limits. |
| 4 | `04-hallucinated-course.json` | `COMP 9999`. Hard rule 1. |
| 5 | `05-double-count-overflow.json` | A Mathematics minor on a COMP major. COMP already requires 11 credits of MATH; the minor lets 9 count twice. |
| 6 | `06-front-loaded-free-final.json` | Front-loaded with Y4 Spring kept free. Must **pass**, with an info saying the student can graduate early. |
| 7 | `07-exchange-term.json` | Y3 Spring at NUS. One HKUST course left in the term (error) and a requirement met only by three unapproved mappings (warning). |
| 8 | — | The five-year term sequence. It lives in `tests/test_terms.py`, not here: `DECISIONS.md` drops five-year support, so `term_sequence` still generates one but no profile, validator path or output label is built for it. |
| 9 | `09-transfer-credits.json` | 24 transferred credits — 18 mapped to named HKUST courses, 6 credit-only, which may count toward the 120 and nothing else. |

## The five warnings every valid plan carries

Cases 1, 6 and 9 pass, and still report five warnings. None of them is a fault
in the plan; each is something the published data cannot settle, and hard rule
11 says to say "verify" rather than invent an answer.

- **`check_prereqs`** — three prerequisites are public-exam levels
  (`Level 3 in HKDSE English Language`), which no plan can check.
- **`check_exclusions`** — the catalog says `MATH 1013` excludes `MATH 1014`
  while listing `MATH 1013` as `MATH 1014`'s prerequisite. 17 pairs read like
  that, so the clash is reported rather than enforced.
- **`check_offering`** — the class schedule disallows automated access
  (hard rule 7), so no course has been checked against the terms it is
  actually offered in.
- **`check_fyp`** — HKUST publishes no rule on how many terms a final year
  project must span.
- **`check_graduation`** — the Common Core needs 6 credits of HAIC and one
  3-credit HAIC course is published for this cohort, so *no* plan can satisfy
  it. Reported as unmeetable rather than as the plan's fault.
