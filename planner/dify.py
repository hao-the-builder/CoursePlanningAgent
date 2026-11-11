"""Run the plan through the Dify workflow instead of `planner/agent.py`.

Why this is not another `LLM_BACKEND`. `planner/llm.py` wraps a *chat
primitive*: one question, one answer, with a tool loop around it. Dify does
not expose anything that shape — its Service API runs a whole app server-side
and never hands a tool call back to the caller. So the Dify workflow in
`dify/course-planner.yml` replaces the agent loop, not the model call inside
it, and that makes it a sibling of `planner/agent.py` rather than a backend
underneath it.

What stays on this side of the wire, by design:

  * **The data.** The workflow reaches `service/tool_api.py` for every course
    code, credit, rule and verdict. Nothing about HKUST is uploaded to Dify.
  * **The last word on validity.** `plan_for_dify` re-runs `validate_plan`
    locally on whatever comes back, and reports *that* verdict. The workflow
    validates its own work too — that is how it repairs — but a plan is never
    presented on the strength of a remote check alone (hard rule 2).
  * **The refusal.** An `unsupported` program is refused here before a
    request is sent, as well as by the service if one is sent anyway
    (hard rule 5).

Run it:

    python -m planner.dify tests/profiles/01-comp-correct.json
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv                       # noqa: E402

from planner import tools as T                       # noqa: E402
from planner.intake import StudentProfile            # noqa: E402
from planner.llm import LLMUnavailable               # noqa: E402
from planner.validate import ValidationReport, validate_plan   # noqa: E402
from schema import PlannedCourse                      # noqa: E402

load_dotenv()          # DIFY_API_KEY, DIFY_BASE_URL, TOOL_API_BASE, TOOL_API_TOKEN

CLOUD = "https://api.dify.ai/v1"
TIMEOUT = 300.0


@dataclass
class DifyResult:
    """What came back, and what this side makes of it."""

    plan: list[PlannedCourse] = field(default_factory=list)
    report: ValidationReport | None = None
    rationale: str = ""
    program: dict = field(default_factory=dict)
    remote_ok: bool | None = None       # the workflow's own verdict
    raw: dict = field(default_factory=dict)
    workflow_run_id: str = ""
    elapsed: float | None = None
    tokens: int | None = None

    @property
    def ok(self) -> bool:
        """The local verdict. The only one that decides anything."""
        return self.report is not None and self.report.ok

    @property
    def agreed(self) -> bool:
        """Whether Dify's verdict matched the one computed here.

        A disagreement is not a tie to break — the local report wins — but it
        means the workflow is talking to a different tool service, or an older
        copy of the data, and that is worth saying out loud.
        """
        return self.remote_ok is None or self.remote_ok == self.ok


def settings() -> tuple[str, str]:
    """The base URL and app key, from the environment (hard rule 8)."""
    key = os.environ.get("DIFY_API_KEY", "").strip()
    if not key:
        raise LLMUnavailable(
            "DIFY_API_KEY is not set. Create the app in Dify by importing "
            "dify/course-planner.yml, then copy its API key from "
            "`API Access` into .env (locally) or Streamlit secrets "
            "(deployed) — never into git.")
    base = os.environ.get("DIFY_BASE_URL", "").strip() or CLOUD
    return base.rstrip("/"), key


def tool_endpoint() -> tuple[str, str]:
    """Where the workflow should reach this repo's tool service.

    Dify calls it, not us, so these are the values Dify needs rather than the
    ones we would use ourselves: a self-hosted Dify in Docker reaches the
    host as `host.docker.internal`, and Dify Cloud needs a public URL.
    """
    token = os.environ.get("TOOL_API_TOKEN", "").strip()
    if not token:
        raise LLMUnavailable(
            "TOOL_API_TOKEN is not set. The Dify workflow authenticates to "
            "service/tool_api.py with it, so both sides need the same value. "
            "Generate one with:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    base = (os.environ.get("TOOL_API_BASE", "").strip()
            or "http://host.docker.internal:8601")
    return base.rstrip("/"), token


# How the workflow's `free_terms` dropdown spells each choice. The form offers
# a fixed list because a reviewer cannot be asked to type a term label, and a
# profile that wants some other term has no option to carry it - so the choice
# is made plain here rather than silently dropped.
FREE_TERM_CHOICES = {
    (): "none",
    ("Y4 Spring",): "Y4 Spring",
    ("Y4 Fall", "Y4 Spring"): "Y4 Fall and Y4 Spring",
}


def free_terms_choice(profile: StudentProfile) -> str:
    """The dropdown option matching this profile's free terms."""
    wanted = tuple(sorted(profile.free_terms, reverse=True))
    for terms, label in FREE_TERM_CHOICES.items():
        if tuple(sorted(terms, reverse=True)) == wanted:
            return label
    raise ValueError(
        f"the Dify form offers no option for free terms {list(profile.free_terms)}. "
        f"It offers {sorted(FREE_TERM_CHOICES.values())}. Run this profile "
        f"through `planner.agent` instead, or add the option to the Start node "
        f"and to FREE_TERM_CHOICES.")


