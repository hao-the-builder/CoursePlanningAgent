"""The deterministic tools, over HTTP, so a Dify workflow can call them.

Why this exists. Dify runs its agent loop on its own server and never hands a
tool call back to the caller — the Service API returns a finished answer, and
the only place a run pauses for the client is a Human Input node. So if the
agentic workflow is to live in Dify, the tools have to be reachable *from*
Dify. This module is that reach: the same functions `planner/tools.py` gives
the local backends, behind four JSON endpoints.

What it does not do, by construction:

  * It never writes anything. Every handler reads `data/` and returns JSON;
    there is no endpoint that creates, edits or deletes a file.
  * It never calls a model. The model is on Dify's side of the wire.
  * It is the only way the Dify workflow can learn a course code, so hard
    rule 1 survives the move: an invented code cannot come back from here,
    and `validate_plan` rejects one that Dify invents anyway.

Run it:

    TOOL_API_TOKEN=... python -m service.tool_api            # 127.0.0.1:8601
    TOOL_API_TOKEN=... python -m service.tool_api --host 0.0.0.0 --port 8601

The token is required and is read from the environment (`.env` locally, never
git — hard rule 8). Without it the server refuses to start rather than
serving `/tools/*` open to whatever can reach the port.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv                                 # noqa: E402
from starlette.applications import Starlette                  # noqa: E402
from starlette.requests import Request                        # noqa: E402
from starlette.responses import JSONResponse                   # noqa: E402
from starlette.routing import Route                            # noqa: E402

from planner import tools as T                                 # noqa: E402
from planner.agent import describe_program                      # noqa: E402
from planner.intake import StudentProfile                       # noqa: E402
from planner.validate import validate_plan                      # noqa: E402
from schema import PlannedCourse                                # noqa: E402

# `.env` is the one place the token is written down, so read it here as
# `app.py` does. An exported shell variable still wins, which is the
# precedence you want — but it is also how the two sides drift apart: a
# service started with one value in its shell keeps using it, whatever `.env`
# says afterwards, and every call then answers 401.
load_dotenv()

TOKEN_ENV = "TOOL_API_TOKEN"
SEARCH_LIMIT = 30


class Bad(Exception):
    """A request this service will not answer, with the reason to send back."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


# ------------------------------------------------------------------ auth --

