# Regulation gaps

What `data/regulations.json` needs (Phase 2 Part C), and whether Phase 1
found an official source for it. **A missing value stays `null`** and the
validator that would use it warns "verify" — hard rule 11 forbids
inventing a threshold.

| Needed value | Source found | Where / why not |
|---|---|---|
| min credits per Regular Term | yes | AR 5 — "a mimimum of 12 credits and a maximum of 18 credits" (the typo is in the source) |
| max credits per Regular Term | yes | AR 5 — same sentence |
| graduation total | yes | AR 4.1 — "Earn at least 120 credits" |
| transfer credit cap / minimum HKUST credits | yes | AR 6.3 — Minimum HKUST Credits |
| credit-only (unspecified) transfer is a recognised type | yes | AR 6.1 (ii) |
| additional-major single-counted credits | yes | AR 3.7 — at least 20 |
| minor total credits | yes | AR — "All Minors require ... at least 18 credits" |
| extended major total credits | yes | AR — "at least 21 credits" |
| overload above the maximum: who approves, what limit | **no** | AR 5 gives the 12-18 range but no overload procedure was found |
| Summer / Winter term credit limits | **no** | AR 5's range applies to Regular Terms; Winter and Summer are not Regular Terms and no separate limit was found |
| double-count cap between Major / Minor / Common Core | **no** | not stated in the AR; may be per-program in the requirement PDFs, or in minor-program rules |
| exchange / outgoing study credit transfer rules | **no** | AR 6 covers transfer generally; no outgoing-exchange-specific rule found |
| Final Year Project duration (must it span two terms?) | **no** | not in the AR; likely per-program in the requirement PDFs |

## For the developer

The four `no` rows need either a URL I did not find or a manual download:

1. **Summer / Winter credit limits** — AR 5's 12-18 range is written for
   *Regular Terms*. Summer and Winter are separate terms in the AR glossary,
   so a student taking summer courses has no sourced limit yet.
2. **Double-count cap (Major / Minor / Common Core)** — the plan's
   `allocate.py` needs this, and `Program.max_double_count_credits` exists
   for it. The AR only states the additional-major rule (20 single-counted
   credits). It may be stated per-program in the requirement PDFs, which
   Phase 2 will see.
3. **Outgoing exchange credit rules** — AR 6 covers credit transfer in
   general. If the Study Abroad office publishes specific rules, add the URL.
4. **FYP duration** — whether a Final Year Project must span two terms is
   probably per-program; Phase 2 should pick it up from each PDF.

Until then `check_load` (summer), `allocate` (cap), `check_exchange` and
`check_fyp` emit "verify" warnings instead of hard errors.
