# Putting it online for reviewers — click by click

`SETUP.md` is for running this on your own machine. This file is for the other
job: a link that works while your laptop is shut, for the whole review window.

Three phases, about 45 minutes the first time.

1. **Put the tool service online** — so Dify can reach the course data from
   anywhere.
2. **Wire Dify to it** — and hide your token from reviewers.
3. **Publish, and keep it awake.**

The host below is **Hugging Face Spaces**: free, no credit card, and it runs
the `Dockerfile` this repo already has. If you would rather use Render or
anything else that builds a Dockerfile, the appendix at the bottom has the
settings; everything from Phase 2 onwards is identical.

---

## Before you start

**Your tool token.** Open `.env` in a text editor and copy everything after
`TOOL_API_TOKEN=` — 43 letters and digits. You will paste it once, into Hugging
Face's secret store, and once into Dify's. Never into a form field a reviewer
can see, and never into a file.

---

# Phase 1 · Put the tool service online

The tool service holds the course data and answers Dify's questions. It runs
on your laptop today, which is why your current link dies when you close it.

## 1.1 Build the folder to upload

A Space has to be **public** for Dify to call it without credentials, and this
repo is private. Publishing all of it would publish the source PDFs, the
tests and your coursework documents too — so build a folder with only the
service and the data it reads:

```powershell
.venv\Scripts\python.exe scripts\make_space.py
```

It prints what it wrote: 158 files, about 1.9 MB, in `deploy\space`. It leaves
out `raw/`, `tests/`, `outputs/`, `pipeline/`, `app.py` and every document in
the repo root. `deploy/` is gitignored, so this never lands in your repo.

## 1.2 Make an account

Sign up at <https://huggingface.co/join>. Email and password; no card.

## 1.3 Create the Space

1. Click your avatar (top right) → **New Space**.
2. Fill in:

| Field | What to choose |
|---|---|
| **Space name** | `course-planner-tools` |
| **License** | anything; `mit` is fine |
| **Space SDK** | **Docker**, then the **Blank** template |
| **Space hardware** | **CPU basic · 2 vCPU · 16 GB · FREE** |
| **Visibility** | **Public** |

3. Click **Create Space**.

> **Public is required, not a preference.** Dify calls this service over the
> internet with no Hugging Face credentials, so a private Space would refuse
> it. What becomes public is the service and HKUST's already-public course
> data — which is why step 1.1 exists.

You will land on a page saying the Space is empty and showing git commands.
Leave that tab open.

## 1.4 Put your token in the Space's secret store

1. On the Space page, click **Settings**.
2. Scroll to **Variables and secrets** → **New secret**.
3. Name it `TOOL_API_TOKEN`, paste the 43 characters as the value, and save.

Use **secret**, not variable. A secret is hidden after saving and is passed to
the container as an environment variable, which is where the service reads it.

**The service refuses to start without this**, deliberately — otherwise it
would answer anyone who found the address.

## 1.5 Get a token for pushing files

Hugging Face will not accept your account password over git. You need an
access token:

