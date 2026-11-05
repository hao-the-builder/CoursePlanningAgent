"""The agent loop (Phase 4).

    python -m planner.agent tests/profiles/01-comp-correct.json

Turns a StudentProfile into 2-3 validated paths:

  1. a required field missing -> ask for it and stop (hard rule 4);
  2. an unsupported program -> say so and stop, with no plan (hard rule 5);
  3. the model drafts the paths, using the deterministic tools for every fact;
  4. every path goes through validate_plan;
  5. blocking errors go back to the model to fix, at most `--max-iterations`
     times;
  6. whatever survives is returned together with its report, unresolved
     errors included (hard rule 2 — a plan is never shown as clean when it
     is not).

Every step is written to `logs/runs/{timestamp}.jsonl` as it happens.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path as FilePath
from typing import Any, Literal

if __package__ in (None, ""):
    sys.path.insert(0, str(FilePath(__file__).resolve().parent.parent))

from planner import tools as T  # noqa: E402
from planner.intake import StudentProfile, follow_up_questions, missing_required  # noqa: E402
from planner.llm import LLMUnavailable, Reply, ToolSpec, chat, prompt_text  # noqa: E402
from planner.logging import RunLog  # noqa: E402
from planner.terms import sort_key, term_sequence  # noqa: E402
from planner.validate import ValidationReport, validate_plan  # noqa: E402
from schema import (  # noqa: E402
    ChooseN,
    CommonCoreArea,
    CreditsFrom,
    EveryTerm,
    NAreas,
    OneOf,
    PlannedCourse,
    Program,
    Required,
    Tier,
)

Status = Literal["ok", "needs_input", "unsupported", "failed"]
DEFAULT_PATHS = 3
DEFAULT_ITERATIONS = 5

TIER_NOTE = {
    Tier.VERIFIED: "checked by hand against the official PDF",
    Tier.AUTO: "read automatically from the official PDF and auto-checked, "
               "but not yet verified by a person",
    Tier.UNSUPPORTED: "could not be read reliably",
}


@dataclass
class Path:
    """One proposed route through the degree."""

    name: str
    summary: str = ""
    why_it_fits: list[str] = field(default_factory=list)
    trade_offs: list[str] = field(default_factory=list)
    plan: list[PlannedCourse] = field(default_factory=list)
    slot_suggestions: dict[str, list[str]] = field(default_factory=dict)
    report: ValidationReport | None = None

    @property
    def ok(self) -> bool:
        return self.report is not None and self.report.ok


@dataclass
class AgentResult:
    status: Status
    message: str = ""
    paths: list[Path] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    iterations: int = 0
    log_path: FilePath | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# ------------------------------------------------------- describing data --

def describe_rule(rule, catalog) -> str:
    def title(code: str) -> str:
        course = catalog.get(code)
        return f"{code} ({course.credits:g} cr)" if course else code

    if isinstance(rule, Required):
        return "take " + ", ".join(title(c) for c in rule.courses)
    if isinstance(rule, OneOf):
        return "take one of " + " | ".join(
            " + ".join(title(c) for c in option) for option in rule.options[:8])
    if isinstance(rule, ChooseN):
        return (f"take {rule.n} of: "
                + ", ".join(rule.courses[:25])
                + (" ..." if len(rule.courses) > 25 else ""))
    if isinstance(rule, CreditsFrom):
        return (f"at least {rule.min_credits:g} credits from "
                + ", ".join(rule.patterns[:25])
                + (" ..." if len(rule.patterns) > 25 else ""))
    if isinstance(rule, CommonCoreArea):
        return f"at least {rule.min_credits:g} credits in Common Core area {rule.area}"
    if isinstance(rule, NAreas):
        return (f"at least {rule.min_credits:g} credits over {rule.n_areas} "
                f"different areas of " + ", ".join(rule.areas))
    if isinstance(rule, EveryTerm):
        return f"take {rule.course} in every Regular Term in residence"
    return str(rule)


def describe_program(program: Program, catalog) -> str:
    lines = []
    for group in program.groups:
        lines.append(f"### {group.name} ({group.category.value})")
        for rule in group.rules:
            lines.append(f"- {describe_rule(rule, catalog)}")
    for caveat in program.caveats:
        lines.append(f"- *Not enforced, tell the student:* {caveat}")
    return "\n".join(lines)


def _group_credits(group, catalog) -> float:
    """Roughly what one group is worth, for the prompt's credit budget."""
    from planner.allocate import group_demand

    return group_demand(group, catalog)


