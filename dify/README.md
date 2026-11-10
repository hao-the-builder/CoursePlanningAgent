# The Dify backend

Two files here, and one service in the repo:

| | |
|---|---|
| `course-planner.yml` | the workflow, as a Dify DSL export you import |
| `openapi.json` | the same four tools as an OpenAPI schema, if you'd rather build an **Agent node** than the fixed graph |
| `../service/tool_api.py` | the tools themselves — the deterministic half, over HTTP |

**Step-by-step instructions are in `SETUP.md`.** This file is the reasoning behind the design.

## Why it is built this way

Dify runs its agent loop on its own server and **never hands a tool call back
to the caller**. The Service API returns a finished answer; the only point a
run pauses for the client is a Human Input node, which is for a person filling
a form. So the tools cannot stay in Python and be called by Dify — they have to
be *reachable from* Dify. That is what `service/tool_api.py` is.

Three things deliberately stay on this side of the wire:

- **The data.** Nothing about HKUST is uploaded to Dify. The workflow asks the
  tool service for every course code, credit value and requirement rule, so
  there is one copy of the catalog and it is the one in `data/`.
- **The last word on validity.** The workflow validates its own plan — that is
  how its repair pass works — but `planner/dify.py` re-runs `validate_plan`
  locally on whatever comes back and reports *that* verdict. A plan is never
  shown on the strength of a remote check (hard rule 2). If the two verdicts
  disagree, that is reported too: it means the workflow is reading a different
  tool service or stale data.
- **The refusal.** An `unsupported` program is refused before a request is
  sent, and again by the service if one is sent anyway (hard rule 5).

**There is no secret in `course-planner.yml`.** The tool service's base URL and
token are Start-node inputs supplied at run time, not values baked into the
file, so the artifact you hand in carries no credential (hard rule 8).

## The graph

```
Start ─► get_program ─► draft_plan ─► LLM shape ─► read ─► validate
                                                              │
                                              ┌───────────────┘
                                              ▼
                            read verdict ─► LLM repair ─► read ─► validate ─► assemble ─► End
```

`draft_plan` returns a complete, legal plan built by code. The first LLM
*shapes* it to the student — moving and swapping rows — and is told that every
code it writes must already appear in that draft. The validator then checks it,
and the repair pass is given the real error list and told to return the plan
untouched if the verdict is already clean.

**The repair pass always runs**, even when the first plan is clean. Dify's
workflow graph is a DAG, and a conditional loop back to an earlier node is not
expressible in a DSL shape I could verify against a real export — so rather
than hand-author a `loop` node from prose docs alone, the cycle is unrolled
into one fixed pass. `planner/agent.py` keeps the thorough version: up to five
retries, driven locally. If you want more passes here, copy nodes 1708–1710 and
chain them; the tests will tell you if the wiring is wrong.

Both `code` nodes that read a model reply **fall back to the previous plan**
rather than passing junk to the validator, so a reply the parser cannot read
costs you the shaping, not the run.

## Setting it up

### 1. Start the tool service

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"   # the token
```

Put it in `.env` as `TOOL_API_TOKEN` (never in git), then:

```bash
# self-hosted Dify in Docker needs the service on a reachable interface
TOOL_API_TOKEN=... python -m service.tool_api --host 0.0.0.0 --port 8601
```

Check it: `curl http://localhost:8601/health` should report 129 programs and
`"verified": 5`. `/health` is open on purpose, so Dify's connection test needs
no token; everything under `/tools/` requires the bearer token.

### 2. Import the workflow

Dify → **Create app** → **Import DSL** → upload `course-planner.yml`.

It imports at DSL version `0.1.5`, which is below Dify's current `0.7.0`, so
expect a *"completed with warnings"* notice and let Dify migrate it. That is
the intended path: every node shape in the file was copied from a real `0.1.x`
export, and declaring a version whose shapes I could not verify would be worse
than being migrated.

### 3. Pick the model

Both LLM nodes are written as:

```yaml
model:
  provider: anthropic
  name: claude-opus-5-5
  mode: chat
  completion_params: {temperature: 0}
```

**This is the one thing you may have to change by hand.** If your workspace
installed Anthropic as a plugin, Dify expects the full path
(`langgenius/anthropic/anthropic`) and will flag the node — open each LLM node
and re-pick the model from the dropdown, which rewrites it correctly. Dify's
own docs do not confirm which form the current editor writes, so this is left
for you to resolve in the UI rather than guessed at here.

Note that Dify has **no per-request model override** — `inputs` only carries
the app's own variables. So CLAUDE.md's `MODEL_FAST` / `MODEL_STRONG` split
does not survive this route: both nodes name one model. Give them different
models in the UI if you want the split back.

### 4. Run it

In the Dify UI, the four inputs are:

| input | value |
|---|---|
| `major` | `COMP` |
| `profile_json` | `{"cohort":"2026-27","major":"COMP","workload_min":12,"workload_max":18,"spread":"front","free_terms":["Y4 Spring"]}` |
| `tool_base` | `http://host.docker.internal:8601` (self-hosted) or your tunnel URL |
| `tool_token` | the `TOOL_API_TOKEN` value |

Or from this repo, which also re-validates the answer locally:

```bash
python -m planner.dify tests/profiles/01-comp-correct.json
```

It prints the run id, the local verdict, and a loud warning if Dify's verdict
disagreed with it.

## The Agent-node alternative

If you want Dify's own agent loop choosing *when* to call each tool, rather
than the fixed graph:

1. Dify → **Tools** → **Custom** → **Import from OpenAPI**, and paste
   `openapi.json`.
2. Set the auth to **Bearer** with your `TOOL_API_TOKEN`.
3. Build an app with an **Agent node**, attach the four tools, and use the
   system prompt from the `LLM · shape the plan` node in `course-planner.yml`
   as a starting point.

That is closer to "agentic" in the loose sense, and it trades the graph's
guarantees for the model's judgement: nothing then forces `validate_plan` to
run before the answer comes out. `planner/dify.py` still re-validates locally,
so hard rule 2 holds either way — but with the fixed graph the model also
can't skip its own check.

## What the tests cover

`tests/test_dify_workflow.py` reads this YAML and checks what makes an import
fail or a run break quietly: the fields Dify's importer requires, a `version`
that is a quoted string, edges that join real nodes, no cycles and no orphans,
every `{{#node.field#}}` reference pointing at a node that is genuinely
upstream, each `code` node's declared outputs matching what its Python returns
on *every* branch, inputs matching the `main()` signature, only stdlib imports,
HTTP nodes posting to endpoints `service/tool_api.py` really serves, request
bodies that are still valid JSON once the variables are substituted, and no
secret in the file.

`tests/test_tool_api.py` runs the service against the real `data/`.
`tests/test_dify_client.py` fakes Dify and checks the half this repo owns —
including the case that matters most: Dify claiming `ok: true` while returning
an invented course, and the local validator overruling it.
