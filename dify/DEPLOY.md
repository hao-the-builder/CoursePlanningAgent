# Putting it online for reviewers — click by click

`SETUP.md` is for running this on your own machine. This file is for the other
job: a link that works while your laptop is shut, for the whole review window.

Three phases, about 45 minutes the first time.

1. **Put the tool service online** — so Dify can reach the course data from
   anywhere.
2. **Wire Dify to it** — and hide your token from reviewers.
3. **Publish, and keep it awake.**

Nothing here touches the repo. If a step goes wrong you can stop and nothing
is broken.

---

## Before you start

Have these two things to hand.

**The repo on GitHub.** It is already pushed. You will point the host at it.

**Your tool token.** It is the `TOOL_API_TOKEN` line in `.env`. Open `.env` in
a text editor and copy everything after the `=`. It is 43 characters of
letters and digits. Do not paste it into anything public — not a GitHub issue,
not a Dify form field that reviewers can see, not a screenshot.

---

# Phase 1 · Put the tool service online

The tool service is the part that holds the course data and answers Dify's
questions. Right now it runs on your laptop. A reviewer opening your link
tomorrow needs it somewhere that is always there.

## 1.1 Make an account

Go to <https://render.com> and sign up — the "Sign up with GitHub" button is
easiest, because the next step needs GitHub access anyway.

> **If it asks for a credit card** and you would rather not give one, stop here
> and use **Plan B** at the bottom of this file instead. Reports disagree about
> whether Render's free tier asks for one, so you will find out at this step.

## 1.2 Create the service

1. Click **New** (top right) → **Web Service**.
2. Choose **Build and deploy from a Git repository**, then **Next**.
3. Find `CoursePlanningAgent` in the list and click **Connect**. If it is not
   listed, click **Configure account** / **Install** and give Render access to
   that repository.

## 1.3 Fill in the settings

Most defaults are fine. These are the ones that matter:

| Setting | What to put | Why |
|---|---|---|
| **Name** | `course-planner-tools` | Becomes part of your URL |
| **Language** or **Runtime** | **Docker** | There is a `Dockerfile` in the repo; this tells Render to use it |
| **Branch** | `main` | |
| **Region** | the one nearest you | |
| **Instance Type** | **Free** | Scroll down; Free is at the bottom of the list |

Leave **Root Directory**, **Build Command** and **Start Command** empty. The
`Dockerfile` already says what to build and how to start it.

## 1.4 Add your token

Still on the same page, find **Environment Variables** (you may need to expand
**Advanced**). Click **Add Environment Variable** and enter:

| Key | Value |
|---|---|
| `TOOL_API_TOKEN` | the 43 characters from `.env` |

**This step is not optional.** The service refuses to start without it, on
purpose — it would otherwise be answering anyone who found the address.

You do **not** need to set `PORT`. Render sets it, and the service reads it.

## 1.5 Deploy

Click **Create Web Service**. Render now builds the image and starts it. The
log scrolls past on screen; the first build takes about three to five minutes.

You are looking for these two lines near the end:

```
tools on http://0.0.0.0:10000  (health is open, /tools/* needs the Bearer token)
INFO:     Application startup complete.
```

Then, at the top of the page, copy your URL. It looks like:

```
https://course-planner-tools.onrender.com
```

## 1.6 Check it with your own eyes

Open this in a browser tab, pasting your own address:

```
https://course-planner-tools.onrender.com/health
```

You should see something like:

```json
{"ok":true,"service":"course-planner-tools","cohort":"2026-27",
 "programs":129,"tiers":{"auto_extracted":92,"unsupported":32,"verified":5},
 "courses":1649}
```

`"programs":129` and `"verified":5` mean the data arrived intact. This endpoint
needs no token on purpose, so you — or a reviewer, or a marker — can confirm
the data side is alive without being given a password.

**If you get an error page**, go to the **Logs** tab in Render and read the
last lines. `TOOL_API_TOKEN` missing is the usual cause, and it says so.

---

# Phase 2 · Wire Dify to it

## 2.1 Import the workflow

In Dify:

1. **Create app** → **Import DSL** (sometimes called *Import from file*).
2. Upload `dify/course-planner.yml` from the repo.

**"Imported with warnings" is expected.** The file is written in an older
version of Dify's format on purpose, so Dify upgrades it as it reads it.

This creates a **new** app. Your old one is untouched, which also means the
model you picked before is not carried over — that is the next step.

Check the form looks right: the Start box should now ask for **Major**,
**Intake cohort**, **Credits per term** (two numbers), **Workload spread** and
**Terms to keep free**, plus two configuration fields you are about to move.

> If a dropdown arrived as a plain text box, click the field in the Start node
> and change its type to **Select**, then add the options listed in
> `SAMPLE_QUERIES.md`. Dify's importer is occasionally lossy about field types;
> the graph itself is unaffected.

## 2.2 Give both LLM boxes a model

Click the box called **LLM · shape the plan**. In its **Model** dropdown, pick
your model.

Then do the same for **LLM · repair pass**. It is easy to forget, and it only
fails *after* the first one has already worked.

## 2.3 Create the two environment variables

