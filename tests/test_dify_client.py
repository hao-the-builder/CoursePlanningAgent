"""Calling the Dify workflow, with Dify faked.

No network and no Dify account here. What these check is the half this repo
owns: that the four Start-node inputs are built the way the DSL declares
them, that a refusal happens before a request goes out, that a failed or
malformed run is reported rather than mined for a plan, and above all that
the verdict comes from the local validator and not from the answer Dify sent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from planner import dify                              # noqa: E402
from planner.agent import load_profile                 # noqa: E402
from planner.intake import StudentProfile              # noqa: E402
from planner.llm import LLMUnavailable                 # noqa: E402
from planner.tools import draft_plan, get_program      # noqa: E402

PROFILE = REPO / "tests" / "profiles" / "01-comp-correct.json"
DSL = REPO / "dify" / "course-planner.yml"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("DIFY_API_KEY", "app-test-key")
    monkeypatch.setenv("DIFY_BASE_URL", "https://dify.example/v1")
    monkeypatch.setenv("TOOL_API_TOKEN", "tool-test-token")
    monkeypatch.setenv("TOOL_API_BASE", "http://host.docker.internal:8601")


@pytest.fixture(scope="module")
def profile() -> StudentProfile:
    return load_profile(PROFILE)


@pytest.fixture(scope="module")
def good_plan(profile) -> list[dict]:
    """A plan that really validates, so the fake Dify returns a real one."""
    rows = draft_plan(profile, get_program(profile.major))
    return [json.loads(row.model_dump_json(exclude_defaults=True))
            for row in rows]


def fake(body: dict, status: int = 200, capture: list | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handle))


def succeeded(result: dict) -> dict:
    return {"task_id": "t1", "workflow_run_id": "w1",
            "data": {"id": "r1", "status": "succeeded",
                     "outputs": {"result": json.dumps(result)},
                     "elapsed_time": 12.5, "total_tokens": 4321}}


# --------------------------------------------------------- what we send --

def test_the_inputs_are_the_four_variables_the_dsl_declares(profile):
    dsl = yaml.safe_load(DSL.read_text(encoding="utf-8"))
    start = next(n for n in dsl["workflow"]["graph"]["nodes"]
                 if n["data"]["type"] == "start")
    declared = {v["variable"] for v in start["data"]["variables"]}
    assert set(dify.inputs_for(profile)) == declared


def test_the_profile_goes_as_the_answers_a_reviewer_would_pick(profile):
    """The workflow assembles the profile from form answers, so a run from
    here sends the same answers and exercises the same node."""
    sent = dify.inputs_for(profile)
    assert sent["major"] == profile.major
    assert sent["cohort"] == profile.cohort
    assert sent["workload_min"] == str(profile.workload_min)
    assert sent["workload_max"] == str(profile.workload_max)
    assert sent["spread"] == profile.spread
    assert sent["tool_token"] == "tool-test-token"
    assert all(isinstance(value, str) for value in sent.values()),         "Dify fills these into text fields"


def test_free_terms_the_form_cannot_express_are_refused_not_dropped(profile):
    """Silently planning a different degree than the one asked for is the
    worst of the available outcomes."""
    import pytest

    asked = profile.model_copy(update={"free_terms": ["Y2 Spring"]})
    with pytest.raises(ValueError, match="no option for free terms"):
        dify.inputs_for(asked)


def test_the_free_term_options_match_the_forms_own_list():
    dsl = yaml.safe_load(DSL.read_text(encoding="utf-8"))
    start = next(n for n in dsl["workflow"]["graph"]["nodes"]
                 if n["data"]["type"] == "start")
    field = next(v for v in start["data"]["variables"]
                 if v["variable"] == "free_terms")
    assert set(field["options"]) == set(dify.FREE_TERM_CHOICES.values()),         "the client offers options the form does not, or the reverse"


def test_the_request_is_a_blocking_workflow_run_with_the_app_key(
        profile, good_plan):
    seen: list[httpx.Request] = []
    dify.plan_for_dify(profile, client=fake(
        succeeded({"plan": good_plan, "rationale": "r",
                   "validation": {"ok": True}}), capture=seen))
    request, = seen
    assert str(request.url) == "https://dify.example/v1/workflows/run"
    assert request.headers["authorization"] == "Bearer app-test-key"
    body = json.loads(request.content)
    assert body["response_mode"] == "blocking"
    assert body["user"]


# ------------------------------------------------- refusals before a call --

def test_a_missing_cohort_asks_rather_than_calling_dify():
    seen: list[httpx.Request] = []
    with pytest.raises(LLMUnavailable, match="cohort"):
        dify.plan_for_dify(StudentProfile(major="COMP"),
                           client=fake({}, capture=seen))
    assert not seen, "a request went out before the input was checked"


def test_an_unsupported_program_is_refused_before_a_call(profile):
    """Hard rule 5 does not wait for a round trip."""
    seen: list[httpx.Request] = []
    with pytest.raises(LLMUnavailable, match="unsupported"):
        dify.plan_for_dify(profile.model_copy(update={"major": "MATH"}),
                           client=fake({}, capture=seen))
    assert not seen


def test_no_key_is_said_plainly(monkeypatch, profile):
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable, match="DIFY_API_KEY"):
        dify.plan_for_dify(profile, client=fake({}))


def test_no_tool_token_is_said_plainly(monkeypatch, profile):
    monkeypatch.delenv("TOOL_API_TOKEN", raising=False)
    with pytest.raises(LLMUnavailable, match="TOOL_API_TOKEN"):
        dify.plan_for_dify(profile, client=fake({}))


# ------------------------------------------------------ what comes back --

def test_a_good_run_is_parsed_whole(profile, good_plan):
    result = dify.plan_for_dify(profile, client=fake(
        succeeded({"plan": good_plan, "rationale": "Front-loaded it.",
                   "program": {"code": "COMP", "tier": "verified"},
                   "validation": {"ok": True}})))
    assert result.ok
    assert result.agreed
    assert len(result.plan) == len(good_plan)
    assert result.rationale == "Front-loaded it."
    assert result.program["tier"] == "verified"
    assert result.workflow_run_id == "w1"
    assert result.tokens == 4321


def test_the_local_validator_overrules_difys_claim_that_a_plan_is_fine(
        profile, good_plan):
    """The point of the whole arrangement: hard rule 2 is enforced here.

    Dify says `ok: true` while handing back a plan with an invented course.
    The returned result must not be ok, and must say the two sides disagree.
    """
    lying = good_plan + [{"code": "COMP 9999", "term": "Y3 Fall",
                          "status": "planned"}]
    result = dify.plan_for_dify(profile, client=fake(
        succeeded({"plan": lying, "rationale": "All good!",
                   "validation": {"ok": True}})))

    assert result.remote_ok is True
    assert result.ok is False
    assert not result.agreed
    assert any("COMP 9999" in issue.message for issue in result.report.errors)


def test_a_failed_run_is_reported_not_mined(profile):
    with pytest.raises(LLMUnavailable, match="failed"):
        dify.plan_for_dify(profile, client=fake(
            {"workflow_run_id": "w1",
             "data": {"status": "failed", "error": "node 1706 timed out",
                      "outputs": {}}}))


def test_a_run_with_no_result_output_names_the_contract(profile):
    with pytest.raises(LLMUnavailable, match="result"):
        dify.plan_for_dify(profile, client=fake(
            {"data": {"status": "succeeded", "outputs": {"answer": "hi"}}}))


def test_a_non_json_result_is_caught(profile):
    with pytest.raises(LLMUnavailable, match="not JSON"):
        dify.plan_for_dify(profile, client=fake(
            {"data": {"status": "succeeded",
                      "outputs": {"result": "I could not do it"}}}))


def test_an_empty_plan_is_not_passed_off_as_one(profile):
    with pytest.raises(LLMUnavailable, match="empty plan"):
        dify.plan_for_dify(profile, client=fake(
            succeeded({"plan": [], "rationale": "nothing to do"})))


def test_an_http_error_quotes_dify(profile):
    with pytest.raises(LLMUnavailable, match="401"):
        dify.plan_for_dify(profile, client=fake(
            {"message": "Access token is invalid"}, status=401))


def test_an_unreachable_dify_says_so(profile):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=request)

    client = httpx.Client(transport=httpx.MockTransport(refuse))
    with pytest.raises(LLMUnavailable, match="could not be reached"):
        dify.plan_for_dify(profile, client=client)