def token() -> str:
    value = os.environ.get(TOKEN_ENV, "").strip()
    if not value:
        raise RuntimeError(
            f"{TOKEN_ENV} is not set. Put it in .env (never in git — hard "
            f"rule 8) and pass the same value as the Bearer token in Dify's "
            f"HTTP Request node. Generate one with:\n"
            f"  python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    return value


def header_token(request: Request) -> str | None:
    sent = request.headers.get("authorization", "")
    prefix = "bearer "
    if not sent.lower().startswith(prefix):
        return None
    return sent[len(prefix):].strip() or None


def unsubstituted(value: str) -> bool:
    """A Dify variable that was never filled in, arriving as its own name."""
    return "{{" in value or "#}}" in value


def authorise(request: Request, fields: dict[str, Any]) -> None:
    """The token, from the `Authorization` header or the request body.

    The body is allowed because a Dify HTTP Request node substitutes
    `{{#node.field#}}` inside a JSON body reliably, and whether it does the
    same inside the headers field is not something the docs settle — a
    workflow that sends the header literally gets a 401 that looks exactly
    like a wrong token. Accepting both means the DSL can use the path that is
    known to work and the header still works for everything else.
    """
    expected = token()
    from_body = fields.get("tool_token")
    candidates = [c.strip() for c in (header_token(request),
                                      from_body if isinstance(from_body, str)
                                      else None) if c]
    if not candidates:
        raise Bad("no token: send `Authorization: Bearer <token>`, or a "
                  "`tool_token` field in the JSON body", 401)
    if any(c == expected for c in candidates):
        return
    if any(unsubstituted(c) for c in candidates):
        raise Bad("the token arrived as an unfilled template, so whatever "
                  "sent it did not substitute the variable. In Dify, put "
                  "`\"tool_token\": \"{{#<start-node>.tool_token#}}\"` in the "
                  "request body rather than in the headers field.", 401)
    raise Bad("that token is not the one this service was started with", 401)


# ------------------------------------------------------------- the input --

async def body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Bad(f"the body is not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise Bad("the body must be a JSON object")
    return parsed


def profile_from(fields: Any) -> StudentProfile:
    """A StudentProfile, or a 400 saying which field is wrong.

    Dify sends whatever the workflow built, so this is the boundary where a
    malformed profile becomes a readable message instead of a traceback. A
    string is accepted too, because a Dify variable carrying JSON arrives as
    text unless the workflow parsed it first.
    """
    if isinstance(fields, str):
        try:
            fields = json.loads(fields)
        except json.JSONDecodeError as exc:
            raise Bad(f"`profile` is a string but not JSON: {exc}") from exc
    if not isinstance(fields, dict):
        raise Bad("`profile` must be a JSON object")
    try:
        return StudentProfile.model_validate(fields)
    except Exception as exc:                       # pydantic ValidationError
        raise Bad(f"`profile` is not a valid student profile: {exc}") from exc


def rows_from(value: Any) -> list[PlannedCourse]:
    """`plan` as a list of PlannedCourse, however Dify wrapped it."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise Bad(f"`plan` is a string but not JSON: {exc}") from exc
    if isinstance(value, dict):          # a model that wrapped it in {"plan": …}
        value = value.get("plan", value)
    if not isinstance(value, list):
        raise Bad("`plan` must be a JSON array of course rows")
    rows = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise Bad(f"row {index} of `plan` is not an object")
        try:
            rows.append(PlannedCourse.model_validate(row))
        except Exception as exc:
            raise Bad(f"row {index} of `plan` is not a course row: {exc}"
                      ) from exc
    return rows


def programs_for(profile: StudentProfile) -> tuple[Any, Any]:
    if not profile.major:
        raise Bad("`profile.major` is required — this service does not guess "
                  "a program (hard rule 4)")
    try:
        major = T.get_program(profile.major)
    except KeyError as exc:
        raise Bad(f"no program {profile.major!r} in data/program_index.json"
                  ) from exc
    minor = T.get_program(profile.minor) if profile.minor else None
    return major, minor


# ---------------------------------------------------------- the handlers --

async def health(request: Request) -> JSONResponse:
    """Open, so Dify's connection test needs no token."""
    rows = T.list_programs()
    tiers: dict[str, int] = {}
    for row in rows:
        tiers[row["tier"]] = tiers.get(row["tier"], 0) + 1
    return JSONResponse({"ok": True, "service": "course-planner-tools",
                         "cohort": "2026-27", "programs": len(rows),
                         "tiers": tiers, "courses": len(T.catalog())})


async def echo(request: Request) -> JSONResponse:
    """What this service actually received, redacted. For debugging a 401.

    Open, like `/health`, and deliberately not an oracle: it never says
    whether a token is correct, only what shape arrived. That is enough to
    tell the three cases apart — no token sent, a token sent as an unfilled
    `{{...}}` template, or a real token of the wrong length — without giving
    anything away to someone guessing.
    """
    fields = await body(request)
    header = header_token(request)
    in_body = fields.get("tool_token")
    in_body = in_body if isinstance(in_body, str) else None

    def describe(value: str | None) -> dict:
        if value is None:
            return {"present": False}
        return {"present": True, "length": len(value.strip()),
                "looks_like_an_unfilled_template": unsubstituted(value)}

    expected = len(token())
    return JSONResponse({
        "authorization_header": describe(header),
        "tool_token_in_body": describe(in_body),
        "expected_token_length": expected,
        "body_keys": sorted(fields),
        "hint": (
            "Neither place carried a token — in Dify, add "
            "\"tool_token\": \"{{#<start-node>.tool_token#}}\" to the request "
            "body." if not (header or in_body) else
            "The token arrived as an unfilled template, so the variable was "
            "not substituted. Put it in the JSON body rather than the headers "
            "field." if unsubstituted(header or in_body or "") else
            f"A token arrived. If calls still fail, it is the wrong value: "
            f"this service expects {expected} characters.")})


async def search_courses(request: Request) -> JSONResponse:
    """Keyword search over the catalog. The only source of real course codes."""
    fields = await body(request)
    authorise(request, fields)
    query = str(fields.get("query") or "").strip()
    if not query:
        raise Bad("`query` is required")
    level = fields.get("level")
    found = T.search_courses(
        query,
        subject=(str(fields["subject"]).strip().upper()
                 if fields.get("subject") else None),
        level=int(level) if level not in (None, "") else None,
        limit=min(int(fields.get("limit") or SEARCH_LIMIT), 100))
    return JSONResponse({"query": query, "count": len(found), "courses": [
        {"code": c.code, "title": c.title, "credits": c.credits,
         "prerequisite": c.prereq_expr,
         "common_core_areas": c.common_core_areas} for c in found]})


async def get_program(request: Request) -> JSONResponse:
    """One program's requirements, rendered the way the planner reads them."""
    fields = await body(request)
    authorise(request, fields)
    code = str(fields.get("code") or "").strip()
    if not code:
        raise Bad("`code` is required")
    try:
        program = T.get_program(code)
    except KeyError as exc:
        raise Bad(f"no program {code!r} in data/program_index.json") from exc
    return JSONResponse({
        "code": program.code, "title": program.title,
        "tier": program.tier.value, "verified_on": program.verified_on,
        "cohort": program.cohort, "source_url": program.source_url,
        "stated_total_credits": program.stated_total_credits,
        "max_double_count_credits": program.max_double_count_credits,
        "plannable": program.tier.value != "unsupported",
        "requirements": describe_program(program, T.catalog()),
        "caveats": program.caveats,
        "unparsed_lines": program.unparsed_lines})


async def draft_plan(request: Request) -> JSONResponse:
    """A complete, feasible plan built by code. The workflow starts here."""
    fields = await body(request)
    authorise(request, fields)
    profile = profile_from(fields.get("profile"))
    major, minor = programs_for(profile)
    if major.tier.value == "unsupported":
        raise Bad(f"{major.code} is tier `unsupported` — it cannot be planned "
                  f"reliably and no plan will be produced for it (hard rule 5)",
                  422)
    rows = T.draft_plan(profile, major, minor,
                        spread=fields.get("spread") or profile.spread)
    # The validator's own tally, not a second implementation of it: a slot
    # carries its credits and this read the catalog alone, so the two would
    # disagree the moment a plan held anything but real courses.
    from planner.validate import term_credits
    per_term = term_credits(rows, T.catalog())
    return JSONResponse({
        "program": major.code, "tier": major.tier.value,
        "count": len(rows), "per_term": per_term,
        "plan": [row.model_dump(exclude_defaults=True) for row in rows]})


async def validate(request: Request) -> JSONResponse:
    """Every check in `planner/validate.py`, for a plan Dify has written.

    This is the endpoint that keeps hard rule 2 true on Dify's side of the
    wire: the workflow can ask whether what it just wrote is allowed out, and
    loop on the answer, instead of returning a plan nobody checked.
    """
    fields = await body(request)
    authorise(request, fields)
    profile = profile_from(fields.get("profile"))
    rows = rows_from(fields.get("plan"))
    major, minor = programs_for(profile)
    report = validate_plan(rows, profile, major=major, minor=minor)

    def issues(group) -> list[dict]:
        return [{"check": i.check, "message": i.message,
                 "course": i.course, "term": i.term} for i in group]

    return JSONResponse({
        "ok": report.ok,
        "error_count": len(report.errors),
        "warning_count": len(report.warnings),
        "errors": issues(report.errors),
        "warnings": issues(report.warnings),
        "infos": issues(report.infos),
        "per_term": report.per_term,
        # `confirmed` is what counts towards 120 today; exchange credits are
        # listed apart because they are pending approval and are never shown
        # as met until the mapping is approved (hard rule 6).
        "credits": {"earned": report.credits.earned,
                    "planned": report.credits.planned,
                    "unspecified_transfer":
                        report.credits.unspecified_transfer,
                    "exchange_pending": report.credits.exchange_pending,
                    "confirmed": report.credits.confirmed,
                    "with_exchange": report.credits.with_exchange}})


# -------------------------------------------------------------- the app --

async def on_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, Bad):
        return JSONResponse({"error": exc.message}, status_code=exc.status)
    return JSONResponse({"error": f"{type(exc).__name__}: {exc}"},
                        status_code=500)


ROUTES = [
    Route("/health", health, methods=["GET"]),
    Route("/debug/echo", echo, methods=["POST"]),
    Route("/tools/search_courses", search_courses, methods=["POST"]),
    Route("/tools/get_program", get_program, methods=["POST"]),
    Route("/tools/draft_plan", draft_plan, methods=["POST"]),
    Route("/tools/validate_plan", validate, methods=["POST"]),
]

app = Starlette(routes=ROUTES,
                exception_handlers={Exception: on_error, Bad: on_error})


def main(argv: list[str] | None = None) -> int:
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1",
                    help="127.0.0.1 keeps it off the network (default). Use "
                         "0.0.0.0 only when Dify runs in a container that "
                         "has to reach it.")
    ap.add_argument("--port", type=int, default=8601)
    args = ap.parse_args(argv)

    token()        # fail now, with the reason, rather than on the first call
    print(f"tools on http://{args.host}:{args.port}  "
          f"(health is open, /tools/* needs the Bearer token)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
