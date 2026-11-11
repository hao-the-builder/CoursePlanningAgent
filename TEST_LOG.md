# Test log

## What was run

513 automated tests, plus 16 student profiles through `scripts/run_eval.py`,
each judged against an expectation written into the profile before the run:
16 of 16 matched. The profiles cover a correct four-year plan, a prerequisite
out of order, an overloaded term, an invented course, a double-count overflow,
front- and back-loading, a free final term, an exchange term, 24 transfer
credits, a minor, a missing cohort, an unsupported major, an out-of-scope
request and a prompt injection.

The released Dify workflow was then run end to end against the live tool
service, and its two Python nodes were executed directly against that service
so the published code is what was measured.

## What broke

**Every tool call returned 401.** Dify did not substitute the token into the
HTTP *header* field. It now travels in the request body, the service accepts
either, and an unsubstituted template is reported as such instead of as a
wrong password.

**The model did not exist.** Dify's Anthropic plugin ships a fixed model list;
every entry in ours — Opus 4, Sonnet 4, Claude 3.5 — has been retired, so the
API answered 404. Fixed by changing provider.

**A Computer Science plan contained four accounting courses.** Free electives
were padded with the alphabetically first eligible courses — 38 of the 120
credits. They are now slots the student fills. The plan was valid throughout,
so no test had caught it; one now asserts that no real course is chosen for
the student.

**Slot credits vanished through the model**, which returns code, term and
status only, reading as a 38-credit shortfall. Each slot now states its size
in its own code. Fixing the slots also exposed a latent crash in the
assistant, which read a field the data model never had, and skewed a
back-loaded plan to 62/58 credits, corrected by moving slots after placement.

## Not fixed

Common Core areas are still filled alphabetically; changing that alters how a
requirement rule is evaluated, which the project's rules say to ask about
first. 4000-level courses can land in Year 1, because the scheduler orders by
prerequisite depth and those courses publish none a machine can read. Only 5
of 129 programs are human-verified and 32 refuse to plan at all. One Common
Core requirement cannot be met from HKUST's published list — reported as a gap
in their data rather than papered over. Term offerings are unknown: the class
schedule disallows automated access, so every plan says to check them.
