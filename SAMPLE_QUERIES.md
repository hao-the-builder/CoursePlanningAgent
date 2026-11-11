# Five things to try

For the prototype link. Each takes about a minute, and they are ordered so the
most informative comes first. Every setting is given, so nothing needs
guessing.

Two things to know before you start:

- **The hosted link runs with no language model configured.** Every plan,
  credit total and requirement check is deterministic Python over data taken
  from HKUST's published PDFs, which is all of the planning. What is missing is
  the written explanation, and the app says so where that text would be. The
  agentic version — a Dify workflow that adds a model's reasoning on top of
  the same tools — is submitted as a file; `dify/SETUP.md` runs it.
- **Rows reading "Free elective" are choices left to you on purpose.** The
  requirements say only "enough credits to reach 120", so the planner states
  the size of each gap rather than picking a course on your behalf.

---

## 1 · The thing it is for

| Setting | Value |
|---|---|
| Intake cohort | `2026-27` |
| Major | `COMP — BEng in Computer Science` |
| Credits per term | `12` to `18` |
| Workload shape | **Even across the degree** |

Press **Plan my degree**.

**What to look at.** Two or three complete four-year plans, each totalling 120
credits with every term inside 12–18. Each path shows its credits per term and
its validation result. Near the top is the **data tier** and the date a human
last checked those requirements against the PDF. At the bottom, an `.xlsx` per
path and one `.docx` covering all of them — the spreadsheet's totals are Excel
formulas, so you can edit the plan and watch the progress figures follow.

---

## 2 · Front-load it, and keep the final term free

As above, then change two things:

| Setting | Value |
|---|---|
| Workload shape | **Front-loaded — free up later years** |
| Terms to keep free | `Y4 Spring` |

**What to look at.** The first half of the degree now carries more credits than
the second, and Y4 Spring appears as a block with no courses and a zero total
rather than being quietly dropped. Same 120 credits, same requirements, a
different shape — the constraints are satisfied, not weighed up.

---

## 3 · Ask for something impossible

As scenario 2, but set **Terms to keep free** to **both** `Y4 Fall` *and*
`Y4 Spring`.

That leaves six terms to carry a 120-credit degree, which needs 20 credits a
term against the 18-credit cap in HKUST's Academic Regulations. No arrangement
of courses can satisfy it.

**What to look at.** The plan comes back with its failures named — each
overloaded term, with the regulation's own URL — in the Progress sheet's
*Things to check* and in the document. It does not quietly drop a term, trim
the degree, or present the result as though it passed.

**This is the scenario worth your time.** A plan that cannot exist is the
hardest thing for a planner to admit, and it is the one property you cannot
verify by reading a successful output.

---

## 4 · Ask for a degree it cannot plan

Set **Major** to `MATH — BSc in Mathematics`.

**What to look at.** It says plainly that this program's requirements could not
be read reliably enough to plan, and produces nothing. 32 of the 129 programs
are in that state, and 92 more are machine-extracted but unverified — the tier
badge in scenario 1 is what tells them apart. Planning anyway from
half-parsed rules would produce something that looks exactly as confident as
scenario 1 does.

---

## 5 · See how exchange credits are treated

Back to scenario 1, then tick **I want to go on exchange**, choose a term such
as `Y3 Spring`, and pick what you would use it for.

**What to look at.** The exchange term is filled with rows marked as pending
rather than real HKUST courses, because which host course maps to which
requirement is the university's decision and not ours. Any requirement that
would only be met by those credits shows as needing approval — never as met.
The credit totals hold exchange credits separately for the same reason.

---

## What is doing the work

Course codes, credits, prerequisites, exclusions, requirement rules, credit
totals and every check are deterministic Python over structured data extracted
from HKUST's official PDFs. Numbers in the spreadsheet are Excel formulas
written by that code, never arithmetic done by a model. A language model's only
job in the full system is to choose between options the data allows and explain
the result, and a plan is validated before it is shown and again afterwards.

Every plan carries its data tier and a line telling you to check it with an
academic advisor. Nothing here is endorsed by HKUST.
