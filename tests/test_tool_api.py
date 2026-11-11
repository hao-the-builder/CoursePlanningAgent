"""The HTTP surface Dify calls.

These run the real handlers against the real `data/`, because the whole point
of the service is that Dify gets the same answers the local backends get. What
is checked here is the boundary: the token, the shape of each response, and
that a plan Dify might invent is rejected by the same validator the local
agent uses.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from starlette.testclient import TestClient      # noqa: E402

import service.tool_api as api                    # noqa: E402

TOKEN = "test-token-not-a-real-secret"
PROFILE = {"cohort": "2026-27", "major": "COMP", "programme_years": 4,
           "workload_min": 12, "workload_max": 18, "spread": "even"}


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv(api.TOKEN_ENV, TOKEN)


@pytest.fixture
def client():
    with TestClient(api.app) as session:
        yield session


def post(client, path: str, payload: dict, auth: str | None = TOKEN):
    headers = {"Authorization": f"Bearer {auth}"} if auth else {}
    return client.post(path, json=payload, headers=headers)


# ------------------------------------------------------------------ auth --

def test_health_is_open_so_dify_can_test_the_connection(client):
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["programs"] == 129
    assert body["tiers"]["verified"] == 5


def test_a_tool_without_a_token_is_refused(client):
    reply = post(client, "/tools/get_program", {"code": "COMP"}, auth=None)
    assert reply.status_code == 401
    assert "Bearer" in reply.json()["error"]


def test_a_tool_with_the_wrong_token_is_refused(client):
    reply = post(client, "/tools/get_program", {"code": "COMP"}, auth="nope")
    assert reply.status_code == 401


def test_the_service_will_not_start_without_a_token(monkeypatch):
    """Hard rule 8: the token comes from the environment, fail closed."""
    monkeypatch.delenv(api.TOKEN_ENV, raising=False)
    with pytest.raises(RuntimeError, match="TOOL_API_TOKEN"):
        api.token()


# ----------------------------------------------------------- the lookups --

def test_search_returns_real_courses_with_credits_and_prerequisites(client):
    body = post(client, "/tools/search_courses",
                {"query": "data structures", "subject": "COMP"}).json()
    assert body["count"] > 0
    first = body["courses"][0]
    assert first["code"].startswith("COMP ")
    assert set(first) == {"code", "title", "credits", "prerequisite",
                          "common_core_areas"}


def test_a_program_carries_its_tier_source_and_verification_date(client):
    body = post(client, "/tools/get_program", {"code": "COMP"}).json()
    assert body["tier"] == "verified"
    assert body["verified_on"]
    assert body["source_url"].startswith("http")
    assert body["plannable"] is True
    assert "Engineering Fundamental" in body["requirements"]


def test_an_unknown_program_is_said_plainly_rather_than_invented(client):
    reply = post(client, "/tools/get_program", {"code": "NOPE"})
    assert reply.status_code == 400
    assert "NOPE" in reply.json()["error"]


# -------------------------------------------------------------- planning --

def test_the_draft_is_a_real_plan_with_credits_per_term(client):
    body = post(client, "/tools/draft_plan", {"profile": PROFILE}).json()
    assert body["count"] > 30
    assert body["tier"] == "verified"
    assert all(row["code"] for row in body["plan"])
    assert sum(body["per_term"].values()) >= 120


def test_an_unsupported_program_is_refused_before_anything_is_planned(client):
    """Hard rule 5, enforced on Dify's side of the wire too."""
    reply = post(client, "/tools/draft_plan",
                 {"profile": dict(PROFILE, major="MATH")})
    assert reply.status_code == 422
    assert "unsupported" in reply.json()["error"]


def test_a_missing_major_asks_rather_than_guesses(client):
    reply = post(client, "/tools/draft_plan",
                 {"profile": {"cohort": "2026-27"}})
    assert reply.status_code == 400
    assert "major" in reply.json()["error"]


# ------------------------------------------------------------ validation --

def test_the_draft_validates_and_the_report_is_returned_whole(client):
    draft = post(client, "/tools/draft_plan", {"profile": PROFILE}).json()
    body = post(client, "/tools/validate_plan",
                {"profile": PROFILE, "plan": draft["plan"]}).json()
    assert body["error_count"] == 0, body["errors"]
    assert body["ok"] is True
    assert body["credits"]["confirmed"] >= 120
    assert body["per_term"]


def test_a_course_dify_invented_is_caught_here(client):
    """Hard rule 1 does not depend on which side of the wire wrote the plan."""
    draft = post(client, "/tools/draft_plan", {"profile": PROFILE}).json()
    plan = draft["plan"] + [{"code": "COMP 9999", "term": "Y3 Fall",
                             "status": "planned"}]
    body = post(client, "/tools/validate_plan",
                {"profile": PROFILE, "plan": plan}).json()
    assert body["ok"] is False
    assert any("COMP 9999" in issue["message"] for issue in body["errors"])


def test_a_plan_that_is_not_a_plan_is_a_readable_message(client):
    reply = post(client, "/tools/validate_plan",
                 {"profile": PROFILE, "plan": [{"nope": 1}]})
    assert reply.status_code == 400
    assert "row 0" in reply.json()["error"]


def test_a_plan_sent_as_a_json_string_is_accepted(client):
    """Dify variables arrive as text unless the workflow parsed them first."""
    import json

    draft = post(client, "/tools/draft_plan", {"profile": PROFILE}).json()
    body = post(client, "/tools/validate_plan",
                {"profile": json.dumps(PROFILE),
                 "plan": json.dumps({"plan": draft["plan"]})}).json()
    assert body["ok"] is True


# ------------------------------------------- the token in the body too --

def test_the_token_is_accepted_in_the_body(client):
    """Dify substitutes variables inside a JSON body dependably; whether it
    does so inside the headers field is not something its docs settle, and a
    header sent literally looks exactly like a wrong token."""
    reply = client.post("/tools/get_program",
                        json={"code": "COMP", "tool_token": TOKEN})
    assert reply.status_code == 200
    assert reply.json()["code"] == "COMP"


def test_a_wrong_token_in_the_body_is_still_refused(client):
    reply = client.post("/tools/get_program",
                        json={"code": "COMP", "tool_token": "nope"})
    assert reply.status_code == 401


def test_an_unfilled_template_says_what_went_wrong(client):
    """The 401 that costs the most time to diagnose, named outright."""
    reply = post(client, "/tools/get_program",
                 {"code": "COMP"}, auth="{{#1701.tool_token#}}")
    assert reply.status_code == 401
    assert "did not substitute" in reply.json()["error"]


def test_the_echo_endpoint_describes_without_revealing(client):
    body = client.post("/debug/echo",
                       json={"tool_token": "{{#1701.tool_token#}}"}).json()
    assert body["tool_token_in_body"]["looks_like_an_unfilled_template"]
    assert body["authorization_header"] == {"present": False}
    assert "not substituted" in body["hint"]
    # It must never confirm or deny a guess, only describe the shape.
    assert TOKEN not in json.dumps(body)
    assert "correct" not in json.dumps(body).lower()


def test_the_echo_endpoint_reports_a_token_that_did_arrive(client):
    body = post(client, "/debug/echo", {}).json()
    assert body["authorization_header"]["present"] is True
    assert body["authorization_header"]["length"] == len(TOKEN)
    assert body["expected_token_length"] == len(TOKEN)