def _all_requirements(major: Program, minor: Program | None,
                      common_core: Program | None, catalog) -> str:
    """Every requirement the student must meet, not just the major's.

    Leaving the Common Core out of the prompt was why early runs came back
    with the Broadening requirement unmet: the model had never been told what
    it was.
    """
    parts = [f"## Major — {major.title} ({major.code})",
             describe_program(major, catalog)]
    if minor is not None:
        parts += [f"\n## Minor — {minor.title} ({minor.code})",
                  describe_program(minor, catalog)]
    if common_core is not None:
        parts += ["\n## University Common Core (every student)",
                  describe_program(common_core, catalog)]
    return "\n".join(parts)


def describe_report(report: ValidationReport) -> str:
    lines = []
    for issue in report.errors:
        lines.append(f"- ERROR [{issue.check}] {issue.message}")
    for issue in report.warnings:
        lines.append(f"- warning [{issue.check}] {issue.message}")
    return "\n".join(lines) or "- nothing to report"


# ------------------------------------------------------------- the tools --

def build_tools(profile: StudentProfile, major: Program,
                minor: Program | None) -> list[ToolSpec]:
    """The only way the model is allowed to learn a fact."""
    catalog = T.catalog()

    def search(args: dict) -> str:
        found = T.search_courses(args.get("query", ""),
                                 subject=args.get("subject"),
                                 level=args.get("level"), limit=30)
        return json.dumps([{"code": c.code, "title": c.title,
                            "credits": c.credits,
                            "prerequisite": c.prereq_expr,
                            "common_core_areas": c.common_core_areas}
                           for c in found], ensure_ascii=False)

    def program(args: dict) -> str:
        found = T.get_program(args["code"])
        return json.dumps({"code": found.code, "title": found.title,
                           "tier": found.tier.value,
                           "requirements": describe_program(found, catalog),
                           "caveats": found.caveats}, ensure_ascii=False)

    def draft(args: dict) -> str:
        rows = T.draft_plan(profile, major, minor,
                            spread=args.get("spread") or profile.spread)
        return json.dumps([r.model_dump(exclude_defaults=True) for r in rows],
                          ensure_ascii=False)

    return [
        ToolSpec(name="draft_plan",
                 description="A complete, feasible plan for this student, "
                             "built by code from the requirement rules. Start "
                             "here, then change what you want to change.",
                 schema={"type": "object",
                         "properties": {"spread": {
                             "type": "string", "enum": ["even", "front", "back"],
                             "description": "How to weight the workload across "
                                            "the degree."}},
                         "required": [], "additionalProperties": False},
                 run=draft),
        ToolSpec(name="search_courses",
                 description="Search the course catalog by keyword. The only "
                             "source of real course codes, titles, credits and "
                             "prerequisites.",
                 schema={"type": "object",
                         "properties": {
                             "query": {"type": "string"},
                             "subject": {"type": "string",
                                         "description": "e.g. COMP, MATH"},
                             "level": {"type": "integer",
                                       "description": "1 to 5"}},
                         "required": ["query"], "additionalProperties": False},
                 run=search),
        ToolSpec(name="get_program",
                 description="The requirements of one program, by its code.",
                 schema={"type": "object",
                         "properties": {"code": {"type": "string"}},
                         "required": ["code"], "additionalProperties": False},
                 run=program),
    ]


