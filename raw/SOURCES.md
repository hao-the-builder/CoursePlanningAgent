# Sources

Provenance for everything under `raw/`. One row per file: where it came from and
when it was downloaded. Nothing in `raw/` is ever hand-edited — all derived data
goes in `data/`.

Filled in by Phase 1. Empty for now.

## Requirement PDFs — `raw/requirements/`

| File | Program | URL | Downloaded |
|---|---|---|---|
| _(none yet)_ | | | |

## Course catalog — `raw/catalog/`

| File | Subject | URL | Downloaded |
|---|---|---|---|
| _(none yet)_ | | | |

## Common Core — `raw/common_core/`

| File | URL | Downloaded |
|---|---|---|
| _(none yet)_ | | |

## Regulations — `raw/regulations/`

Needed for `data/regulations.json`: minimum and maximum credit load per regular
term, overload rules, summer and winter limits, double-counting caps between
Major / Minor / Common Core, credit transfer and advanced standing, exchange
credit transfer, FYP duration, and graduation requirements.

| File | What it covers | URL | Downloaded |
|---|---|---|---|
| _(none yet)_ | | | |

## TODO / blocked

- **Term offerings** — the class schedule site (`w5.ab.ust.hk/wcq`) disallows
  automated access, so it is not scraped. `data/offerings.json` stays empty and
  `check_offering` emits a "verify on the class schedule" warning rather than a
  made-up answer. Needs a manual export if offering data is wanted.
- Any regulation that cannot be found on an official page is listed here for the
  developer. A validator with no sourced threshold warns "verify" — hard rule 11
  forbids inventing one.
