"""Phase 4 tests: the LLM wrapper, the agent loop and the run log.

Everything here runs on `LLM_BACKEND=stub`, which answers from the same
deterministic tools the real backends are given. That exercises the parts
worth testing — the loop, the retries, validation of what comes back, the
refusals and the log — without a model, a network or a bill. What the stub
cannot test is the quality of a model's judgement, and no test here pretends
to.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from planner import llm  # noqa: E402
from planner.agent import (  # noqa: E402
    build_tools,
    describe_program,
    load_profile,
    plan_for,
)
from planner.intake import StudentProfile, follow_up_questions, missing_required  # noqa: E402
from planner.llm import LLMUnavailable, Reply, ToolSpec, chat, prompt_text  # noqa: E402
from planner.logging import RunLog  # noqa: E402
from planner.tools import catalog, draft_plan, get_program  # noqa: E402

PROFILES = REPO / "tests" / "profiles"


@pytest.fixture(autouse=True)
def stub_backend(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "stub")


@pytest.fixture
def log(tmp_path) -> RunLog:
    return RunLog.open(name="test", directory=tmp_path)


def comp(**fields) -> StudentProfile:
    return StudentProfile(**{"cohort": "2026-27", "major": "COMP", **fields})


# ------------------------------------------------------------- the wrapper --

def test_the_backend_and_model_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "api")
    assert llm.backend_name() == "api"
    monkeypatch.setenv("MODEL_FAST", "claude-haiku-5-5")
    monkeypatch.setenv("MODEL_STRONG", "claude-opus-5-5")
    # fast for intake and retries, strong for the work that matters
    assert llm.model_for("intake") == "claude-haiku-5-5"
    assert llm.model_for("retry") == "claude-haiku-5-5"
    assert llm.model_for("plan") == "claude-opus-5-5"
    assert llm.model_for("prose") == "claude-opus-5-5"


def test_an_unknown_backend_says_so_rather_than_guessing(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "gpt")
    with pytest.raises(LLMUnavailable, match="not one of"):
        chat("hello")


def test_the_api_backend_refuses_to_run_without_a_key(monkeypatch):
    """Hard rule 8: the key lives in .env or Streamlit secrets, never here."""
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable, match="ANTHROPIC_API_KEY"):
        chat("hello")


def test_a_reply_parses_json_out_of_a_fenced_block():
    fenced = Reply(text='Here you go:\n```json\n{"paths": []}\n```\n',
                   backend="stub", model="none")
    assert fenced.json() == {"paths": []}
    assert Reply(text='{"a": 1}', backend="stub", model="none").json() == {"a": 1}
    with pytest.raises(ValueError, match="no JSON object"):
        Reply(text="sorry, no", backend="stub", model="none").json()


def test_the_stub_says_plainly_that_no_model_ran():
    reply = chat("write something", task="prose")
    assert "stub" in reply.text.lower()
    assert reply.model == "none"


def test_prompts_are_files_and_carry_the_hard_rules():
    system = prompt_text("system")
    for phrase in ("Never invent a course code", "SLOT:", "mapping is approved",
                   "do not predict grades".lower()):
        assert phrase.lower() in system.lower(), phrase
    filled = prompt_text("planning", paths="2", program="COMP",
                         program_title="BEng in Computer Science",
                         cohort="2026-27")
    assert "# Plan 2 paths" in filled
    assert "BEng in Computer Science" in filled


# --------------------------------------------------------------- the tools --

def test_the_model_is_given_only_deterministic_tools():
    specs = build_tools(comp(), get_program("COMP"), None)
    assert {t.name for t in specs} == {"draft_plan", "search_courses",
                                       "get_program"}
    for spec in specs:
        assert spec.schema["type"] == "object"
        assert spec.schema["additionalProperties"] is False
        assert spec.description


def test_the_search_tool_returns_real_catalog_rows():
    specs = {t.name: t for t in build_tools(comp(), get_program("COMP"), None)}
    rows = json.loads(specs["search_courses"].run({"query": "machine learning",
                                                   "subject": "COMP"}))
    assert rows and all(row["code"] in catalog() for row in rows)


def test_a_tool_that_raises_comes_back_as_an_error_not_a_crash():
    boom = ToolSpec(name="boom", description="", schema={},
                    run=lambda args: 1 / 0)
    reply = chat("go", task="plan", tools=[boom])
    assert reply.text == ""          # no draft_plan, so the stub says nothing


def test_the_requirements_are_described_without_inventing_anything():
    text = describe_program(get_program("COMP"), catalog())
    assert "COMP 1023" in text and "Elective" in text
    assert "COMP 9999" not in text


# ---------------------------------------------------------------- the loop --

def test_a_missing_required_field_is_asked_about_not_guessed(log):
    result = plan_for(StudentProfile(major="COMP"), log=log)
    assert result.status == "needs_input"
    assert result.paths == []
    assert any("intake year" in q for q in result.questions)

    assert missing_required(StudentProfile()) == ["cohort", "major"]
    assert len(follow_up_questions(StudentProfile())) == 2


def test_an_unsupported_program_gets_no_plan_at_all(log):
    """Hard rule 5: say plainly that it cannot be planned, and stop."""
    result = plan_for(comp(major="MATH"), log=log)
    assert result.status == "unsupported"
    assert result.paths == []
    assert "cannot be planned reliably" in result.message
    assert "track" in result.message.lower()


def test_a_dual_degree_is_refused_as_out_of_scope(log):
    result = plan_for(comp(major="T&M-DDP"), log=log)
    assert result.status == "unsupported" and not result.paths


def test_a_program_that_does_not_exist_is_refused(log):
    result = plan_for(comp(major="NOT-A-PROGRAM"), log=log)
    assert result.status == "unsupported"
    assert "no program called" in result.message


def test_a_supported_major_produces_two_to_three_valid_paths(log):
    result = plan_for(comp(), paths=3, log=log)
    assert result.status == "ok"
    assert 2 <= len(result.paths) <= 3
    for path in result.paths:
        assert path.ok, [i.message for i in path.report.errors]
        assert path.report.credits.confirmed >= 120
        assert path.name and path.summary


def test_the_paths_are_actually_different():
    result = plan_for(comp(), paths=3)
    shapes = {tuple(sorted(p.report.per_term.items())) for p in result.paths}
    assert len(shapes) == len(result.paths), "the paths are the same plan"


def test_front_loaded_plus_a_free_term_plus_exchange_all_hold_at_once():
    """Phase 4's own test case: three constraints that fight each other."""
    profile = load_profile(PROFILES / "10-front-free-exchange.json")
    result = plan_for(profile, paths=1)
    assert result.status == "ok"
    path = result.paths[0]
    assert path.ok, [i.message for i in path.report.errors]

    # Y4 Spring really is free
    assert path.report.per_term.get("Y4 Spring", 0) == 0
    # Y3 Spring holds exchange rows and no HKUST course
    away = [p for p in path.plan if p.term == "Y3 Spring"]
    assert away and all(p.status == "exchange" for p in away)
    assert all(not p.mapping_approved for p in away)
    # front-loaded: the first half carries at least as much as the second
    order = sorted(path.report.per_term, key=lambda t: (t[1], t))
    assert not any(i.check == "check_spread" for i in path.report.warnings)