def inputs_for(profile: StudentProfile) -> dict[str, str]:
    """The Start-node variables, as the DSL declares them.

    The workflow asks a person questions and assembles the profile itself, so
    this sends the same answers a reviewer would pick from the form rather
    than the profile JSON. Keeping to one path means a run from here exercises
    what a reviewer exercises, including the node that does the assembling.
    """
    base, token = tool_endpoint()
    return {
        "major": profile.major or "",
        "cohort": profile.cohort or "",
        "workload_min": str(profile.workload_min),
        "workload_max": str(profile.workload_max),
        "spread": profile.spread or "even",
        "free_terms": free_terms_choice(profile),
        "tool_base": base,
        "tool_token": token,
    }


def run_workflow(profile: StudentProfile, *, user: str = "course-planner",
                 client: Any | None = None) -> dict:
    """POST /workflows/run, blocking, and return the parsed body."""
    import httpx

    base, key = settings()
    payload = {"inputs": inputs_for(profile), "response_mode": "blocking",
               "user": user}
    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT)
    try:
        reply = http.post(f"{base}/workflows/run", json=payload,
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"})
    except Exception as exc:                       # network, DNS, timeout
        raise LLMUnavailable(f"Dify at {base} could not be reached: {exc}"
                             ) from exc
    finally:
        if owned:
            http.close()

    if reply.status_code != 200:
        raise LLMUnavailable(
            f"Dify answered {reply.status_code} for POST {base}/workflows/run: "
            f"{reply.text[:400]}")
    try:
        return reply.json()
    except Exception as exc:
        raise LLMUnavailable(f"Dify's reply was not JSON: {exc}") from exc


def read_result(body: dict) -> dict:
    """The workflow's single `result` output, parsed.

    The DSL ends in one End node with one output, so this is the whole
    contract between the two sides. A failed or stopped run is reported as
    such rather than mined for a partial plan.
    """
    data = body.get("data") or {}
    status = data.get("status")
    if status and status not in ("succeeded", "partial-succeeded"):
        raise LLMUnavailable(
            f"the Dify run ended `{status}`"
            + (f": {data['error']}" if data.get("error") else ""))
    outputs = data.get("outputs") or {}
    if "result" not in outputs:
        raise LLMUnavailable(
            f"the workflow returned no `result` output (got "
            f"{sorted(outputs) or 'nothing'}). The End node in "
            f"dify/course-planner.yml outputs one variable called `result`.")
    raw = outputs["result"]
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception as exc:
        raise LLMUnavailable(f"`result` was not JSON: {exc}") from exc


def plan_for_dify(profile: StudentProfile, *, user: str = "course-planner",
                  client: Any | None = None) -> DifyResult:
    """Ask Dify for a plan, then judge it here."""
    if not profile.cohort or not profile.major:
        missing = [name for name, value in (("cohort", profile.cohort),
                                            ("major", profile.major))
                   if not value]
        raise LLMUnavailable(
            f"missing required input: {', '.join(missing)}. The agent asks "
            f"rather than guessing (hard rule 4).")

    major = T.get_program(profile.major)
    if major.tier.value == "unsupported":
        raise LLMUnavailable(
            f"{major.code} — {major.title} is tier `unsupported`: its "
            f"requirements could not be read reliably, so it cannot be "
            f"planned yet and no plan will be produced for it.")

    body = run_workflow(profile, user=user, client=client)
    result = read_result(body)
    data = body.get("data") or {}

    rows = [PlannedCourse.model_validate(row)
            for row in (result.get("plan") or [])
            if isinstance(row, dict)]
    if not rows:
        raise LLMUnavailable("the workflow returned an empty plan")

    # The verdict that counts is computed here, over this repo's data.
    report = validate_plan(rows, profile, major=major,
                           minor=T.get_program(profile.minor)
                           if profile.minor else None)

    return DifyResult(
        plan=rows, report=report,
        rationale=str(result.get("rationale") or ""),
        program=result.get("program") or {},
        remote_ok=(result.get("validation") or {}).get("ok"),
        raw=result,
        workflow_run_id=str(body.get("workflow_run_id") or ""),
        elapsed=data.get("elapsed_time"), tokens=data.get("total_tokens"))


# ------------------------------------------------------------------ CLI --

def main(argv: list[str] | None = None) -> int:
    import argparse

    from planner.agent import load_profile

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("profile", type=Path, help="a tests/profiles/*.json file")
    ap.add_argument("--user", default="course-planner")
    args = ap.parse_args(argv)

    try:
        result = plan_for_dify(load_profile(args.profile), user=args.user)
    except LLMUnavailable as exc:
        print(f"cannot run: {exc}")
        return 1

    report = result.report
    print(f"run {result.workflow_run_id or '?'} · {len(result.plan)} rows · "
          f"{result.elapsed or '?'}s · {result.tokens or '?'} tokens")
    print(f"local verdict: {'ok' if result.ok else 'NOT ok'} — "
          f"{len(report.errors)} errors, {len(report.warnings)} warnings")
    if not result.agreed:
        print(f"!! Dify reported ok={result.remote_ok} and this side "
              f"computed ok={result.ok}. The workflow is reading different "
              f"data — check TOOL_API_BASE points at this repo's service.")
    for issue in report.errors[:10]:
        print(f"  error: {issue}")
    if result.rationale:
        print(f"\n{result.rationale}")
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