This is the step that keeps your token away from reviewers. Right now the token
is a form field, which means anyone who opens your link is handed it.

In the workflow editor, find **Environment Variables** — it is in the panel on
the right-hand side, or behind a **Variables** button at the top. Add two:

| Name | Type | Value |
|---|---|---|
| `tool_base` | String | your Render URL, with **no** trailing slash |
| `tool_token` | **Secret** | the 43 characters from `.env` |

Use **Secret** for the token, not String. A secret is masked in the interface
and is left blank when the app is exported, so it cannot leak through a file
you hand in.

## 2.4 Point the four tool boxes at them

There are four boxes named `Tool · something`. Each has **two** places that
still refer to the old form fields. That is eight small edits, and they are all
the same edit.

For each of these boxes — **Tool · get_program**, **Tool · draft_plan**,
**Tool · validate_plan**, **Tool · validate_plan (final)** — do this:

**The URL field.** It currently reads something like:

```
{{#1701.tool_base#}}/tools/get_program
```

Delete just the `{{#1701.tool_base#}}` part, leaving `/tools/get_program`. With
your cursor at the front, type `/` — Dify opens a variable picker — and choose
**tool_base** from the **Environment Variables** section. The field should end
up as the environment variable followed by `/tools/get_program`.

**The body field.** Below it, the request body starts like:

```json
{"tool_token": "{{#1701.tool_token#}}", ...
```

Delete just the `{{#1701.tool_token#}}` part, keeping the quotes around it, and
insert the **tool_token** environment variable the same way.

> **Pick from the list; do not type the reference by hand.** The template form
> is easy to get subtly wrong, and a reference that does not resolve arrives at
> the service as the literal text `{{#...#}}`. The service will tell you that
> in those words rather than leaving you to guess — but picking from the list
> avoids it entirely.

When all four are done, delete `tool_base` and `tool_token` from the **Start**
box so reviewers never see them.

## 2.5 Check the timeouts

Open each `Tool ·` box and find **Timeout**. It should read roughly 30 seconds
to connect and 60 to read. If the import reset them to 0, set them.

This matters because a sleeping free service takes up to a minute to wake, and
the default timeout gives up before it answers.

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

All twelve boxes should go green and the result should be a readable plan:
a term-by-term table totalling 120 credits, the data tier, nine things to
check, and a line telling you to see an academic advisor.

**If a `Tool ·` box fails**, the troubleshooting table at the bottom of
`SETUP.md` covers what each failure means.

---

# Phase 3 · Publish, and keep it awake

## 3.1 Publish

Click **Publish** (top right). Then open the app's overview page and find the
**web app** URL — this is the link reviewers use. Set its access so anyone
with the link can run it.

## 3.2 Stop it falling asleep

A free service sleeps after about 15 minutes of nobody using it, and takes up
to a minute to wake. A reviewer who meets that reads it as broken.

So give it a heartbeat. Go to <https://cron-job.org> (free, no card), sign up,
and create a cronjob:

| Setting | Value |
|---|---|
| **URL** | `https://course-planner-tools.onrender.com/health` |
| **Schedule** | every 10 minutes |

That is it. The service now gets a visitor every ten minutes and never sleeps
during your review window. `/health` needs no token, which is why it is the
right URL to use for this.

## 3.3 Prove it the way a reviewer will

Do all three:

1. Open the web app link in a **private/incognito window** — this is how you
   find out it is actually public and not just visible to you.
2. Open it **on your phone**.
3. **Close your laptop** and try again from your phone.

If step 3 works, you are done. If it only works with your laptop open,
something is still pointing at your machine — check the `tool_base`
environment variable is your Render URL and not a `trycloudflare.com` address.

---

## What to hand in

| What | Where |
|---|---|
| **Demo link** | the Dify web app URL from 3.1 |
| **Test log** | `TEST_LOG.md` |
| **Sample scenarios** | `SAMPLE_QUERIES.md` |

Worth sending with the link: *"The first run may take up to a minute if the
service has been idle."*

Neither YAML nor either document contains the token — it lives in Render's
environment and in Dify's secret store, and a Dify export leaves secrets
blank.

---

## Plan B · if Render wants a card

Use Hugging Face Spaces, which is free without one.

1. Sign up at <https://huggingface.co>.
2. **New** → **Space**. Name it, choose **Docker** as the SDK, and **Blank**
   as the template. Hardware: **CPU basic (free)**.
3. In **Settings → Variables and secrets**, add a secret `TOOL_API_TOKEN` with
   the value from `.env`.
4. Push this repo to the Space's git remote (the Space page shows the command).
5. Add this to the very top of `README.md` in the Space, before anything else:

   ```
   ---
   title: Course Planner Tools
   sdk: docker
   app_port: 8601
   ---
   ```

   The Space serves whatever is on `app_port`, and the `Dockerfile` listens on
   8601.
6. Your address is `https://<your-name>-<space-name>.hf.space`. Check
   `/health` as in 1.6, then carry on from Phase 2.

A free Space sleeps after **48 hours** idle rather than 15 minutes, so the
heartbeat in 3.2 matters less — but it does no harm.
