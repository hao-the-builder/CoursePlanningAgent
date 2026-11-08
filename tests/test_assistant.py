"""Phase 6 tests: the assistant that answers about a plan and revises it.

The model's reply is faked here, because what needs testing is not what a
model says but what the code does with it: a revision is parsed into real
course rows, validated, and only applied if it is no worse than the plan it
replaces. The changes shown to the student are read off the two plans, never
taken from the model's own account of what it did.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path as FilePath

import pytest

REPO = FilePath(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from planner import assistant  # noqa: E402
from planner.agent import load_profile, plan_for  # noqa: E402
from planner.llm import LLMUnavailable, Reply  # noqa: E402
from schema import PlannedCourse  # noqa: E402

PROFILE = REPO / "tests" / "profiles" / "01-comp-correct.json"


@pytest.fixture(scope="module")
def planned():
    """A real validated plan from the stub backend — the thing we revise."""
    profile = load_profile(PROFILE)
    result = plan_for(profile, paths=1)
    assert result.paths, "the stub backend produced no plan to revise"
    return result.paths[0], profile


def reply_of(text: str) -> Reply:
    return Reply(text=text, backend="fake", model="fake")


def fake(monkeypatch, text: str) -> None:
    monkeypatch.setattr(assistant, "chat",
                        lambda *a, **k: reply_of(text))


def as_json(rows) -> str:
    return json.dumps({"plan": [
        {"code": r.code, "term": r.term, "status": r.status} for r in rows]})


# ------------------------------------------------------------ answering --

def test_a_question_is_answered_without_touching_the_plan(planned, monkeypatch):
    path, profile = planned
    fake(monkeypatch, "COMP 2611 sits in Y2 Fall because COMP 2011 comes "
                      "first and it is its prerequisite.")
    answer = assistant.ask("Why is COMP 2611 in Y2 Fall?", path=path,
                           profile=profile)
    assert not answer.revised
    assert answer.path is None
    assert "prerequisite" in answer.text
    assert answer.changes == []


def test_no_model_is_said_plainly_rather_than_guessed(planned, monkeypatch):
    path, profile = planned

    def unavailable(*_a, **_k):
        raise LLMUnavailable("no backend here")

    monkeypatch.setattr(assistant, "chat", unavailable)
    answer = assistant.ask("What fills the Arts slot?", path=path,
                           profile=profile)
    assert not answer.revised
    assert "No model is connected" in answer.text


# ------------------------------------------------------------- revising --

def test_a_change_that_validates_lands_and_the_diff_is_computed_not_quoted(
        planned, monkeypatch):
    """The model's prose is not trusted for what changed; the plans are.

    The validator is held to the plan's own verdict here, so the test is about
    the revision path rather than about whether this particular move happens
    to be legal. The gate itself is the next test.
    """
    path, profile = planned
    rows = [r.model_copy() for r in path.plan]
    once = Counter(r.code for r in rows)
    moved = next(r for r in rows
                 if r.status == "planned" and once[r.code] == 1)
    was, moved.term = moved.term, _other_term(rows, moved)

    monkeypatch.setattr(assistant, "validate_plan",
                        lambda *a, **k: path.report)
    fake(monkeypatch, "Moved one course later. I also rewrote your whole "
                      "degree, which is not true.\n" + as_json(rows))
    answer = assistant.ask("Move that course later", path=path,
                           profile=profile)

    assert answer.revised, answer.refused
    assert answer.changes == [f"{moved.code} moved from {was} to {moved.term}"]
    assert answer.path.report is not None
    assert len(answer.path.plan) == len(path.plan)


def test_an_invented_course_is_rejected_and_the_plan_is_kept(
        planned, monkeypatch):
    """Hard rule 1 holds whatever the model is talked into writing."""
    path, profile = planned
    rows = [r.model_copy() for r in path.plan]
    rows.append(PlannedCourse(code="COMP 9999", term="Y3 Fall",
                              status="planned"))

    fake(monkeypatch, "Added COMP 9999 Advanced Wizardry.\n" + as_json(rows))
    answer = assistant.ask("Add COMP 9999", path=path, profile=profile)

    assert not answer.revised
    assert answer.refused
    assert any("COMP 9999" in message for message in answer.errors)


def test_a_reply_that_is_not_json_is_treated_as_an_answer(planned, monkeypatch):
    path, profile = planned
    fake(monkeypatch, "I cannot do that without breaking the prerequisite "
                      "chain: {this brace is not a plan}")
    answer = assistant.ask("Move everything to Y1", path=path, profile=profile)
    assert not answer.revised
    assert "prerequisite chain" in answer.text


# ---------------------------------------------------------- the reading --

def test_the_plan_is_handed_over_as_one_line_per_course(planned):
    from planner.tools import catalog

    path, _ = planned
    table = assistant.plan_table(path, catalog())
    assert len(table.splitlines()) == len(path.plan)
    assert all(line.count("|") == 4 for line in table.splitlines())


def test_the_changes_list_names_adds_removes_and_moves():
    old = [PlannedCourse(code="COMP 2011", term="Y1 Fall", status="planned"),
           PlannedCourse(code="COMP 2012", term="Y1 Spring", status="planned")]
    new = [PlannedCourse(code="COMP 2011", term="Y2 Fall", status="planned"),
           PlannedCourse(code="COMP 2611", term="Y1 Spring", status="planned")]
    assert assistant.changes_between(old, new) == [
        "COMP 2611 added to Y1 Spring",
        "COMP 2012 removed from Y1 Spring",
        "COMP 2011 moved from Y1 Fall to Y2 Fall",
    ]


def _other_term(rows, row) -> str:
    """Any later term that already holds courses, so the move is plausible."""
    from planner.terms import sort_key

    terms = sorted({r.term for r in rows if r.status == "planned"},
                   key=sort_key)
    after = [t for t in terms if sort_key(t) > sort_key(row.term)]
    return after[0] if after else terms[0]
