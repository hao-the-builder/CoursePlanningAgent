# Setting it up on Dify — step by step

Plain instructions, in order. Commands are written for Windows, which is what
this repo is developed on. For *why* it is built this way, see
`dify/README.md`; this file is only how to make it run.

Allow about 30 minutes the first time.

---

## 0. What you are building

Three things talk to each other:

```
   YOUR DIFY WORKFLOW                 THIS REPO
   ┌──────────────────┐               ┌─────────────────────┐
   │ asks the model   │  ──HTTP──►    │ tool service        │
   │ to shape a plan  │  ◄────────    │ (holds the data)    │
   └──────────────────┘               └─────────────────────┘
```

- **The tool service** runs on your computer. It holds the HKUST course data
  and answers four questions: search courses, get a program's rules, build a
  draft plan, check a plan.
- **The Dify workflow** is the agent. It asks the model to shape the plan, then
  checks it against the tool service, then asks the model to fix any problems.
- **No course data is uploaded to Dify.** Dify asks your service every time.

So the order is always: start the service first, then run the workflow.

---

## 1. Choose where Dify runs

This is the only decision that changes the steps.

| | Your own Dify (Docker) | Dify Cloud |
|---|---|---|
| Can it reach your computer? | Yes, directly | No — needs a tunnel |
| Extra setup | Install Docker, run Dify | Install a tunnel tool |
| Easier overall | **Yes, recommended** | Fewer installs, more fiddling |

**Pick your own Dify if you can.** Your computer and Dify are then on the same
machine, so nothing has to be exposed to the internet.

### If you chose your own Dify

Install Docker Desktop, then:

```powershell
git clone --depth 1 https://github.com/langgenius/dify.git
cd dify\docker
copy .env.example .env
docker compose up -d
```

Open <http://localhost/install> in a browser, create the admin account, and
sign in. Dify is now at <http://localhost>.

### If you chose Dify Cloud

Sign up at <https://dify.ai>. Nothing else for now — step 3 handles the
tunnel.

---

## 2. Start the tool service

Open a terminal in this repo.

**Make a token.** This is a password that only your service and your workflow
know, so nobody else can call your service.

```powershell
.venv\Scripts\python.exe -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(43)))"
```

Letters and digits only, on purpose. `secrets.token_urlsafe` also emits `-`
and `_`, and a token that *begins* with one of those is a trap: the character
is easy to lose when you copy it into a form field, and what you get back is a
401 saying the token is wrong — with no hint that it is only wrong by one
character.

Copy what it prints. Open `.env` in this repo and add the line:

```
TOOL_API_TOKEN=paste-what-was-printed-here
```

`.env` is ignored by git, so the token never leaves your computer.

**Start the service.** Leave this terminal open — it has to keep running.

```powershell
.venv\Scripts\python.exe -m service.tool_api --host 0.0.0.0 --port 8601
```

The service reads the token from `.env`, so there is nothing to type twice.

> **Do not set `$env:TOOL_API_TOKEN` in the terminal as well.** A shell
> variable overrides `.env`, and then editing `.env` changes nothing while the
> service keeps the old value — every call answers **401** and the two sides
> look identical to you. If you have already done it, close that terminal and
> open a fresh one.

> `--host 0.0.0.0` lets Dify's container reach it. If you are not using Docker
> and not using a tunnel, leave it off and it stays private to your computer.

**Check it works.** In a *second* terminal:

```powershell
curl http://localhost:8601/health
```

You should see `"ok":true`, `"programs":129` and `"verified":5`. If you do, the
data side is finished and you never have to touch it again.

---

## 3. Let Dify reach the service

### Your own Dify (Docker)

Nothing to install. Dify's container sees your computer as
`host.docker.internal`, so the address you will type into Dify is:

```
http://host.docker.internal:8601
```

### Dify Cloud

Dify Cloud runs on the internet and cannot see your computer, so you need a
tunnel — a temporary public address that forwards to your service.

Install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/),
then in a third terminal:

```powershell
cloudflared tunnel --url http://localhost:8601
```

It prints an address like `https://random-words-here.trycloudflare.com`. That
is the address you will type into Dify.

Two things to know:

- **The address changes every time you restart the tunnel.** You will have to
  update it in Dify each time.
- **Close the tunnel when you are done.** While it is open, anyone with the
  address can reach your service. It is read-only and needs the token, and the
  course data is public anyway — but there is no reason to leave it open.

---

## 4. Import the workflow

In Dify:

1. Click **Create app**.
2. Choose **Import DSL** (sometimes called *Import from file*).
3. Upload `dify/course-planner.yml` from this repo.