1. Click your avatar → **Access Tokens** (or go to
   <https://huggingface.co/settings/tokens>).
2. **Create new token** → type **Write** → name it anything → **Create**.
3. Copy it. It starts with `hf_`. You will paste it in the next step.

This is a *different* token from `TOOL_API_TOKEN`. One lets you upload files;
the other protects your service.

## 1.6 Upload the folder

Open a terminal in this repo and run these, replacing `YOUR-USERNAME` with
your Hugging Face username:

```powershell
cd deploy\space
git init -b main
git add -A
git commit -m "Course planner tool service"
git remote add origin https://huggingface.co/spaces/YOUR-USERNAME/course-planner-tools
git push -u origin main
```

The push asks for credentials:

- **Username:** your Hugging Face username
- **Password:** the `hf_...` token from 1.5 — *not* your account password

> On Windows a credential dialog may appear instead of a prompt in the
> terminal. Same answers: username, then the token in the password box.

Then come back to the repo root for later steps:

```powershell
cd ..\..
```

## 1.7 Watch it build, then check it

Reload the Space page. It will say **Building** — this takes two to four
minutes the first time. Click **Logs** to watch. You are waiting for:

```
tools on http://0.0.0.0:8601  (health is open, /tools/* needs the Bearer token)
INFO:     Application startup complete.
```

The status then changes to **Running**.

Your service address is shown on the Space page, and looks like:

```
https://YOUR-USERNAME-course-planner-tools.hf.space
```

Open this in a browser tab:

```
https://YOUR-USERNAME-course-planner-tools.hf.space/health
```

You should see:

```json
{"ok":true,"service":"course-planner-tools","cohort":"2026-27",
 "programs":129,"tiers":{"auto_extracted":92,"unsupported":32,"verified":5},
 "courses":1649}
```

`"programs":129` and `"verified":5` mean the data arrived intact. This endpoint
needs no token on purpose, so you — or a reviewer, or a marker — can confirm
the data side is alive without being handed a password.

**If the build fails**, read the last lines of **Logs**. A missing
`TOOL_API_TOKEN` is the usual cause and the error says so by name.

**If you change the data later**, re-run `scripts/make_space.py`, then
`cd deploy\space`, `git add -A`, `git commit -m "update"`, `git push`.

---

# Phase 2 · Wire Dify to it

## 2.1 Import the workflow

In Dify:

1. **Create app** → **Import DSL** (sometimes called *Import from file*).
2. Upload `dify/course-planner.yml` from the repo.

**"Imported with warnings" is expected.** The file is written in an older
version of Dify's format on purpose, so Dify upgrades it as it reads it.

This creates a **new** app, so the model you picked in your old one does not
come with it — that is the next step.

Check the Start box now asks for **Major**, **Intake cohort**, **Credits per
term** (two numbers), **Workload spread** and **Terms to keep free**, plus two
configuration fields you are about to move.

> If a dropdown arrived as a plain text box, click the field in the Start node
> and change its type to **Select**, then add the options from
> `SAMPLE_QUERIES.md`. Dify's importer is occasionally lossy about field
> types; the graph itself is unaffected.

## 2.2 Give both LLM boxes a model

Click **LLM · shape the plan** and pick your model from its **Model**
dropdown. Then do the same for **LLM · repair pass**.

Do not skip the second one. It is easy to forget, and it only fails *after*
the first has already worked, which makes it look like a new problem.

## 2.3 Create the two environment variables

This is what keeps your token away from reviewers. Right now it is a form
field, so anyone who opens your link is handed it.

In the workflow editor find **Environment Variables** — in the right-hand
panel, or behind a **Variables** button at the top. Add two:

| Name | Type | Value |
|---|---|---|
| `tool_base` | String | `https://YOUR-USERNAME-course-planner-tools.hf.space` (no trailing slash) |
| `tool_token` | **Secret** | the 43 characters from `.env` |

**Secret**, not String, for the token: a secret is masked in the interface and
left blank when the app is exported, so it cannot leak through a file you hand
in.

## 2.4 Point the four tool boxes at them

Four boxes are named `Tool · something`, and each has **two** places still
referring to the old form fields. Eight small edits, all the same edit.

For **Tool · get_program**, **Tool · draft_plan**, **Tool · validate_plan**
and **Tool · validate_plan (final)**:

**The URL field** reads something like:

```
{{#1701.tool_base#}}/tools/get_program
```

Delete just the `{{#1701.tool_base#}}` part, leaving `/tools/get_program`. Put
the cursor at the front and type `/` — Dify opens a variable picker — then
choose **tool_base** under *Environment Variables*.

**The body field** below it starts:

```json
{"tool_token": "{{#1701.tool_token#}}", ...
```

Delete just the `{{#1701.tool_token#}}` part, keeping the quotes, and insert
the **tool_token** environment variable the same way.

> **Pick from the list; do not type the reference by hand.** The template form
> is easy to get subtly wrong, and a reference that does not resolve arrives
> at the service as the literal text `{{#...#}}`. The service will say exactly
> that rather than leaving you to guess at a 401 — but picking from the list
> avoids it entirely.

When all four are done, delete `tool_base` and `tool_token` from the **Start**
box so reviewers never see them.

## 2.5 Check the timeouts

Open each `Tool ·` box and find **Timeout**: about 30 seconds to connect, 60
to read. If the import reset them to 0, set them. A sleeping free service
takes up to a minute to wake, and the default gives up before it answers.

## 2.6 Run it once

Click **Run** and fill in:

| Field | Value |
|---|---|
| Major | `COMP` |
| Intake cohort | `2026-27` |
| Credits per term, minimum | `12` |
| Credits per term, maximum | `18` |
| Workload spread | `even` |
| Terms to keep free | `Y4 Spring` |

All twelve boxes should go green, and the result should be a readable plan: a
term-by-term table totalling 120 credits, the data tier, nine things to check,
and a line telling you to see an academic advisor.

**If a `Tool ·` box fails**, the troubleshooting table at the end of
`SETUP.md` says what each failure means.

---

# Phase 3 · Publish, and keep it awake

## 3.1 Publish

Click **Publish** (top right). Open the app's overview page, find the **web
app** URL — this is the link reviewers use — and set its access so anyone with
the link can run it.

## 3.2 Stop it falling asleep

A free Space sleeps after **48 hours** with no visitors and takes up to a
minute to wake. Over a review window that is a real risk, and a reviewer who
meets a cold start reads it as broken.

So give it a heartbeat. At <https://cron-job.org> (free, no card), sign up and
create one cronjob:

| Setting | Value |
|---|---|
| **URL** | `https://YOUR-USERNAME-course-planner-tools.hf.space/health` |
| **Schedule** | every 15 minutes |

`/health` needs no token, which is why it is the right URL for this.

## 3.3 Prove it the way a reviewer will

Do all three:

1. Open the web app link in a **private/incognito window** — this is how you
   learn whether it is really public rather than just visible to you.
2. Open it **on your phone**.
3. **Close your laptop** and try again from your phone.

If step 3 works you are done. If it only works with the laptop open, something
still points at your machine: check `tool_base` is the `hf.space` address and
not a `trycloudflare.com` one.

---

## What to hand in

| What | Where |
|---|---|
| **Demo link** | the Dify web app URL from 3.1 |
| **Test log** | `TEST_LOG.md` |
| **Sample scenarios** | `SAMPLE_QUERIES.md` |

Worth sending with the link: *"The first run may take up to a minute if the
service has been idle."*

No token is in any of it. It lives in the Space's secret store and in Dify's,
and a Dify export leaves secrets blank.

---

## Appendix · other hosts

Everything from Phase 2 on is the same wherever the service runs. What changes
is how it gets there.

**Any host that builds a Dockerfile** — Render, Railway, Fly, Koyeb, Cloud Run
— can use this repo directly rather than `deploy/space`, because they can read
a private repository once you connect your GitHub account. The settings that
matter are always the same four:

| Setting | Value |
|---|---|
| Runtime / Language | **Docker** |
| Branch | `main` |
| Build and start commands | **leave empty** — the `Dockerfile` says both |
| Environment variable | `TOOL_API_TOKEN` = the 43 characters from `.env` |

You do not need to set `PORT`: the host sets it and the service reads it.

Two things to know before choosing one. Several of these ask for a credit card
at sign-up even on a free plan. And free instances sleep much sooner than a
Space does — about 15 minutes idle rather than 48 hours — which makes the
heartbeat in 3.2 essential rather than merely wise.

**Vercel is a poor fit**, despite being free and easy elsewhere. It runs
serverless functions, not containers, so it ignores the `Dockerfile` and needs
a separate entry point; and it installs the repo's root `requirements.txt`,
which carries Streamlit, pdfplumber and the model SDKs that this service never
imports. Possible, but more work than the options above for no gain.
