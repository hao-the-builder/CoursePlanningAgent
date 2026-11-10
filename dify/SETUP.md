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
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy what it prints. Open `.env` in this repo and add the line:

```
TOOL_API_TOKEN=paste-what-was-printed-here
```

`.env` is ignored by git, so the token never leaves your computer.

**Start the service.** Leave this terminal open — it has to keep running.

```powershell
$env:TOOL_API_TOKEN = "paste-the-same-token-here"
.venv\Scripts\python.exe -m service.tool_api --host 0.0.0.0 --port 8601
```

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
installation.

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
{"cohort":"2026-27","major":"COMP","workload_min":12,"workload_max":18,"spread":"front","free_terms":["Y4 Spring"]}
```

Press run and watch the boxes light up one by one.

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
| A `Tool ·` box returns **401** | Wrong token | The `tool_token` you typed must exactly match `TOOL_API_TOKEN` in the service terminal |
| A `Tool ·` box returns **422** with *unsupported* | That program's rules could not be read reliably, so it refuses to plan it | Use a program that works: `COMP`, `MATH-AM`, `FINA`, `GCS-SS`, `IDT` |
| A `Tool ·` box returns **400** with *not valid JSON* | `profile_json` is malformed | Paste the example from step 6 again; it must be one line of valid JSON |
| An `LLM ·` box is red | No model picked, or no provider set up | Step 5 |
| Result has `"ok": false` and a list of errors | The workflow ran correctly and the plan genuinely breaks a rule | Read the errors; this is the system working, not failing |
| `result` says *the model's reply could not be read* | The model did not answer with clean JSON | It fell back to the code-built plan on purpose. Re-run; if it keeps happening, try a stronger model |

**Still stuck?** The service terminal prints every request it receives. If a
box in Dify fails and nothing appears there, the request never arrived, so the
problem is the address or the tunnel — not the service.
