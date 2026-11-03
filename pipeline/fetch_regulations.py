"""Download HKUST regulations into raw/regulations/ (Phase 1, task 4).

Hard rule 11: every regulation a validator relies on must come from an official
source recorded in data/regulations.json with its URL. This script saves the
pages; Phase 2 Part C extracts the values with a source_quote for each. Where a
value is not stated in any page found here, it goes in GAPS.md and the matching
validator warns "verify" rather than inventing a threshold.

Sources
  academic-regulations-governing-ug-studies-2026-27
      The Academic Regulations for this cohort. Confirmed to contain:
        AR 3.7  additional major: at least 20 single-counted credits
        AR 4.1  at least 120 credits for a bachelor's degree, subject to AR 6.3
        AR 5    minimum 12 and maximum 18 credits per Regular Term
        AR 6.1  three transfer types, incl. "credit-only transfer" (the
                "unspecified credits" case in the intake form)
        AR 6.3  minimum HKUST credits, i.e. the cap on transferred credits
        Glossary: the four academic terms (Fall, Winter, Spring, Summer)
  credit-transfer-undergraduate-studies-ug
      The Academic Registry's credit transfer and advanced standing page.
  cle.hkust.edu.hk/courses
      University English Language Requirement, linked from every program page.
  legal.hkust.edu.hk/legal-education-course
      University Legal Education Requirement, likewise.

Not fetched: the class schedule (w5.ab.ust.hk/wcq) sets Disallow: / — see
raw/SOURCES.md. Term offerings therefore have no data source (hard rule 7).

Usage:
    python pipeline/fetch_regulations.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402

from pipeline.fetcher import RAW, Fetcher, _utf8_stdout, render_sources  # noqa: E402

DEST = RAW / "regulations"
REG = "https://registry.hkust.edu.hk/resource-library"

SOURCES = [
    (f"{REG}/academic-regulations-governing-ug-studies-2026-27",
     "academic_regulations_ug_2026-27.html",
     "Academic Regulations Governing UG Studies, 2026-27 (credit load, "
     "graduation, credit transfer)"),
    (f"{REG}/credit-transfer-undergraduate-studies-ug",
     "credit_transfer_ug.html",
     "Credit transfer and advanced standing for UG studies"),
    ("https://cle.hkust.edu.hk/courses",
     "english_language_requirement.html",
     "University English Language Requirement"),
    ("https://legal.hkust.edu.hk/legal-education-course",
     "legal_education_requirement.html",
     "University Legal Education Requirement"),
]

# What Phase 2 Part C must fill in regulations.json, and whether a source for
# it was located in Phase 1. Anything False is a TODO for the developer, not a
# number to guess.
NEEDED = [
    ("min credits per Regular Term", True,
     "AR 5 — \"a mimimum of 12 credits and a maximum of 18 credits\" "
     "(the typo is in the source)"),
    ("max credits per Regular Term", True, "AR 5 — same sentence"),
    ("graduation total", True, "AR 4.1 — \"Earn at least 120 credits\""),
    ("transfer credit cap / minimum HKUST credits", True, "AR 6.3 — Minimum HKUST Credits"),
    ("credit-only (unspecified) transfer is a recognised type", True, "AR 6.1 (ii)"),
    ("additional-major single-counted credits", True, "AR 3.7 — at least 20"),
    ("minor total credits", True, "AR — \"All Minors require ... at least 18 credits\""),
    ("extended major total credits", True, "AR — \"at least 21 credits\""),
    ("overload above the maximum: who approves, what limit", False,
     "AR 5 gives the 12-18 range but no overload procedure was found"),
    ("Summer / Winter term credit limits", False,
     "AR 5's range applies to Regular Terms; Winter and Summer are not Regular "
     "Terms and no separate limit was found"),
    ("double-count cap between Major / Minor / Common Core", False,
     "not stated in the AR; may be per-program in the requirement PDFs, or in "
     "minor-program rules"),
    ("exchange / outgoing study credit transfer rules", False,
     "AR 6 covers transfer generally; no outgoing-exchange-specific rule found"),
    ("Final Year Project duration (must it span two terms?)", False,
     "not in the AR; likely per-program in the requirement PDFs"),
]


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)

    with Fetcher(delay=args.delay) as f:
        print("Regulations")
        for url, name, note in SOURCES:
            f.save(url, DEST / name, area="regulations", note=note, expect="text/html")

        # Report which of the needed facts appear in the AR text, as a sanity
        # check that the page saved is the one that matters.
        ar = DEST / "academic_regulations_ug_2026-27.html"
        if ar.exists():
            soup = BeautifulSoup(ar.read_text(encoding="utf-8", errors="replace"), "lxml")
            for junk in soup(["script", "style", "nav", "footer", "header"]):
                junk.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            print(f"\n  AR text: {len(text):,} characters")
            # NB "mimimum" is spelled that way in the source page.
            for probe in ["12 credits and a maximum of 18 credits",
                          "at least 120 credits", "6.3 Minimum HKUST Credits",
                          "credit-only transfer", "20 single-counted credits"]:
                print(f"    {'found' if probe.lower() in text.lower() else 'MISSING':8} {probe!r}")

        gaps = ["# Regulation gaps\n",
                "What `data/regulations.json` needs (Phase 2 Part C), and whether Phase 1",
                "found an official source for it. **A missing value stays `null`** and the",
                "validator that would use it warns \"verify\" — hard rule 11 forbids",
                "inventing a threshold.\n",
                "| Needed value | Source found | Where / why not |",
                "|---|---|---|"]
        for label, ok, where in NEEDED:
            gaps.append(f"| {label} | {'yes' if ok else '**no**'} | {where} |")
        gaps += [
            "",
            "## For the developer",
            "",
            "The four `no` rows need either a URL I did not find or a manual download:",
            "",
            "1. **Summer / Winter credit limits** — AR 5's 12-18 range is written for",
            "   *Regular Terms*. Summer and Winter are separate terms in the AR glossary,",
            "   so a student taking summer courses has no sourced limit yet.",
            "2. **Double-count cap (Major / Minor / Common Core)** — the plan's",
            "   `allocate.py` needs this, and `Program.max_double_count_credits` exists",
            "   for it. The AR only states the additional-major rule (20 single-counted",
            "   credits). It may be stated per-program in the requirement PDFs, which",
            "   Phase 2 will see.",
            "3. **Outgoing exchange credit rules** — AR 6 covers credit transfer in",
            "   general. If the Study Abroad office publishes specific rules, add the URL.",
            "4. **FYP duration** — whether a Final Year Project must span two terms is",
            "   probably per-program; Phase 2 should pick it up from each PDF.",
            "",
            "Until then `check_load` (summer), `allocate` (cap), `check_exchange` and",
            "`check_fyp` emit \"verify\" warnings instead of hard errors.",
            "",
        ]
        (DEST / "GAPS.md").write_text("\n".join(gaps), encoding="utf-8")
        print(f"\n  wrote raw/regulations/GAPS.md "
              f"({sum(1 for _, ok, _ in NEEDED if not ok)} gaps)")

        render_sources()
        f.report("Regulations")


if __name__ == "__main__":
    main()