# -------------------------------------------------------------- the loop --

def _profile_summary(profile: StudentProfile) -> str:
    bits = []
    if profile.direction:
        bits.append(f"- Direction within the major: {profile.direction}")
    if profile.career_interests:
        bits.append(f"- Career interests: {profile.career_interests}")
    if profile.background:
        bits.append(f"- Background: {profile.background}")
    if profile.gpa_target:
        bits.append(f"- GPA target: {profile.gpa_target:g} (affects workload "
                    f"advice only — never predict a grade)")
    if profile.graduate_early:
        bits.append("- Would like to graduate early if possible")
    if profile.reserve_summer_for_internship:
        bits.append("- Wants summers kept for internships")
    if profile.unspecified_transfer_credits:
        bits.append(f"- {profile.unspecified_transfer_credits:g} transferred "
                    f"credits with no named course; these count as free "
                    f"electives only")
    for note in profile.notes:
        bits.append(f"- {note}")
    return "\n".join(bits) or "- Nothing else was said."


def _term_table(profile: StudentProfile) -> str:
    terms = term_sequence(profile.cohort or "2026-27", profile.programme_years,
                          use_summer=profile.use_summer,
                          use_winter=profile.use_winter)
    return "\n".join(f"- `{t.label}` = {t.calendar}" for t in terms)


def _already_done(profile: StudentProfile) -> str:
    rows = profile.already_taken()
    if not rows:
        return "- Nothing yet; this is a plan from the start of the degree."
    return "\n".join(
        f"- `{r.code}` in `{r.term}`, status `{r.status}`" for r in rows)


def _parse_paths(reply: Reply) -> list[Path]:
    payload = reply.json()
    out: list[Path] = []
    for raw in payload.get("paths", []):
        rows = []
        for row in raw.get("plan", []):
            try:
                rows.append(PlannedCourse.model_validate(row))
            except Exception as exc:                 # noqa: BLE001
                raise ValueError(f"bad plan row {row!r}: {exc}") from exc
        out.append(Path(name=raw.get("name", "Unnamed path"),
                        summary=raw.get("summary", ""),
                        why_it_fits=list(raw.get("why_it_fits", [])),
                        trade_offs=list(raw.get("trade_offs", [])),
                        plan=rows,
                        slot_suggestions=dict(raw.get("slot_suggestions", {}))))
    if not out:
        raise ValueError("the reply contained no paths")
    return out


