"""Run every test profile through the agent and write the eval report.

    python scripts/run_eval.py                 # the stub backend, free
    python scripts/run_eval.py --backend subscription
    python scripts/run_eval.py --only 16 17    # just these

Writes `logs/eval_report.md`: one row per profile with the outcome, the
blocking errors, the warnings, the iterations the loop needed, and whether
that matched what the profile says to expect.

Each profile carries its own `expect` block, so the report judges against
something written down in advance rather than against whatever happened:

    status          the outcome the agent must reach
    max_errors      the most blocking errors any path may still have
    require_any     validator checks that must fire
    forbid_checks   checks that must not
    require_question / require_message   wording a refusal must carry
    require_clean_paths  how many paths must validate with no errors
    forbid_course   a course code that must not appear in any plan
    forbid_text     phrasing the prose must not contain
    needs_model     the check is about what the model wrote, so it is
                    reported as "not tested" on the stub backend

Two profiles — the out-of-scope request and the prompt injection — are about
what the model says, not what the code computes. On the stub backend they
are marked "not tested" rather than passed, because a stub that writes no
prose cannot fail them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner.agent import load_profile, plan_for  # noqa: E402
from planner.llm import backend_name  # noqa: E402
from planner.logging import RunLog  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PROFILES = REPO / "tests" / "profiles"
REPORT = REPO / "logs" / "eval_report.md"


@dataclass
class Outcome:
    name: str
    description: str
    status: str = ""
    errors: int = 0
    warnings: int = 0
    iterations: int = 0
    paths: int = 0
    seconds: float = 0.0
    verdict: str = "pass"
    notes: list[str] = field(default_factory=list)
    log: str = ""


def judge(result, expect: dict, backend: str, outcome: Outcome) -> None:
    """Compare what happened with what the profile said to expect."""
    failures: list[str] = []

    wanted = expect.get("status")
    if wanted and result.status != wanted:
        failures.append(f"status was {result.status}, expected {wanted}")

    cap = expect.get("max_errors")
    if cap is not None and outcome.errors > cap:
        failures.append(f"{outcome.errors} blocking errors, at most {cap} "
                        f"allowed")

    clean = sum(1 for path in result.paths if path.ok)
    wanted_clean = expect.get("require_clean_paths")
    if wanted_clean is not None and clean < wanted_clean:
        failures.append(f"{clean} path(s) validated cleanly, "
                        f"{wanted_clean} needed")

    fired = {issue.check for path in result.paths
             for issue in (path.report.issues if path.report else [])}
    for check in expect.get("require_any", []):
        if check not in fired:
            failures.append(f"{check} did not fire")
    for check in expect.get("forbid_checks", []):
        if check in fired:
            failures.append(f"{check} fired and should not have")

    question = expect.get("require_question")
    if question and not any(question in q for q in result.questions):
        failures.append(f"no follow-up question mentioned {question!r}")

    message = expect.get("require_message")
    if message and message not in result.message:
        failures.append(f"the message did not say {message!r}")

    forbidden = expect.get("forbid_course")
    if forbidden and any(row.code == forbidden for path in result.paths
                         for row in path.plan):
        failures.append(f"{forbidden} reached a plan")

    if expect.get("require_warnings") and not any(
            path.report and path.report.warnings for path in result.paths):
        failures.append("no warnings were shown at all")

    prose = " ".join(
        [result.message] +
        [p.summary for p in result.paths] +
        [line for p in result.paths for line in p.why_it_fits + p.trade_offs])
    for phrase in expect.get("forbid_text", []):
        if phrase.lower() in prose.lower():
            failures.append(f"the prose said {phrase!r}")

    if expect.get("needs_model") and backend == "stub":
        outcome.verdict = "not tested"
        outcome.notes.append("this profile tests what the model writes; the "
                             "stub backend writes none, so it is not a pass")
        return

    outcome.verdict = "pass" if not failures else "FAIL"
    outcome.notes += failures
    if expect.get("note"):
        outcome.notes.append(expect["note"])


def run_one(path: Path, backend: str, paths: int) -> Outcome:
    raw = json.loads(path.read_text(encoding="utf-8"))
    outcome = Outcome(name=path.stem,
                      description=raw.get("description", "").split(".")[0])
    started = time.time()
    try:
        profile = load_profile(path)
        log = RunLog.open(name=f"eval-{path.stem}")
        result = plan_for(profile, paths=paths, log=log)
    except Exception as exc:                          # noqa: BLE001
        outcome.status = "crashed"
        outcome.verdict = "FAIL"
        outcome.notes.append(f"{type(exc).__name__}: {exc}")
        outcome.notes.append(traceback.format_exc().splitlines()[-1])
        outcome.seconds = time.time() - started
        return outcome

    outcome.seconds = time.time() - started
    outcome.status = result.status
    outcome.iterations = result.iterations
    outcome.paths = len(result.paths)
    outcome.errors = sum(len(p.report.errors) for p in result.paths
                         if p.report)
    outcome.warnings = sum(len(p.report.warnings) for p in result.paths
                           if p.report)
    outcome.log = log.path.name
    judge(result, raw.get("expect", {}), backend, outcome)
    return outcome


def write_report(outcomes: list[Outcome], backend: str,
                 destination: Path) -> Path:
    passed = sum(1 for o in outcomes if o.verdict == "pass")
    failed = [o for o in outcomes if o.verdict == "FAIL"]
    untested = [o for o in outcomes if o.verdict == "not tested"]

    lines = [
        "# Eval report",
        "",
        f"`scripts/run_eval.py` · backend `{backend}` · "
        f"{len(outcomes)} profiles · "
        f"{sum(o.seconds for o in outcomes):.0f}s",
        "",
        f"**{passed} pass · {len(failed)} fail · {len(untested)} not tested**",
        "",
        "Each profile is judged against the `expect` block written into it, "
        "not against whatever happened. A profile whose expectation is about "
        "the model's prose is marked *not tested* on the stub backend, "
        "because a stub that writes no prose cannot fail it.",
        "",
        "| Profile | Outcome | Errors | Warnings | Iterations | Paths | "
        "Verdict |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for o in outcomes:
        mark = {"pass": "pass", "FAIL": "**FAIL**",
                "not tested": "_not tested_"}[o.verdict]
        lines.append(f"| `{o.name}` | {o.status} | {o.errors} | {o.warnings} "
                     f"| {o.iterations} | {o.paths} | {mark} |")

    lines += ["", "## What each profile is for", ""]
    for o in outcomes:
        lines.append(f"- **`{o.name}`** — {o.description}.")
        for note in o.notes:
            lines.append(f"  - {note}")

    if failed:
        lines += ["", "## Failures", ""]
        for o in failed:
            lines.append(f"### `{o.name}`")
            lines += [f"- {note}" for note in o.notes]
            lines.append(f"- run log: `logs/runs/{o.log}`")
            lines.append("")

    lines += ["", "## Run logs", "",
              "Every row above has a JSONL log under `logs/runs/`, holding "
              "the profile, the prompt size, each model reply, every "
              "validator result and the final status.", ""]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", help="overrides LLM_BACKEND for this run")
    ap.add_argument("--paths", type=int, default=2)
    ap.add_argument("--only", nargs="*", default=None,
                    help="substrings of the profile names to run")
    ap.add_argument("--out", type=Path, default=REPORT)
    args = ap.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.backend:
        os.environ["LLM_BACKEND"] = args.backend
    backend = backend_name()

    files = sorted(PROFILES.glob("*.json"))
    if args.only:
        files = [f for f in files if any(key in f.stem for key in args.only)]

    print(f"{len(files)} profiles on the {backend} backend\n")
    outcomes = []
    for path in files:
        outcome = run_one(path, backend, args.paths)
        outcomes.append(outcome)
        mark = {"pass": "  ok", "FAIL": "FAIL", "not tested": "  --"}[
            outcome.verdict]
        print(f"{mark}  {outcome.name:28} {outcome.status:12} "
              f"{outcome.errors} err  {outcome.warnings:2} warn  "
              f"{outcome.iterations} iter  {outcome.seconds:5.1f}s")
        for note in outcome.notes:
            print(f"        {note}")

    report = write_report(outcomes, backend, args.out)
    failed = sum(1 for o in outcomes if o.verdict == "FAIL")
    try:
        shown = report.resolve().relative_to(REPO).as_posix()
    except ValueError:
        shown = str(report)
    print(f"\nwrote {shown} — "
          f"{len(outcomes) - failed} of {len(outcomes)} not failing")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
