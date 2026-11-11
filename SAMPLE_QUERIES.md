# Five things to try

Scenarios in the order that shows the most for the least clicking. Each is a
run of the published workflow and takes about a minute.

The form asks for six things. Every scenario below gives all six, so nothing
has to be guessed.

> **If the first run is slow or the first step fails, run it once more.** The
> tool service sleeps when nobody has used it for a while and takes up to a
> minute to wake. Opening `/health` on the service first wakes it.

---

## 1 · The thing it is for

| Field | Value |
|---|---|
| Major | `COMP` |
| Intake cohort | `2026-27` |
| Credits per term | `12` to `18` |
| Workload spread | `even` |
| Terms to keep free | `Y4 Spring` |

A complete four-year plan for a Computer Science degree, with the final term
free.

**What to look at.** The total is exactly 120 against the 120 needed. Every
term sits inside 12–18 credits. The header says the data tier is **verified**
and when a human last checked it against the PDF, and the requirements link
goes to the official source. `"Passed every check"` comes from the validator,
not from the model describing its own work.

---

## 2 · Ask for the free term to be paid for earlier

Same as above, but **Workload spread** `front`.

**What to look at.** The first half of the degree now carries more credits
than the second. Nothing else about the request changed — this is the planner
shaping the same 120 credits around a stated preference. Compare the term
table against scenario 1.

---

## 3 · Ask for something impossible

Same as scenario 1, but **Terms to keep free** `Y4 Fall and Y4 Spring`.

That leaves six terms to carry a 120-credit degree, which needs 20 credits a
term against an 18-credit cap in HKUST's Academic Regulations. No arrangement
of courses can satisfy it.

**What to look at.** The result says the plan breaks twelve rules and lists
every one, with the regulation's own URL, *above* the plan rather than below
it. It does not quietly drop a term, trim the degree, or present the plan as
though it passed. **This is the scenario worth your time**: a plan that cannot
exist is the hardest thing for a planner to admit, and it is the one property
you cannot check by reading a successful output.

---

## 4 · Ask for a degree it cannot plan

Same as scenario 1, but **Major** `MATH`.

**What to look at.** The run stops at the drafting step and says the program's
requirements could not be read reliably, so no plan will be produced for it.
32 of the 129 programs are in this state. The alternative — planning anyway
from half-parsed rules — would produce something that looks exactly as
confident as scenario 1.

---

## 5 · Read what it refuses to be sure about

Any successful run, at the bottom.

**What to look at.** Nine things to verify, each naming what could not be
checked and why:

- **No course was checked against the terms it is offered in.** HKUST's class
  schedule disallows automated access, so that data does not exist here.
- **One Common Core requirement cannot be met by any plan** — the courses
  HKUST publishes for this cohort do not add up to it. That is a gap in their
  data, and it is reported as one rather than hidden.
- **Prerequisites written for a person**, like "Level 3 or above in HKDSE
  Mathematics Extended Module M1", which no validator can confirm for you.
- **Two catalog entries that contradict each other**, where a course excludes
  another that is also its own prerequisite.

Each plan also carries a line telling you to check it with an academic
advisor. Nothing here is endorsed by HKUST.

---

## What is doing the work

Course codes, credits, prerequisites, requirement rules, credit totals and
every check come from a read-only service over HTTP, reading data extracted
from HKUST's official PDFs. The model reorders a plan the code has already
built and explains it. A plan is validated before it is returned and
re-validated afterwards, so a plan that breaks a rule cannot be presented as
if it passed — scenario 3 is that mechanism firing.

Rows reading **Free elective** are choices left to you on purpose. The
requirements say only "enough credits to reach 120", so the planner states the
size of each gap rather than picking a course on your behalf.