**You will probably see a warning like "imported with warnings."** That is
expected and fine. The file is written in an older version of Dify's format on
purpose, so Dify upgrades it as it imports. Click through it.

You should now see a workflow with 12 boxes joined left to right, starting at
**Start** and ending at **End**.

---

## 5. Give it a model

The workflow asks for Claude, but it cannot know how your Dify is set up, so
check this by hand.

First, make sure a model is available at all: **Settings → Model Provider**.
If nothing is set up, add a provider there (Anthropic if you have an API key
for it; otherwise any provider your Dify offers).

Then in the workflow, click on the box called **LLM · shape the plan**:

- If the model box shows a model name and no warning, you are done.
- If it is empty or shows a red warning, **pick a model from the dropdown.**

Do the same for the box called **LLM · repair pass**.

That is all — picking from the dropdown writes the right settings for your
installation, **as long as the dropdown offers a model that still exists.**

### If the provider only offers old models

Dify's Anthropic plugin carries a **fixed list** of model names, written when
that version of the plugin was published. It never asks Anthropic what exists
today. So if the list stops at Claude Opus 4, Sonnet 4 and Claude 3.5, the
plugin is from before June 2026 — and every model on that list has since been
retired. Picking any of them gives you this:

```
[models] Bad Request Error, Error code: 404 - {'type': 'error', 'error':
{'type': 'not_found_error', 'message': 'model: claude-opus-4-20250514'}}
```

That 404 is Anthropic saying the model is gone. Your key is fine and the
workflow is fine. Retirement dates, for reference: Opus 4 and Sonnet 4 on
15 June 2026, Sonnet 3.7 in February 2026, Claude 3.5 Sonnet in October 2025.

**First, try updating the plugin.** Dify's **Plugins** page → Anthropic →
update. If the Marketplace version is current, the dropdown gains the Claude 5
models and there is nothing else to do.

**If it still only lists old models, add Claude through the
OpenAI-API-compatible provider instead.** Anthropic serves an OpenAI-shaped
endpoint, so the same Anthropic key works — and that provider has no built-in
model list, so you type the name yourself and are never again at the mercy of
the plugin's age.

**Settings → Model Provider → OpenAI-API-compatible → Add Model:**

| Field | Value |
|---|---|
| Model Name | `claude-opus-5-5` |
| API Key | your Anthropic API key |
| API endpoint URL | `https://api.anthropic.com/v1` |
| Completion mode | Chat |
| Model context size | `200000` |
| Upper bound for max tokens | `8192` |

Leave `/chat/completions` off the end of the URL — Dify appends the route
itself. The context and token numbers only cap what Dify will send; the model
allows far more, and this workflow needs a few thousand tokens at most.

Then re-pick the model in **both** LLM boxes, choosing the new
OpenAI-API-compatible entry.

**The current model names**, if you want a cheaper one:

| Model | Name to type | Cost per million tokens, in / out |
|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | $4 / $20 |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | $2 / $10 |
| Claude Haiku 5.5 | `claude-haiku-5-5` | $0.10 / $0.50 |

These names carry **no date suffix** — `claude-opus-5-5` is the whole name. A
name ending in a date, like `claude-opus-4-20250514`, is the old style, and
every model that used it has been retired.

> The compatibility endpoint does not offer extended thinking or prompt
> caching. This workflow uses neither — both LLM boxes only ask for JSON back.

> Both boxes name the same model. Dify cannot be told which model to use per
> request, so if you want a cheaper model for the repair pass, set it here.

---

## 6. Run it

Click **Run** in the top right. Dify asks for four values:

| Field | What to type |
|---|---|
| `major` | `COMP` |
| `profile_json` | the line below, exactly |
| `tool_base` | `http://host.docker.internal:8601` — or your tunnel address |
| `tool_token` | the token from step 2 |

For `profile_json`:

```json
{"cohort":"2026-27","major":"COMP","workload_min":12,"workload_max":18,"spread":"even","free_terms":["Y4 Spring"]}
```

Press run and watch the boxes light up one by one.

> **Use this profile for your first run.** It is chosen because the plan the
> code builds for it already passes every check, so a clean result proves the
> plumbing works. Once it does, try changing `"even"` to `"front"`: that one
> puts Y3 Spring at 19 credits, one over the 18-credit cap in the Academic
> Regulations, and you get to watch the repair pass fix a real error instead of
> an imaginary one. Seeing `"ok": false` on *that* profile is the system
> working.

**What a good result looks like.** The End box gives you one value called
`result`, holding something like:

