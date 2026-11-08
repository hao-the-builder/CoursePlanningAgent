"""The assistant that sits beside a finished plan.

Two things a student wants once a plan exists: to ask why it looks like that,
and to change it. Both go through `ask()`.

The division of labour is the same as everywhere else in this project. The
model reads the plan and the requirement data through the tools the agent
already exposes, chooses what to say, and — for a change — writes the revised
list of courses. Nothing it says is taken as fact about a course, and nothing
it writes is shown to the student until `validate_plan` has judged it:

* the revision is parsed into real `PlannedCourse` rows, so an invented course
  code cannot survive (hard rule 1 — `unknown_courses` is a blocking error);
* it is validated in full, exactly as a generated plan is;
* it lands only if it is no worse than the plan it replaces. A revision that
  introduces a blocking error is reported and dropped, with the errors quoted,
  and the student keeps the plan they had;
* the list of changes shown to the student is computed here by comparing the
  two plans, not taken from the model's description of its own work.

What it will not do is what the whole app will not do: register anything,
contact anyone, or predict a grade.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace

from planner.agent import Path, build_tools
from planner.intake import StudentProfile
from planner.llm import LLMUnavailable, Reply, chat, prompt_text
from planner.logging import RunLog
from planner.terms import sort_key
from planner.tools import catalog as load_catalog
from planner.tools import get_program
from planner.validate import ValidationReport, validate_plan
from schema import PlannedCourse

MAX_HISTORY = 8            # turns of context sent back with a question
JSON_BLOCK = re.compile(r"\{.*\}", re.S)


@dataclass
class Answer:
    """What one turn of the assistant produced."""

    text: str
    path: Path | None = None           # the revised path, when one landed
    changes: list[str] = field(default_factory=list)
    refused: str = ""                  # why a revision did not land
    errors: list[str] = field(default_factory=list)
    backend: str = ""

    @property
    def revised(self) -> bool:
        return self.path is not None


# ------------------------------------------------------ what it is told --

def plan_table(path: Path, catalog: dict) -> str:
    """The plan as the model should see it: one line per course, by term."""
    rows = sorted(path.plan, key=lambda r: (sort_key(r.term), r.code))
    lines = []
    for row in rows:
        course = catalog.get(row.code)
        credits = f"{course.credits:g}" if course else "?"
        title = course.title if course else row.title or ""
        lines.append(f"{row.term} | {row.code} | {title} | {credits} | "
                     f"{row.status}")
    return "\n".join(lines) or "(empty)"


def report_summary(report: ValidationReport | None) -> str:
    if report is None:
        return "(not validated)"
    out = [f"confirmed credits: {report.credits.confirmed:g}",
           f"exchange pending: {report.credits.exchange_pending:g}",
           f"blocking errors: {len(report.errors)}",
           f"warnings: {len(report.warnings)}"]
    for issue in report.errors:
        out.append(f"ERROR — {issue.message}")
    for issue in report.warnings[:12]:
        out.append(f"warning — {issue.message}")
    if len(report.warnings) > 12:
        out.append(f"… and {len(report.warnings) - 12} more warnings")
    return "\n".join(out)


def _history_text(history) -> str:
    recent = list(history)[-MAX_HISTORY * 2:]
    return "\n".join(f"{who}: {what}" for who, what in recent) or "(none)"


# ------------------------------------------------- reading what came back --

def _revision_rows(reply: Reply) -> list[PlannedCourse] | None:
    """The revised plan in the reply, or None if it only answered."""
    match = JSON_BLOCK.search(reply.text or "")
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "plan" not in payload:
        return None
    rows = []
    for row in payload.get("plan") or []:
        rows.append(PlannedCourse.model_validate(row))
    return rows


def _prose(reply: Reply) -> str:
    """The reply with any JSON block taken out."""
    text = JSON_BLOCK.sub("", reply.text or "").strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def changes_between(old: list[PlannedCourse],
                    new: list[PlannedCourse]) -> list[str]:
    """What actually changed, read off the two plans rather than described.

    Counted by (course, term) pair rather than by course, because a course can
    legitimately appear in several terms — COMP 4900 is required in every term
    a COMP student is in residence — and keying by code alone would hide a
    move of one of them.
    """
    before = Counter((row.code, row.term) for row in old)
    after = Counter((row.code, row.term) for row in new)
    added = sorted((after - before).elements())
    removed = sorted((before - after).elements())

    moved = []
    for gone in list(removed):
        came = next((pair for pair in added if pair[0] == gone[0]), None)
        if came is not None:
            added.remove(came)
            removed.remove(gone)
            moved.append(f"{gone[0]} moved from {gone[1]} to {came[1]}")

    return ([f"{code} added to {term}" for code, term in added]
            + [f"{code} removed from {term}" for code, term in removed]
            + moved)


# ------------------------------------------------------------- the turn --

def ask(question: str, *, path: Path, profile: StudentProfile,
        history=(), log: RunLog | None = None) -> Answer:
    """Answer a question about the plan, and revise it if that is the ask."""
    catalog = load_catalog()
    major = get_program(profile.major)
    minor = get_program(profile.minor) if profile.minor else None
    tools = build_tools(profile, major, minor)

    prompt = prompt_text(
        "assistant",
        question=question.strip(),
        history=_history_text(history),
        path_name=path.name,
        plan=plan_table(path, catalog),
        verdict=report_summary(path.report),
        program=f"{major.code} — {major.title}",
        minor=f"{minor.code} — {minor.title}" if minor else "none",
        free_terms=", ".join(profile.free_terms) or "none",
        exchange=", ".join(profile.exchange_terms) or "none",
        load=f"{profile.workload_min:g}–{profile.workload_max:g} credits, "
             f"{profile.spread}-loaded",
    )

    try:
        reply = chat(prompt, task="assistant", tools=tools,
                     system=prompt_text("system"), max_tokens=8000)
    except LLMUnavailable as exc:
        return Answer(text=f"No model is connected, so I cannot answer this "
                           f"one: {exc}", backend="none")

    if log is not None:
        log.event("assistant", question=question[:400], backend=reply.backend,
                  model=reply.model, chars=len(reply.text or ""),
                  cost_usd=reply.cost_usd)

    try:
        rows = _revision_rows(reply)
    except Exception as exc:                            # noqa: BLE001
        return Answer(text=_prose(reply) or "I could not write that change.",
                      refused=f"the revision could not be read: {exc}",
                      backend=reply.backend)

    text = _prose(reply)
    if rows is None:
        if not text:
            text = ("The model returned nothing for that. Try asking it more "
                    "directly.")
        return Answer(text=text, backend=reply.backend)

    report = validate_plan(rows, profile, major=major, minor=minor,
                           catalog=catalog)
    was = len(path.report.errors) if path.report else 0
    errors = [issue.message for issue in report.errors]

    if len(errors) > was:
        if log is not None:
            log.event("revision_rejected", errors=errors)
        return Answer(
            text=text or "I tried that change.",
            refused=("that change breaks the plan, so it was not applied — "
                     "your plan is unchanged"),
            errors=errors, backend=reply.backend)

    changes = changes_between(path.plan, rows)
    if not changes:
        return Answer(text=text or "Nothing in the plan needed to change.",
                      backend=reply.backend)

    if log is not None:
        log.event("revision_applied", changes=changes,
                  errors=errors, warnings=len(report.warnings))
    return Answer(text=text, path=replace(path, plan=rows, report=report),
                  changes=changes, errors=errors, backend=reply.backend)