def plan_for(profile: StudentProfile, *, paths: int = DEFAULT_PATHS,
             max_iterations: int = DEFAULT_ITERATIONS,
             log: RunLog | None = None) -> AgentResult:
    """Run the loop. Never raises for an expected outcome; returns a status."""
    log = log or RunLog.open()
    log.event("profile", profile=profile.model_dump(mode="json"))

    missing = missing_required(profile)
    if missing:
        questions = follow_up_questions(profile)
        log.event("needs_input", missing=missing, questions=questions)
        return AgentResult(status="needs_input", questions=questions,
                           message="I need a little more before I can plan.",
                           log_path=log.path)

    ceiling = T.regulation("max_credits_regular_term")
    if ceiling and profile.workload_min > ceiling:
        message = (
            f"You asked for at least {profile.workload_min:g} credits a term, "
            f"but the Academic Regulations cap a Regular Term at {ceiling:g} "
            f"without the Dean's approval "
            f"({T.regulation_source('max_credits_regular_term')}). Lower the "
            f"minimum, or tell me the overload is already approved and what "
            f"ceiling it allows.")
        log.event("needs_input", reason="workload above the regulation cap")
        return AgentResult(status="needs_input", message=message,
                           questions=["What credit load should I plan to, "
                                      "given the 18-credit cap?"],
                           log_path=log.path)

    try:
        major = T.get_program(profile.major)
    except KeyError:
        message = (f"There is no program called {profile.major!r} in the "
                   f"{profile.cohort} catalog, so I cannot plan it.")
        log.event("unsupported", reason=message)
        return AgentResult(status="unsupported", message=message,
                           log_path=log.path)

    minor = T.get_program(profile.minor) if profile.minor else None
    for program in (major, minor):
        if program is not None and program.tier is Tier.UNSUPPORTED:
            reason = "; ".join(program.unparsed_lines[:3])
            message = (f"{program.title} ({program.code}) cannot be planned "
                       f"reliably from the published requirements, so I am "
                       f"not going to produce a plan for it. {reason}")
            log.event("unsupported", program=program.code, reason=message)
            return AgentResult(status="unsupported", message=message,
                               log_path=log.path)

    catalog = T.catalog()
    common_core = T.common_core_for(profile.major)
    spec = build_tools(profile, major, minor)
    system = prompt_text("system")
    degree = T.regulation("graduation_total_credits") or 120.0
    floor = sum(_group_credits(g, catalog)
                for program in (major, minor, common_core) if program
                for g in program.groups)
    prompt = prompt_text(
        "planning",
        paths=str(paths), program=major.code, program_title=major.title,
        cohort=profile.cohort, years=str(profile.programme_years),
        minor=minor.title if minor else "none",
        tier=major.tier.value, tier_note=TIER_NOTE[major.tier],
        profile_summary=_profile_summary(profile),
        term_table=_term_table(profile),
        free_terms=", ".join(profile.free_terms) or "none",
        exchange_terms=", ".join(profile.exchange_terms) or "none",
        workload_min=f"{profile.workload_min:g}",
        workload_max=f"{profile.workload_max:g}",
        spread=profile.spread,
        requirements=_all_requirements(major, minor, common_core, catalog),
        degree_credits=f"{degree:g}",
        required_credits=f"{floor:g}",
        free_credits=f"{max(0.0, degree - floor):g}",
        expected_rows=str(round(degree / 3)),
        already_done=_already_done(profile),
        tool_summary="\n".join(f"- `{t.name}` — {t.description}" for t in spec),
    )
    log.event("prompt_built", chars=len(prompt), tools=[t.name for t in spec],
              degree_credits=degree, required_credits=floor)

    message = prompt
    drafted: list[Path] = []
    iterations = 0
    unreadable = False

    for iterations in range(1, max_iterations + 1):
        # CLAUDE.md puts retries on MODEL_FAST, which is right for a
        # reply that was merely unreadable. Re-planning around a
        # validation error is the same work as planning, so it stays on
        # MODEL_STRONG.
        task = "retry" if unreadable else "plan"
        log.event("llm_request", iteration=iterations, task=task,
                  chars=len(message))
        try:
            reply = chat(message, task=task, system=system, tools=spec)
        except LLMUnavailable as exc:
            log.event("llm_unavailable", error=str(exc))
            return AgentResult(status="failed", message=str(exc),
                               paths=drafted, iterations=iterations,
                               log_path=log.path)
        log.event("llm_reply", iteration=iterations, backend=reply.backend,
                  model=reply.model, turns=reply.turns,
                  tool_calls=[name for name, _ in reply.tool_calls],
                  cost_usd=reply.cost_usd, chars=len(reply.text))

        try:
            drafted = _parse_paths(reply)
        except (ValueError, json.JSONDecodeError) as exc:
            unreadable = True
            log.event("unreadable_reply", iteration=iterations,
                      error=str(exc))
            message = (f"That reply could not be read: {exc}\n\nSend the same "
                       f"answer again as one JSON object in the shape the "
                       f"instructions described, with nothing before or after "
                       f"it.")
            continue

        unreadable = False
        for path in drafted:
            path.report = validate_plan(path.plan, profile, major=major,
                                        minor=minor, catalog=catalog)
            log.event("validated", iteration=iterations, path=path.name,
                      errors=[i.message for i in path.report.errors],
                      warnings=len(path.report.warnings),
                      credits=path.report.credits.confirmed)

        broken = [p for p in drafted if not p.ok]
        if not broken:
            log.event("accepted", iterations=iterations,
                      paths=[p.name for p in drafted])
            return AgentResult(status="ok", paths=drafted,
                               iterations=iterations, log_path=log.path)

        if iterations == max_iterations:
            break
        message = _fix_request(drafted)

    log.event("gave_up", iterations=iterations,
              unresolved=sum(len(p.report.errors) for p in drafted
                             if p.report))
    return AgentResult(
        status="ok" if any(p.ok for p in drafted) else "failed",
        message=("Some paths still have blocking problems after "
                 f"{iterations} attempts. They are listed with each path and "
                 f"must be shown to the student."),
        paths=drafted, iterations=iterations, log_path=log.path)


