"""Backend-agnostic LLM wrapper (Phase 4).

One call, `chat(...)`, three backends chosen by `LLM_BACKEND`:

  `subscription`  the Claude Agent SDK, driving the developer's own Claude
                  plan through the local `claude` CLI. Local development only.
  `api`           the `anthropic` SDK with `ANTHROPIC_API_KEY`. The deployed
                  demo (Phase 7) uses this, with the key in Streamlit secrets.
  `stub`          no model at all. It answers from the same deterministic
                  tools the real backends are given, so the agent loop, the
                  validator, the retries and the outputs can all be tested
                  offline and for free. It is a test double, not a model: it
                  writes no prose worth reading and makes no choices.

Model choice follows CLAUDE.md: `MODEL_FAST` for intake and retries,
`MODEL_STRONG` for planning and the document.

Both SDK surfaces were checked against their current documentation rather
than from memory, which changed three things that an older habit would have
got wrong: thinking is `{"type": "adaptive"}` with `output_config.effort`
rather than a token budget; `tool_choice` may not be forced on this model
family, so the prompt asks for the tool instead; and the Agent SDK takes
custom tools through an in-process MCP server, with `setting_sources=[]` so
it does not read this repository's own CLAUDE.md and start following the
phase plan.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent
PROMPTS = REPO / "planner" / "prompts"

DEFAULT_BACKEND = "stub"
MODEL_STRONG = "claude-opus-5-5"
MODEL_FAST = "claude-haiku-5-5"
MAX_TOOL_TURNS = 12


class LLMUnavailable(RuntimeError):
    """The chosen backend cannot run here. Says what to do about it."""


@dataclass(frozen=True)
class ToolSpec:
    """A deterministic tool the model may call. The model never gets data any
    other way, so every fact in an output traces back to one of these."""

    name: str
    description: str
    schema: dict
    run: Callable[[dict], str]


@dataclass
class Reply:
    text: str
    backend: str
    model: str
    turns: int = 1
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    cost_usd: float | None = None
    stop_reason: str | None = None

    def json(self) -> Any:
        """The reply parsed as JSON, tolerating a fenced code block."""
        text = self.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text.split("\n", 1)[1] if text.lower().startswith("json") \
                else text
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"no JSON object in the reply: {self.text[:200]!r}")
        return json.loads(text[start:end + 1])


# ------------------------------------------------------------- settings --

def _env(name: str, fallback: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or fallback


def backend_name() -> str:
    return _env("LLM_BACKEND", DEFAULT_BACKEND).lower()


def model_for(task: str) -> str:
    """MODEL_FAST for intake and retries, MODEL_STRONG for the real work."""
    fast = {"intake", "retry", "slots"}
    return (_env("MODEL_FAST", MODEL_FAST) if task in fast
            else _env("MODEL_STRONG", MODEL_STRONG))


def prompt_text(name: str, **fields: Any) -> str:
    """One of planner/prompts/*.md, with its $placeholders filled in.

    `string.Template` rather than `str.format`, because these prompts are
    full of JSON examples and doubling every brace to escape them would make
    them unreadable.
    """
    from string import Template

    raw = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return Template(raw).safe_substitute(**fields) if fields else raw


# -------------------------------------------------------------- backends --

def _run_tool(tools: Sequence[ToolSpec], name: str, arguments: dict) -> str:
    for tool in tools:
        if tool.name == name:
            try:
                return tool.run(arguments)
            except Exception as exc:                 # noqa: BLE001
                return f"ERROR: {type(exc).__name__}: {exc}"
    return f"ERROR: no tool named {name!r}"


def _chat_stub(prompt: str, *, task: str, system: str,
               tools: Sequence[ToolSpec], **_: Any) -> Reply:
    """Answer from the tools, with no model in the loop.

    For a planning task it calls the `draft_plan` tool the agent registered —
    the same tool a real backend would reach for — and returns its JSON. For
    anything else it says plainly that no model ran, so a stub run is never
    mistaken for a real one in an output.
    """
    names = {t.name for t in tools}
    if task in {"plan", "retry"} and "draft_plan" in names:
        wanted = 3
        for marker in ("# Plan 1 paths", "# Plan 2 paths"):
            if marker in prompt:
                wanted = int(marker.split()[2])
        shapes = [("even", "Even load throughout"),
                  ("front", "Front-loaded, lighter final year"),
                  ("back", "Back-loaded, gentle start")][:wanted]
        calls, paths = [], []
        for spread, name in shapes:
            calls.append(("draft_plan", {"spread": spread}))
            paths.append({
                "name": name,
                "summary": f"A feasible {spread}-weighted plan built by code "
                           f"from the requirement rules. No model wrote this.",
                "why_it_fits": [f"The workload shape asked for was {spread}."],
                "trade_offs": ["Generated without a model, so nothing here is "
                               "tailored to what the student said."],
                "plan": json.loads(_run_tool(tools, "draft_plan",
                                             {"spread": spread})),
                "slot_suggestions": {},
            })
        return Reply(text=json.dumps({"paths": paths}), backend="stub",
                     model="none", tool_calls=calls)
    if task == "prose":
        return Reply(text="(No model ran: LLM_BACKEND=stub. This text is a "
                          "placeholder, not advice.)",
                     backend="stub", model="none")
    return Reply(text="", backend="stub", model="none")


def _chat_api(prompt: str, *, task: str, system: str, model: str,
              tools: Sequence[ToolSpec], max_tokens: int, effort: str) -> Reply:
    """The `anthropic` SDK, with a hand-written tool loop."""
    try:
        import anthropic
    except ImportError as exc:                       # pragma: no cover
        raise LLMUnavailable("the `anthropic` package is not installed; "
                             "pip install -r requirements.txt") from exc
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMUnavailable(
            "LLM_BACKEND=api needs ANTHROPIC_API_KEY. Put it in .env for "
            "local use, or in Streamlit secrets when deployed — never in git "
            "(hard rule 8).")

    client = anthropic.Anthropic()
    definitions = [{"name": t.name, "description": t.description,
                    "input_schema": t.schema, "strict": True} for t in tools]
    messages: list[dict] = [{"role": "user", "content": prompt}]
    calls: list[tuple[str, dict]] = []

    for turn in range(1, MAX_TOOL_TURNS + 1):
        request: dict[str, Any] = {
            "model": model, "max_tokens": max_tokens, "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
        if system:
            request["system"] = system
        if definitions:
            request["tools"] = definitions
        response = client.messages.create(**request)

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            raise LLMUnavailable(
                f"the model declined this request "
                f"({getattr(detail, 'category', 'unspecified')}).")

        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content
                           if getattr(b, "type", "") == "text")
            return Reply(text=text, backend="api", model=model, turns=turn,
                         tool_calls=calls, stop_reason=response.stop_reason)

        results = []
        for block in response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            calls.append((block.name, dict(block.input)))
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": _run_tool(tools, block.name,
                                                 dict(block.input))})
        messages.append({"role": "user", "content": results})

    raise LLMUnavailable(f"gave up after {MAX_TOOL_TURNS} tool turns")


def _chat_subscription(prompt: str, *, task: str, system: str, model: str,
                       tools: Sequence[ToolSpec], max_tokens: int,
                       effort: str) -> Reply:
    """The Claude Agent SDK, on the developer's own plan. Local only."""
    try:
        import asyncio

        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            ToolUseBlock,
            create_sdk_mcp_server,
            query,
        )
        from claude_agent_sdk import tool as sdk_tool
    except ImportError as exc:                       # pragma: no cover
        raise LLMUnavailable("the `claude-agent-sdk` package is not "
                             "installed; pip install -r requirements.txt"
                             ) from exc

    calls: list[tuple[str, dict]] = []

    def wrap(spec: ToolSpec):
        @sdk_tool(spec.name, spec.description, spec.schema)
        async def handler(arguments: dict) -> dict:
            # The call is recorded from the ToolUseBlock below, not here, or
            # every call would be counted twice.
            return {"content": [{"type": "text",
                                 "text": _run_tool(tools, spec.name, arguments)}]}
        return handler

    server = create_sdk_mcp_server(name="planner", version="1.0.0",
                                   tools=[wrap(t) for t in tools])

    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system or None,
        mcp_servers={"planner": server},
        allowed_tools=[f"mcp__planner__{t.name}" for t in tools],
        # No built-in tools: this agent plans courses, it does not read the
        # filesystem. And no setting sources, so the Agent SDK does not load
        # this repository's own CLAUDE.md and try to follow the phase plan.
        tools=[],
        setting_sources=[],
        permission_mode="default",
        max_turns=MAX_TOOL_TURNS,
    )

    async def run() -> Reply:
        text_parts: list[str] = []
        cost: float | None = None
        turns = 0
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                turns += 1
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        calls.append((block.name, dict(block.input)))
            elif isinstance(message, ResultMessage):
                cost = message.total_cost_usd
                if message.is_error:
                    raise LLMUnavailable(
                        f"the Claude Agent SDK ended with "
                        f"{message.subtype}: {message.result}")
                if message.result:
                    text_parts = [message.result]
        return Reply(text="\n".join(text_parts).strip(), backend="subscription",
                     model=model, turns=turns, tool_calls=calls, cost_usd=cost)

    try:
        return asyncio.run(run())
    except LLMUnavailable:
        raise
    except FileNotFoundError as exc:                 # pragma: no cover
        raise LLMUnavailable(
            "the Claude Agent SDK could not start the `claude` CLI. Install "
            "Claude Code and sign in, or set LLM_BACKEND=api.") from exc


BACKENDS = {"stub": _chat_stub, "api": _chat_api,
            "subscription": _chat_subscription}


def chat(prompt: str, *, task: str = "plan", system: str = "",
         tools: Sequence[ToolSpec] = (), model: str | None = None,
         max_tokens: int = 16000, effort: str = "high",
         backend: str | None = None) -> Reply:
    """Ask the configured backend one question.

    `task` picks the model (fast for intake and retries, strong for planning
    and prose) and tells the stub backend what shape of answer to give.
    """
    name = (backend or backend_name()).lower()
    if name not in BACKENDS:
        raise LLMUnavailable(
            f"LLM_BACKEND={name!r} is not one of {sorted(BACKENDS)}")
    return BACKENDS[name](prompt, task=task, system=system,
                          model=model or model_for(task), tools=tools,
                          max_tokens=max_tokens, effort=effort)
