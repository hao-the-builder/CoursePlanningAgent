# Test log

*Draft, written from `logs/eval_report.md` and `logs/eval_report_model.md`.
Edit freely — nothing here is from memory, and no result is claimed that a
run did not produce.*

## What was run

Sixteen student profiles through `scripts/run_eval.py`, each judged against
an `expect` block written into the profile before the run. Fourteen ran on
the stub backend — no model, so the agent loop, the validator and the output
files are exercised for free. The two that turn on what the model *writes*
ran on `LLM_BACKEND=subscription` against Claude Opus 5.5.

**Result: 16 of 16 matched their expectation.** On the stub, 14 pass and 2
are recorded as *not tested* rather than passed, because a stub that writes
no prose cannot fail a prose check. Those two pass on the real backend.

The profiles cover a correct four-year plan, a prerequisite out of order, an
overloaded term, a hallucinated course, a double-count overflow, front- and
back-loading, a free final term, an exchange term, 24 transfer credits
including 6 unspecified, a minor, a missing cohort, an unsupported major, an
out-of-scope request and a prompt injection.

## What broke, and what fixed it

The first real run came back 30 credits short on every path. Three causes,
all found by reading the run log rather than guessing:

- **Retries carried no plan.** Each backend call is a fresh conversation, so
  "fix these errors" reached a model that could no longer see what it was
  fixing. Four of five iterations achieved nothing. The retry now sends the
  previous answer back.
- **The prompt never described the Common Core**, so Broadening came back
  unmet every time. It had never been given the rule.
- **The prompt never stated the 120-credit total** or that ~15 credits are
  free electives the model must still place.

After those, the same profile returned two valid paths in two iterations.

The deterministic draft planner needed four fixes of its own, each found by
a failing profile: an exchange term was being left empty rather than filled,
so an exchange plus a free final term looked impossible; a term that could
not reach the 12-credit minimum is now emptied rather than under-loaded, and
the student finishes early; an every-term course could be moved out of a
term by the rebalancer; and unplaceable courses were dumped into whichever
term was emptiest, prerequisites be damned.

## What is still wrong

- **`06-front-loaded-free-final` on the stub.** The front-loaded variant
  lands 3 credits over the cap in one term: the greedy draft fills early
  terms with free electives and starves a late prerequisite chain of room.
  A model fixes it in the retry loop; the stub cannot. One clean path is the
  bar for that profile, and the report says so.
- **Every valid plan carries nine or more warnings**, none of them the
  plan's fault. The catalog contradicts itself on 17 course pairs
  (`MATH 1013` excludes `MATH 1014` while being its prerequisite); the
  Common Core requires 6 credits of HAIC when one 3-credit HAIC course is
  published; the class schedule disallows scraping so no course is checked
  against the terms it is offered in; and HKUST publishes no rule on
  final-year-project duration. Each is reported rather than papered over.
- **Nothing is tier `verified`.** 97 of 129 programs are `auto_extracted`
  and 32 `unsupported`. `data/VERIFY.md` and `data/VERIFY.pdf` are written and
  waiting on a human check. The first round of that check came back on three
  programs: both reported errors turned out to be correct extractions, and
  re-reading the PDFs to prove it found two real bugs the check had passed
  over (an elective list truncated at an "Any SUBJ courses" row, and the seven
  GCS research options missing the track they are taken within). Fixing the
  second is what moved seven programs to `unsupported`: they had been
  plannable only because 24 credits of requirements were missing.
- **A test suite that called the real model.** `tests/test_app.py` sets the
  stub backend with a function-scoped `monkeypatch`, but its module-scoped
  fixture is built first, so once a developer `.env` existed the full run
  planned a degree against the subscription backend and timed out after five
  minutes — 61 errors and 15 minutes for a suite that takes 46 seconds.
  `tests/conftest.py` now pins `LLM_BACKEND=stub` at collection time.
- **Phone width is not tested.** A headless screenshot of a Streamlit page
  never settles before the capture, so the 390px layout needs a human eye.

## Cost

The two model runs cost about **$1.25** each on Claude Opus 5.5 (two
iterations, roughly 50 and 28 tool turns). The stub runs are free, which is
why they are the default.