```json
{
 "ok": true,
 "plan": [ { "code": "COMP 2011", "term": "Y1 Fall", "status": "planned" }, ... ],
 "rationale": "Front-loaded the first two years so Y4 Spring is free...",
 "program": { "code": "COMP", "tier": "verified", "verified_on": "2026-11-09" },
 "validation": { "ok": true, "error_count": 0, "warnings": [...] },
 "caveat": "Check this plan with your academic advisor before you register."
}
```

`"ok": true` means the plan passed every check. That line comes from the
checker, not from the model talking about itself.

---

## 7. Optional: run it from this repo

This proves the full round trip and checks Dify's answer a second time, here,
against the local data.

In Dify, open your app's **API Access** page and copy the API key. Add to
`.env`:

```
DIFY_API_KEY=the-app-key-you-copied
DIFY_BASE_URL=http://localhost/v1
TOOL_API_BASE=http://host.docker.internal:8601
```

(For Dify Cloud, leave `DIFY_BASE_URL` out — it defaults to the cloud — and set
`TOOL_API_BASE` to your tunnel address.)

Then:

```powershell
.venv\Scripts\python.exe -m planner.dify tests\profiles\01-comp-correct.json
```

It prints the run id, how long it took, and the verdict **computed here** —
plus a loud warning if Dify's verdict disagreed with it.

---

## 8. What you hand in

Based on what you said you need to submit — a YAML file and the Dify workflow:

| What | Where |
|---|---|
| **The workflow file** | `dify/course-planner.yml` |
| **The working workflow** | your Dify app — share it, or export it again from Dify once it is running |
| Proof it ran | a screenshot of a finished run, and the `result` JSON |

If you also want to show how it is wired:

- `dify/README.md` — why the design is what it is
- `dify/openapi.json` — the four tools as a standard API description
- this file — how to run it

**The YAML has no password in it.** The service address and token are typed in
when you run it, not stored in the file, so the file is safe to hand in as is.

Two sentences worth having ready, because they are the parts most likely to be
asked about:

> The agent runs as a Dify workflow. It calls out to a small read-only service
> for every course code and every rule, so the course data is never copied into
> Dify and the model cannot invent a course that gets through.

> Every plan is checked by a validator before it is returned, and checked again
> on the client side, so a plan that fails the rules can never be presented as
> if it passed.

---

## 9. If something breaks

| What you see | What it means | Fix |
|---|---|---|
| Import fails immediately | The file was changed, or Dify rejected the format | Re-download `course-planner.yml` from the repo, unedited |
| A `Tool ·` box turns red, error mentions *connection* or *timeout* | Dify cannot reach your service | Is the service terminal still running? Is `tool_base` right? Docker needs `host.docker.internal`, not `localhost` |
| A `Tool ·` box returns **401** | Wrong token. Dify's trace shows the request it sent — compare the token in it, character by character, against `.env`. A token one character short is the usual answer, and a leading `-` or `_` is the usual missing character | The `tool_token` you typed must match `TOOL_API_TOKEN` in `.env`. If it looks right, the service is probably running with an older value from a shell variable — close that terminal, open a new one, start it again |
| A `Tool ·` box returns **422** with *unsupported* | That program's rules could not be read reliably, so it refuses to plan it | Use a program that works: `COMP`, `MATH-AM`, `FINA`, `GCS-SS`, `IDT` |
| A `Tool ·` box returns **400** with *not valid JSON* | `profile_json` is malformed | Paste the example from step 6 again; it must be one line of valid JSON |
| An `LLM ·` box is red | No model picked, or no provider set up | Step 5 |
| An `LLM ·` box gives **404** `not_found_error` naming a model with a date in it, like `claude-opus-4-20250514` | The provider plugin's model list is older than the models. That one is retired | Step 5, *If the provider only offers old models* — update the Anthropic plugin, or add `claude-opus-5-5` by name through the OpenAI-API-compatible provider |
| An `LLM ·` box gives **400** mentioning `temperature` | The model rejects sampling parameters | Open the node and clear `temperature` from its settings |
| Result has `"ok": false` and a list of errors | The workflow ran correctly and the plan genuinely breaks a rule | Read the errors; this is the system working, not failing |
| `result` says *the model's reply could not be read* | The model did not answer with clean JSON | It fell back to the code-built plan on purpose. Re-run; if it keeps happening, try a stronger model |

**Still stuck?** The service terminal prints every request it receives. If a
box in Dify fails and nothing appears there, the request never arrived, so the
problem is the address or the tunnel — not the service.
