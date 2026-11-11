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

**Any chat model works.** The file names a Claude model because that is what
it was written against, but nothing in the workflow depends on it: the two LLM
boxes only reorder rows that the tool service already supplied and write a few
sentences of rationale. Every course code, credit figure and rule comes from
the service, the validator checks the model's output either way, and the `code`
box after each LLM box falls back to the code-built plan if the reply will not
parse. So use whichever model your Dify can actually reach — and say in your
write-up which one you used.

The workflow cannot know how your Dify is set up, so check this by hand.

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

> **Use this profile for your first run.** The plan the code builds for it
> already passes every check, so a clean result proves the plumbing works.
>
> **For a second run, ask for something impossible.** Add `"Y4 Fall"` to
> `free_terms` so it reads `["Y4 Fall","Y4 Spring"]`. That leaves six terms to
> carry a 120-credit degree, which needs 20 credits a term against an
> 18-credit cap in the Academic Regulations, so no arrangement of courses can
> satisfy it. You get `"ok": false` and twelve errors naming the exact
> overload in each term. **That is the better demo**: it shows the system
> refusing to present a plan that breaks a rule, which is the one property
> nobody can check by reading the output. A plan that cannot exist is the
> hardest thing for an agent to admit.

**What a good result looks like.** The End box gives you one value called
`result`, holding something like:

```json
{
 "ok": true,
 "plan": [ { "code": "COMP 2011", "term": "Y1 Fall", "status": "planned" },
           { "code": "SLOT:FREE-1-3CR", "term": "Y2 Fall", "status": "planned" }, ... ],
 "rationale": "Front-loaded the first two years so Y4 Spring is free...",
 "program": { "code": "COMP", "tier": "verified", "verified_on": "2026-11-09" },
 "validation": { "ok": true, "error_count": 0, "warnings": [...] },
 "caveat": "Check this plan with your academic advisor before you register."
}
```

`"ok": true` means the plan passed every check. That line comes from the
checker, not from the model talking about itself.

**The `SLOT:` rows are deliberate.** A free elective is your choice, not the
planner's: the requirements say only "and enough credits to reach 120". Each
slot states its size in its own code — `SLOT:FREE-1-3CR` is three credits —
and those credits count toward the 120, so the totals are complete while the
choice stays open. The `.docx` is where two or three real options for each one
belong. Earlier versions filled these with real course codes taken off the top
of an alphabetical list, which is how a Computer Science plan ended up holding
four accounting courses.

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

---

## 10. Letting other people test it

> **For a link reviewers can use, follow `dify/DEPLOY.md` instead.** It is the
> same ground as this section but written click by click, including the
> hosting account, the eight fields that have to be repointed in Dify, and
> how to stop a free service falling asleep mid-review. This section is the
> short version and the reasoning.

Publishing in Dify is one click. The thing that breaks is the one you cannot
see from inside Dify: **`tool_base` points at your laptop.** A published app
whose `tool_base` is a quick tunnel works for exactly as long as your machine
is awake and that tunnel is alive - and a quick tunnel is deregistered without
warning. A tester who opens the link tomorrow gets a connection error on every
`Tool ·` box.

So before sharing a link, two things have to change.

### 10a. The token must stop being an input

Right now `tool_token` is a Start variable, which means **every tester has to
be told your token, and can read it.** They can also point `tool_base` at a
server of their own. Neither is acceptable once the link leaves your hands.

Dify has workflow **environment variables** for exactly this - string, number
and secret types, referenced from any node. Move `tool_base` to a string and
`tool_token` to a **secret**, then open each of the four `Tool ·` nodes and
repoint the body fields at the environment variable instead of the Start
variable.

> Pick the variable from Dify's own variable picker rather than typing the
> reference by hand. The template form is easy to get subtly wrong, and a
> reference that does not resolve arrives at this service as the literal text
> `{{#...#}}` - which it will tell you about, in those words, rather than
> leaving you to guess at a 401.

Testers are then left with the two inputs that are actually theirs: `major`
and `profile_json`.

### 10b. The service needs a home that is not your laptop

| | Works while you are offline | Address changes | Setup |
|---|---|---|---|
| **Deploy the service** | Yes | No | A hosting account, ~15 min |
| **Named Cloudflare tunnel** | No | No | A Cloudflare account, ~10 min |
| **Testers run the repo** | Yes, on their machine | n/a | None for you |

**Deploy it.** There is a `Dockerfile` in the repo root that builds the tool
service alone - four packages, no Streamlit, no model SDKs, because nothing
here calls a model. Any container host works the same way: point it at this
repo, let it build the Dockerfile, set `TOOL_API_TOKEN` in the host's secret
store, and it serves on whatever port the host assigns through `$PORT`.

Then check `https://your-service/health` in a browser - it is open on purpose,
so a tester or a grader can confirm the data side is up without a token - and
put that address in the `tool_base` environment variable.

> **Free tiers usually sleep.** A free instance commonly spins down after
> about 15 minutes idle and takes up to a minute to wake. The first Dify run
> after a quiet spell can therefore time out on the first `Tool ·` box and
> succeed on a retry. Opening `/health` first wakes it. Say this in whatever
> note you send with the link, or a tester will read a cold start as a broken
> app.

**Named Cloudflare tunnel**, if you would rather not deploy: `cloudflared
tunnel login`, then `cloudflared tunnel create course-planner`, then route a
hostname you own to it. The address stops changing, which is the one thing
quick tunnels get wrong. Your machine still has to be running, so this suits a
demo at a known time rather than a link someone opens whenever.

**Testers run the repo.** Worth remembering as the fallback: this project's own
Streamlit app needs no Dify and no tunnel, because the data ships with the
code. `pip install -r requirements.txt`, then `streamlit run app.py`. What they
lose is the Dify workflow - which is the part you are submitting, so this is a
complement to a shared link, not a substitute for one.

### 10c. Then publish

**Publish** in the app, then open the app's overview and find the web-app URL
and its accessibility setting. Make it public if you want anyone with the link
to run it. Send testers the link, the two inputs they need, and one line about
the cold start.

A profile they can paste:

```json
{"cohort":"2026-27","major":"COMP","workload_min":12,"workload_max":18,"spread":"even","free_terms":["Y4 Spring"]}
```

And `COMP`, `MATH-AM`, `FINA`, `GCS-SS` or `IDT` for `major` - those five are
the verified programs. Anything else is honest about its data tier or refuses.