def _as_payload(paths: list[Path]) -> dict:
    return {"paths": [{"name": p.name, "summary": p.summary,
                       "why_it_fits": p.why_it_fits,
                       "trade_offs": p.trade_offs,
                       "plan": [r.model_dump(exclude_defaults=True)
                                for r in p.plan],
                       "slot_suggestions": p.slot_suggestions}
                      for p in paths]}


def _fix_request(drafted: list[Path]) -> str:
    """The retry message, carrying the whole previous answer back.

    Each call to a backend is a fresh conversation — the Agent SDK starts a
    new session per query, and the API wrapper sends no history — so a retry
    that listed only the errors was asking the model to fix a plan it could
    no longer see. That is what made the first real runs spend four
    iterations achieving nothing.
    """
    parts = ["Here is the answer you sent. Some of it does not validate.", "",
             "```json", json.dumps(_as_payload(drafted), indent=1), "```", "",
             "## What is wrong", ""]
    for path in drafted:
        errors = path.report.errors if path.report else []
        if not errors:
            parts.append(f"- **{path.name}**: valid. Keep it exactly as it is.")
            continue
        parts.append(f"- **{path.name}**:")
        parts += [f"  - {issue.message}" for issue in errors]
    parts += [
        "",
        "Send the whole JSON object again with every path — the valid ones "
        "unchanged, the rest corrected. Change as little as possible. If a "
        "requirement genuinely cannot be met, leave it unmet and say so in "
        "`trade_offs`; never invent a course to cover it.",
    ]
    return "\n".join(parts)


# --------------------------------------------------------------- the CLI --

def load_profile(path: FilePath) -> StudentProfile:
    """A profile file, or one of the Phase 3 test fixtures."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = raw.get("profile", raw)
    transfers = [r for r in raw.get("plan", []) if r.get("status") == "transfer"]
    if transfers and "transfer_credits" not in fields:
        fields = {**fields, "transfer_credits": transfers}
    return StudentProfile.model_validate(fields)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile", type=FilePath)
    ap.add_argument("--paths", type=int, default=DEFAULT_PATHS)
    ap.add_argument("--max-iterations", type=int, default=DEFAULT_ITERATIONS)
    args = ap.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    profile = load_profile(args.profile)
    result = plan_for(profile, paths=args.paths,
                      max_iterations=args.max_iterations)

    print(f"status: {result.status}   iterations: {result.iterations}")
    if result.message:
        print(result.message)
    for question in result.questions:
        print(f"  ? {question}")

    for path in result.paths:
        report = path.report
        mark = "ok " if path.ok else "!! "
        print(f"\n{mark}{path.name}")
        if path.summary:
            print(f"   {path.summary}")
        if report:
            print(f"   {report.credits.confirmed:g} credits, "
                  f"{len(report.errors)} errors, {len(report.warnings)} warnings")
            for term, credits in sorted(report.per_term.items(),
                                        key=lambda kv: sort_key(kv[0])):
                print(f"     {term:11} {credits:g}")
            for issue in report.errors:
                print(f"     ERROR {issue.message[:110]}")
    if result.log_path:
        print(f"\nlog: {result.log_path}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