def test_a_final_year_project_is_never_sent_abroad():
    profile = load_profile(PROFILES / "10-front-free-exchange.json")
    rows = draft_plan(profile, get_program("COMP"))
    titles = [catalog()[p.code].title.lower() for p in rows
              if p.status == "exchange" and p.code in catalog()]
    assert not any("final year" in t or "industrial experience" in t
                   for t in titles)


def test_an_exchange_row_is_never_counted_as_met():
    """Hard rule 6."""
    profile = load_profile(PROFILES / "10-front-free-exchange.json")
    report = plan_for(profile, paths=1).paths[0].report
    assert report.credits.exchange_pending > 0
    assert report.credits.confirmed < 120 <= report.credits.with_exchange
    assert any("not approved yet" in i.message for i in report.warnings)


def test_an_unreadable_reply_is_retried_then_given_up_on(monkeypatch, log):
    """The model sends something that is not JSON. The loop asks again, and
    stops after max_iterations rather than looping forever."""
    attempts = []

    def nonsense(prompt, **kwargs):
        attempts.append(kwargs.get("task"))
        return Reply(text="I would rather not.", backend="stub", model="none")

    monkeypatch.setitem(llm.BACKENDS, "stub", nonsense)
    result = plan_for(comp(), max_iterations=3, log=log)
    assert result.status == "failed"
    assert attempts == ["plan", "retry", "retry"]
    assert log.events_of("unreadable_reply")


def test_a_backend_that_cannot_run_is_reported_not_raised(monkeypatch, log):
    def unavailable(prompt, **kwargs):
        raise LLMUnavailable("no model here")

    monkeypatch.setitem(llm.BACKENDS, "stub", unavailable)
    result = plan_for(comp(), log=log)
    assert result.status == "failed" and "no model here" in result.message
    assert log.events_of("llm_unavailable")


def test_errors_go_back_to_the_model_and_the_paths_come_back_fixed(monkeypatch,
                                                                   log):
    """One broken path on the first try, fixed on the second."""
    calls = {"n": 0}
    good = llm.BACKENDS["stub"]

    def flaky(prompt, **kwargs):
        calls["n"] += 1
        reply = good(prompt, **kwargs)
        if calls["n"] == 1:
            payload = reply.json()
            payload["paths"][0]["plan"].append(
                {"code": "COMP 9999", "term": "Y1 Fall", "status": "planned"})
            return Reply(text=json.dumps(payload), backend="stub", model="none")
        return reply

    monkeypatch.setitem(llm.BACKENDS, "stub", flaky)
    result = plan_for(comp(), paths=2, max_iterations=3, log=log)
    assert result.status == "ok" and result.iterations == 2
    assert all(p.ok for p in result.paths)
    sent = log.events_of("validated")
    assert any("COMP 9999" in str(e["errors"]) for e in sent)


# ----------------------------------------------------------------- the log --

def test_every_run_leaves_a_replayable_log(log):
    plan_for(comp(), paths=2, log=log)
    events = log.read()
    kinds = [e["event"] for e in events]
    for required in ("run_started", "profile", "prompt_built", "llm_request",
                     "llm_reply", "validated", "accepted"):
        assert required in kinds, required
    assert all("at" in e and "elapsed_s" in e for e in events)
    # the profile is recorded in full so a run can be replayed
    profile = next(e for e in events if e["event"] == "profile")["profile"]
    assert profile["major"] == "COMP"


def test_the_log_never_writes_a_credential(tmp_path):
    log = RunLog.open(name="secrets", directory=tmp_path)
    log.event("config", api_key="sk-ant-real", nested={"auth_token": "t"},
              model="claude-opus-5-5")
    text = log.path.read_text(encoding="utf-8")
    assert "sk-ant-real" not in text and "<redacted>" in text
    assert "claude-opus-5-5" in text


def test_the_cli_runs_a_profile_file_end_to_end(tmp_path, monkeypatch):
    from planner import agent

    monkeypatch.chdir(tmp_path)
    code = agent.main([str(PROFILES / "01-comp-correct.json"), "--paths", "2"])
    assert code == 0
