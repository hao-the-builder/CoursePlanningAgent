"""Build `data/VERIFY.pdf` — the pack the developer checks by hand.

    python scripts/make_verify_pdf.py
    python scripts/make_verify_pdf.py --out somewhere/else.pdf

The rule tables come straight from `data/VERIFY.md`, which
`pipeline/check_program.py` writes from the program JSONs, so no requirement
is retyped here. What this file adds is the part a markdown table cannot
carry: what to do with it, a tick box per rule, rows worth a second look,
and the two other jobs that need a human (the deploy and the phone check).

Rendering goes through headless Chrome's `--print-to-pdf`, the only PDF
engine on this machine, so there is no new dependency to install.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "data" / "VERIFY.md"
INDEX = REPO / "data" / "program_index.json"
SECRETS_EXAMPLE = REPO / ".streamlit" / "secrets.toml.example"
DEFAULT_OUT = REPO / "data" / "VERIFY.pdf"

REPO_SLUG = "hao-the-builder/CoursePlanningAgent"


# --- the markdown subset used by VERIFY.md ---------------------------------

CODE_SPAN = re.compile(r"`([^`]*)`")
COURSE = re.compile(r"\b([A-Z]{2,6})\s?(\d{3,4}[A-Z]?)\b")
LEVEL = re.compile(r"(\d)000-level")


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def inline(text: str) -> str:
    """Bold, italic, code spans, autolinks. Code spans are taken out first
    so that a pipe or an asterisk inside one survives."""
    spans: list[str] = []

    def hide(match: re.Match[str]) -> str:
        spans.append(match.group(1))
        return f"\x00{len(spans) - 1}\x00"

    text = CODE_SPAN.sub(hide, text)
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"_([^_]+)_", r"<em>\1</em>", text)
    text = re.sub(r"&lt;(https?://[^&\s]+)&gt;",
                  r'<a href="\1">\1</a>', text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                  r'<a href="\2">\1</a>', text)
    return re.sub(r"\x00(\d+)\x00",
                  lambda m: f"<code>{esc(spans[int(m.group(1))])}</code>",
                  text)


def cells(row: str) -> list[str]:
    """Split a table row on pipes that are not inside a code span — the
    source-quote column is full of them."""
    out: list[str] = []
    buf: list[str] = []
    in_code = False
    for ch in row.strip():
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
        elif ch == "|" and not in_code:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    parts = [c.strip() for c in out]
    if parts and not parts[0]:
        parts.pop(0)
    if parts and not parts[-1]:
        parts.pop()
    return parts


def blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Group lines into ('table'|'list'|'para'|'h3'|'hr', lines)."""
    out: list[tuple[str, list[str]]] = []
    buf: list[str] = []
    kind = ""

    def flush() -> None:
        nonlocal buf, kind
        if buf:
            out.append((kind, buf))
        buf, kind = [], ""

    for raw in lines:
        # trailing spaces are kept: two of them are a markdown line break,
        # which the Source / Tier lines rely on
        stripped = raw.rstrip("\r\n")
        if kind == "table" and buf and buf[-1].count("`") % 2:
            # a source quote that spans lines in the PDF spans lines here
            # too, so the row is not over until its code span closes
            buf[-1] += "\n" + stripped.strip()
        elif not stripped.strip():
            flush()
        elif stripped.startswith("### "):
            flush()
            out.append(("h3", [stripped[4:]]))
        elif stripped.startswith("---"):
            flush()
        elif stripped.startswith("|"):
            if kind != "table":
                flush()
            kind = "table"
            buf.append(stripped)
        elif stripped.startswith("- "):
            if kind != "list":
                flush()
            kind = "list"
            buf.append(stripped[2:])
        else:
            if kind != "para":
                flush()
            kind = "para"
            buf.append(stripped)
    flush()
    return out


# --- rows worth a second look ---------------------------------------------

def courses(text: str) -> set[str]:
    return {f"{m.group(1)} {m.group(2)}" for m in COURSE.finditer(text)}


def flags(rows: list[list[str]]) -> dict[int, list[str]]:
    """Mechanical reasons a row deserves the first look, by row index.

    Nothing here means the row is wrong — only that the extraction did
    something to it that the PDF line alone does not show.
    """
    found: dict[int, list[str]] = {}
    shared: dict[str, list[str]] = {}
    for row in rows:
        if len(row) >= 3:
            shared.setdefault(row[2], []).append(row[0])

    for i, row in enumerate(rows):
        if len(row) < 3:
            continue
        number, data, quote = row[0], row[1], row[2]
        notes: list[str] = []

        dropped = sorted(courses(quote) - courses(data))
        if dropped:
            shown = ", ".join(dropped[:4])
            more = f" and {len(dropped) - 4} more" if len(dropped) > 4 else ""
            notes.append(f"the line names {shown}{more}; the rule does not. "
                         f"The usual reason is a course missing from the "
                         f"2026-27 catalog, and the caveats at the end of "
                         f"this program say which — check that it is that")

        if re.match(r"at least 0 credits", data):
            notes.append("no credit minimum: the line states none, so this "
                         "requirement enforces nothing")

        levels = set(LEVEL.findall(quote))
        in_data = {c.split()[1][0] for c in courses(data)}
        if levels and in_data and not (levels & in_data):
            notes.append(f"the line says {'/'.join(sorted(levels))}000-level "
                         f"but the courses listed are "
                         f"{'/'.join(sorted(in_data))}000-level")

        same = [n for n in shared.get(quote, []) if n != number]
        if same:
            notes.append(f"this one PDF line also produced row "
                         f"{', '.join(same)} — a course count and a credit "
                         f"minimum from the same sentence")

        if notes:
            found[i] = notes
    return found


# --- rendering -------------------------------------------------------------

CSS = """
@page { size: A4; margin: 15mm 13mm 14mm 13mm; }
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", -apple-system, system-ui, Arial, sans-serif;
  font-size: 9.6pt; line-height: 1.45; color: #1a1a1a; margin: 0;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1 { font-size: 23pt; line-height: 1.1; margin: 0 0 6pt; letter-spacing: -0.4pt; }
h2 { font-size: 14pt; margin: 0 0 2pt; letter-spacing: -0.2pt; }
h3 { font-size: 10.4pt; margin: 14pt 0 4pt; break-after: avoid; }
h4 { font-size: 10pt; margin: 12pt 0 4pt; break-after: avoid; }
p { margin: 0 0 6pt; }
a { color: #1a4f8a; text-decoration: none; word-break: break-all; }
code { font-family: Consolas, "Courier New", monospace; font-size: 0.9em;
       background: #f2f2f0; padding: 0 2px; border-radius: 2px; }
.kicker { font-size: 8.4pt; letter-spacing: 1.1pt; text-transform: uppercase;
          color: #6b6b6b; margin: 0 0 10pt; }
.lede { font-size: 11pt; line-height: 1.5; color: #333; margin-bottom: 12pt; }
hr { border: 0; border-top: 1px solid #ddd; margin: 14pt 0; }

table { border-collapse: collapse; width: 100%; font-size: 8.3pt;
        margin: 0 0 8pt; }
thead { display: table-header-group; }
th { text-align: left; font-weight: 600; font-size: 7.6pt;
     text-transform: uppercase; letter-spacing: 0.5pt; color: #555;
     border-bottom: 1.2px solid #999; padding: 3pt 4pt; }
td { border-bottom: 1px solid #e6e6e6; padding: 4pt 4pt; vertical-align: top;
     word-break: break-word; }
tr { break-inside: avoid; }
td.tick { width: 9mm; text-align: center; }
td.num, th.num { width: 7mm; color: #777; }
td.quote { width: 41%; font-family: Consolas, "Courier New", monospace;
           font-size: 7.4pt; color: #444; background: #fafaf8; }
td.quote code { background: none; padding: 0; font-size: 1em;
                white-space: pre-wrap; }
.box { display: inline-block; width: 3.4mm; height: 3.4mm;
       border: 1px solid #666; border-radius: 0.6mm; }
.flagged td { background: #fffaf0; }
.flag { display: block; margin-top: 3pt; font-size: 7.4pt; color: #8a5a00;
        font-style: italic; }

.jobs td { font-size: 9.2pt; }
.jobs td:first-child { font-weight: 600; width: 34%; }

.card { border: 1px solid #ddd; border-left: 3px solid #1a4f8a;
        padding: 8pt 10pt; margin: 0 0 10pt; background: #fbfbfa;
        break-inside: avoid; }
.card h4 { margin-top: 0; }
.card ul, .card ol { margin: 0; padding-left: 16pt; }
.card li { margin-bottom: 3pt; }
ul, ol { margin: 0 0 8pt; padding-left: 16pt; }
li { margin-bottom: 3pt; }

.prog { break-before: page; }
.meta { font-size: 8.4pt; color: #555; margin: 0 0 2pt; }
.look { break-after: avoid; font-size: 8.4pt; color: #8a5a00; background: #fffaf0;
        border: 1px solid #f0dca8; padding: 5pt 7pt; margin: 6pt 0 10pt; }
.verdict { break-inside: avoid; border: 1px solid #bbb; padding: 8pt 10pt;
           margin: 10pt 0 0; }
.verdict .line { border-bottom: 1px solid #ccc; height: 13pt; margin-top: 7pt; }
.checklist { list-style: none; padding-left: 0; }
.checklist li { padding-left: 7mm; text-indent: -7mm; margin-bottom: 5pt; }
.checklist li::before { content: "\\2610\\00a0\\00a0"; font-size: 12pt;
                        line-height: 1; }
.checklist li pre { text-indent: 0; margin-top: 5pt; }
pre { background: #f6f6f4; border: 1px solid #e2e2de; padding: 7pt 9pt;
      font-family: Consolas, "Courier New", monospace; font-size: 8pt;
      margin: 0 0 8pt; white-space: pre-wrap; break-inside: avoid; }
.tiny { font-size: 8pt; color: #666; }
footer { margin-top: 16pt; border-top: 1px solid #ddd; padding-top: 7pt;
         font-size: 7.8pt; color: #777; }
.sheet { break-before: page; }
"""


def render_table(lines: list[str]) -> str:
    rows = [cells(line) for line in lines]
    if len(rows) < 2:
        return ""
    header, body = rows[0], [r for r in rows[2:] if r]
    marks = flags(body)

    head = ['<tr><th class="num">OK?</th>']
    head.append(f'<th class="num">{esc(header[0])}</th>')
    for col in header[1:]:
        klass = ' class="quote"' if "came from" in col else ""
        head.append(f"<th{klass}>{esc(col)}</th>")
    head.append("</tr>")

    out = [f'<table><thead>{"".join(head)}</thead><tbody>']
    for i, row in enumerate(body):
        klass = ' class="flagged"' if i in marks else ""
        out.append(f"<tr{klass}>")
        out.append('<td class="tick"><span class="box"></span></td>')
        out.append(f'<td class="num">{inline(row[0])}</td>')
        note = "".join(f'<span class="flag">look: {esc(n)}</span>'
                       for n in marks.get(i, []))
        out.append(f"<td>{inline(row[1])}{note}</td>")
        for col in row[2:]:
            out.append(f'<td class="quote">{inline(col)}</td>')
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def render_section(title: str, body: list[str], school: str | None,
                   ordinal: str = "") -> str:
    code = title.split("—")[0].strip().split()[0]
    out = [f'<section class="prog"><h2>{inline(title)}</h2>']
    meta = " &middot; ".join(x for x in (ordinal, esc(school or "")) if x)
    if meta:
        out.append(f'<p class="meta">{meta}</p>')

    looks: list[str] = []
    rendered: list[str] = []
    for kind, lines in blocks(body):
        if kind == "h3":
            rendered.append(f"<h3>{inline(lines[0])}</h3>")
            group = lines[0]
        elif kind == "table":
            rows = [cells(line) for line in lines]
            marked = flags([r for r in rows[2:] if r])
            if marked:
                numbers = ", ".join(
                    [r[0] for i, r in enumerate(r2 for r2 in rows[2:] if r2)
                     if i in marked])
                looks.append(f"{re.sub(r'  _.*', '', group)} {numbers}")
            rendered.append(render_table(lines))
        elif kind == "list":
            items = "".join(f"<li>{inline(x)}</li>" for x in lines)
            rendered.append(f"<ul>{items}</ul>")
        else:
            parts = []
            for line in lines:
                parts.append(inline(line.rstrip()))
                parts.append("<br>" if line.endswith("  ") else " ")
            rendered.append(f"<p>{''.join(parts[:-1])}</p>")

    if looks:
        box = ('<p class="look"><strong>Shaded rows first.</strong> '
               + esc("; ".join(looks)) +
               ". The reason is printed under each one. A shaded row is "
               "not a mistake — it is a row where the extraction did "
               "something the PDF line alone does not show.</p>")
        # after the Source / Tier line, which belongs directly under the title
        at = 1 if rendered and rendered[0].startswith("<p>") else 0
        rendered.insert(at, box)
    out += rendered
    out.append(
        f'<div class="verdict"><strong>{esc(code)} — your verdict.</strong> '
        f'Circle one: &nbsp; right &nbsp;/&nbsp; wrong &nbsp;/&nbsp; not sure'
        f'<div class="line"></div><div class="line"></div>'
        f'<div class="line"></div></div>')
    out.append("</section>")
    return "".join(out)


def front_matter(today: str) -> str:
    return f"""
<p class="kicker">HKUST Course Planning Agent &middot; {today}</p>
<h1>What still needs a human</h1>
<p class="lede">Everything a machine can check is checked: 443 tests pass and
all sixteen eval profiles match what they were told to expect. Three things
are left, and none of them can be done without you. The first is most of this
pack; the other two take twenty minutes between them.</p>

<table class="jobs"><tbody>
<tr><td>1 &middot; Verify five programs</td>
    <td>This pack, and five PDFs open in a browser. About 45&ndash;60 minutes.
    It closes the one Phase&nbsp;2 &ldquo;Done when&rdquo; that is still
    open.</td></tr>
<tr><td>2 &middot; Deploy the app</td>
    <td>Your Streamlit Cloud account, an API key, and a spend limit set
    first. About 15 minutes. Page at the end.</td></tr>
<tr><td>3 &middot; Look at it on a phone</td>
    <td>The deployed link on your own phone. Five minutes, and it cannot be
    done headlessly.</td></tr>
</tbody></table>

<div class="card">
<h4>Why job 1 cannot be automated</h4>
<p>The requirement rules were read out of 129 official PDFs by code. That code
already checks what it can: every course code exists in the catalog, every
rule loads as a valid <code>Program</code>, the credits add up to the total the
PDF states, and nothing was silently dropped. 104 programs pass all of that
and sit at tier <code>auto_extracted</code>; 25 failed and are marked
<code>unsupported</code>, so the app refuses to plan them.</p>
<p>What no check can tell is whether a rule <em>means</em> what the PDF
sentence meant. &ldquo;Must take&rdquo; versus &ldquo;choose one of&rdquo;,
the right group, the right count &mdash; that needs eyes on both. Only your
say-so sets <code>tier: verified</code>. Nothing is verified today.</p>
</div>

<h3>How to check a program</h3>
<ol>
<li>Open the <strong>Source</strong> link printed under the program&rsquo;s
heading. It is the official 2026-27 requirement PDF, the same file the rules
were read from.</li>
<li>Find the matching section in the PDF. The <code>### </code> headings here
are the PDF&rsquo;s own headings, in the PDF&rsquo;s order.</li>
<li>Read down the table. The middle column is what the data now says; the
right column is the line of the PDF it was read from. You are checking three
things only: <strong>the course codes, the credits, and how many are
required</strong>.</li>
<li>Tick the box when a row matches. When it does not, write the group and
the row number in the box at the end of that program, with a word on what is
wrong.</li>
<li>Start with the shaded rows. Each program lists them at the top.</li>
</ol>

<div class="card">
<h4>What counts as wrong</h4>
<ul>
<li>A course code in the rule that the PDF does not name, or one the PDF
requires that the rule leaves out.</li>
<li>Credits that do not match the PDF&rsquo;s number.</li>
<li>&ldquo;Must take&rdquo; where the PDF says choose one of several; or the
wrong <em>n</em> in &ldquo;must take 5 of these 60&rdquo;.</li>
<li>A requirement filed under the wrong group &mdash; School where the PDF
puts it under Major, or inside a track when it applies to everyone &mdash;
where that changes what a student must take.</li>
</ul>
</div>

<div class="card">
<h4>What is not wrong, however odd it looks</h4>
<ul>
<li><strong>A caveat.</strong> The PDF states a condition no rule type can
enforce (&ldquo;at least 3 courses from one area&rdquo;, &ldquo;subject to
approval of the program office&rdquo;). Caveats are shown to the student
instead of being checked, and are listed at the end of each program. Read
them; there is nothing to tick.</li>
<li><strong>A course dropped from a rule</strong> because it is not in the
2026-27 catalog. <code>ELEC 2600H</code> in COMP is the example: the PDF names
it, HKUST deleted the course after 2021-22, so it is out of the rule and
recorded as a caveat.</li>
<li><strong>One PDF line producing two rules</strong> &mdash; a course count
and a credit minimum from the same sentence. Both are real; the credit total
still counts each course once.</li>
<li><strong>The phrasing.</strong> &ldquo;must take one of: A + B <strong>OR</strong>
C&rdquo; is how the data writes the PDF&rsquo;s bracketed note
<code>[(A AND B) OR C]</code>.</li>
<li><strong>A 60-code elective list.</strong> Do not read it code by code.
Check the first three, the last three, and the count.</li>
</ul>
</div>

<div class="card">
<h4>Two things to know before you start</h4>
<ul>
<li><strong>Two of the five are track variants.</strong> BSc Mathematics and
BSc Global China Studies both make the student choose a track, so the base
program is not a plannable curriculum and is marked
<code>unsupported</code>. <code>MATH-AM</code> (Applied Mathematics) and
<code>GCS-SS</code> (Social Science) stand in for them, one per school as
Phase&nbsp;2 Part&nbsp;F asks.</li>
<li><strong>A wrong row is a useful result.</strong> It is a bug in the
extraction code, which is worth more than a tick. Say what you saw and it
gets fixed and re-checked, not patched by hand.</li>
</ul>
</div>
"""


def reply_page() -> str:
    return """
<section class="sheet">
<h2>When you are done &mdash; what to say</h2>
<p>Tell Claude Code in whatever words come naturally. This is a complete
answer:</p>
<pre>COMP, FINA and IDT are right.
MATH-AM is wrong: Requirements row 1 should include COMP 1022P.
GCS-SS: not sure about Elective row 2, the PDF reads differently to me.</pre>

<h3>What happens to each answer</h3>
<table><tbody>
<tr><td style="width:24%"><strong>right</strong></td>
    <td><code>"tier": "verified"</code> goes into
    <code>data/programs/{CODE}.json</code>, the index is rebuilt, and the app
    shows a green badge for that program. Nothing else sets that tier.</td></tr>
<tr><td><strong>wrong</strong></td>
    <td>The extraction code is fixed &mdash; not the JSON by hand, because
    the same bug will be in other programs &mdash; then
    <code>pipeline/extract_programs.py</code> and
    <code>check_program.py --all</code> re-run, the tests run, and the row
    comes back to you.</td></tr>
<tr><td><strong>not sure</strong></td>
    <td>Stays <code>auto_extracted</code>. The app still plans it, with the
    amber badge and &ldquo;verify with your advisor&rdquo;. That is the honest
    state, so leaving a row unsure costs nothing.</td></tr>
</tbody></table>

<h3>The five, at a glance</h3>
<table><thead><tr><th class="num">OK?</th><th>Program</th>
<th>Verdict</th></tr></thead><tbody>
<tr><td class="tick"><span class="box"></span></td>
    <td>COMP &mdash; BEng in Computer Science</td><td></td></tr>
<tr><td class="tick"><span class="box"></span></td>
    <td>MATH-AM &mdash; BSc Mathematics, Applied Mathematics Track</td>
    <td></td></tr>
<tr><td class="tick"><span class="box"></span></td>
    <td>FINA &mdash; BBA in Finance</td><td></td></tr>
<tr><td class="tick"><span class="box"></span></td>
    <td>GCS-SS &mdash; BSc Global China Studies, Social Science Track</td>
    <td></td></tr>
<tr><td class="tick"><span class="box"></span></td>
    <td>IDT &mdash; BSc in Innovation, Design and Technology</td><td></td></tr>
</tbody></table>
<p class="tiny">Five verified programs is what Phase&nbsp;2 asks for. Four
right and one wrong still closes it, once the wrong one is fixed and
re-checked.</p>
</section>
"""


def deploy_page(secrets: str) -> str:
    return f"""
<section class="sheet">
<h2>Job 2 &mdash; deploy the app</h2>
<p>Everything in the repository is ready: <code>app.py</code> copies Streamlit
secrets into the environment on startup, <code>requirements.txt</code> is
pinned, and the raw PDFs are kept out of git so a deploy pulls about 3&nbsp;MB.
What is missing is yours alone: an account, a key, and a spend limit.</p>

<ol class="checklist">
<li><strong>Set a spend limit first.</strong>
<a href="https://console.anthropic.com/settings/limits">console.anthropic.com
&rarr; Settings &rarr; Limits</a>. Do this before the key exists, not after.
A planning run costs about <strong>$1.25</strong> on Claude Opus 5.5, and a
public link is a public link.</li>
<li><strong>Create an API key.</strong>
<a href="https://console.anthropic.com/settings/keys">console.anthropic.com
&rarr; API keys</a>. It is shown once. Do not paste it into any file in the
repository &mdash; hard rule 8, and <code>.streamlit/secrets.toml</code> is
gitignored for the same reason.</li>
<li><strong>Create the app.</strong>
<a href="https://share.streamlit.io">share.streamlit.io</a> &rarr; sign in
with GitHub &rarr; <em>Create app</em> &rarr; from existing repo.
Repository <code>{REPO_SLUG}</code>, branch <code>main</code>, main file
<code>app.py</code>. Python 3.11 or newer.</li>
<li><strong>Paste the secrets</strong> into <em>Advanced settings &rarr;
Secrets</em>, with your real key in place of the placeholder:
<pre>{esc(secrets)}</pre>
<code>LLM_BACKEND</code> must be <code>api</code> here.
<code>subscription</code> only works where the <code>claude</code> CLI is
installed and signed in, which it is not on Cloud.</li>
<li><strong>Deploy</strong>, and watch the build log once. First build takes a
few minutes.</li>
<li><strong>Smoke-test the link in a fresh browser</strong> (not the tab you
deployed from, which is signed in): pick <em>BEng in Computer Science</em>,
leave every default, press <em>Plan my degree</em>, and download one
<code>.xlsx</code> and the <code>.docx</code>. That is one $1.25 run.</li>
<li><strong>Try the refusal</strong> while you are there: pick <em>BSc in
Mathematics</em> and check the red badge appears before you spend a second
generation. <code>SAMPLE_QUERIES.md</code> has five scenarios in the order
that shows the most.</li>
</ol>
<p class="tiny">If the app boots but every run fails, the key is the first
suspect: Streamlit Cloud supplies secrets through <code>st.secrets</code>
rather than the environment, and <code>planner/llm.py</code> reads the
environment. The bridge is at the top of <code>app.py</code>.</p>
</section>
"""


def phone_page() -> str:
    return """
<section class="sheet">
<h2>Job 3 &mdash; look at it on a phone</h2>
<p>This is the one test that could not be written.
<code>tests/test_app.py</code> drives the real Streamlit widgets headlessly,
so the four-step flow, the refusals and the session limits are tested &mdash;
but a headless screenshot of a Streamlit page never settles before the capture,
so no test has ever seen the layout. The app uses a single centred column and
full-width buttons, which is the layout that survives a phone, but that is a
design choice rather than a verified result.</p>
<p>Open the deployed link on your phone, or Chrome DevTools at 390&nbsp;px
wide, and look for six things:</p>
<ol class="checklist">
<li>No sideways scrolling on any of the four steps &mdash; form, chat,
generate, download.</li>
<li>Form fields and buttons run the full width and are tappable without
zooming.</li>
<li>The data-tier badge and the &ldquo;verify with your advisor&rdquo; line
are readable at arm&rsquo;s length. They are the honest part of the output; if
they are small enough to skip, that is a real defect.</li>
<li>The credits-per-term chart fits the screen rather than being cropped.</li>
<li>The download buttons actually deliver a file to the phone.</li>
<li>The chat box is still visible once the keyboard is up.</li>
</ol>
<p>Anything that fails here is a CSS-level fix in <code>app.py</code>, so send
a screenshot and a sentence.</p>

<h3>While you have it open</h3>
<p>Two numbers worth knowing, both from <code>TEST_LOG.md</code> and neither a
defect:</p>
<ul>
<li><strong>Every valid plan carries nine or more warnings</strong>, and none
of them is the plan&rsquo;s fault. The catalog contradicts itself on 17 course
pairs (<code>MATH 1013</code> excludes <code>MATH 1014</code> while also being
its prerequisite); the Common Core asks for 6 credits of HAIC when one
3-credit HAIC course is published; the class schedule disallows automated
access, so no course is checked against the terms it is actually offered in;
and HKUST publishes no rule on final-year-project duration. Each is reported
in plain English rather than papered over.</li>
<li><strong>One known failure stands</strong>:
<code>06-front-loaded-free-final</code> on the stub backend lands 3 credits
over the cap in one term. A model fixes it in the retry loop; the stub cannot.
The eval report says so rather than hiding it.</li>
</ul>
</section>
"""


def build_html(today: str) -> str:
    text = SOURCE.read_text(encoding="utf-8")
    schools: dict[str, str] = {}
    if INDEX.exists():
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        rows = index.get("programs", []) if isinstance(index, dict) else index
        for row in rows:
            if isinstance(row, dict) and row.get("code"):
                name = row.get("school_name") or ""
                code = row.get("school") or ""
                schools[row["code"]] = (f"{code} — {name}" if name else code)

    parts = re.split(r"^## ", text, flags=re.M)[1:]
    sections = []
    for n, part in enumerate(parts, start=1):
        lines = part.splitlines()
        title = lines[0].strip()
        code = title.split("—")[0].strip().split()[0]
        sections.append(render_section(
            title, lines[1:], schools.get(code) or None,
            ordinal=f"Program {n} of {len(parts)}"))

    secrets = (SECRETS_EXAMPLE.read_text(encoding="utf-8")
               if SECRETS_EXAMPLE.exists() else "")
    secrets = "\n".join(line for line in secrets.splitlines()
                        if line.strip() and not line.startswith("#"))

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>What still needs a human</title>"
        f"<style>{CSS}</style></head><body>"
        + front_matter(today)
        + "".join(sections)
        + reply_page()
        + deploy_page(secrets)
        + phone_page()
        + f'<footer>Built by <code>scripts/make_verify_pdf.py</code> from '
          f'<code>data/VERIFY.md</code> on {today}. Every requirement rule and '
          f'every quoted PDF line comes from that file, which '
          f'<code>pipeline/check_program.py</code> writes from the program '
          f'JSONs &mdash; nothing in the tables was retyped. Regenerate with '
          f'<code>python scripts/make_verify_pdf.py</code>.</footer>'
        "</body></html>")


def find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("chrome"), shutil.which("msedge"),
        shutil.which("google-chrome"), shutil.which("chromium"),
    ]
    for path in candidates:
        if path and Path(path).exists():
            return str(path)
    raise SystemExit("no Chrome or Edge found — set CHROME to the executable")


def to_pdf(html: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="verifypdf-"))
    page = work / "verify.html"
    page.write_text(html, encoding="utf-8")
    url = "file:///" + str(page).replace("\\", "/")
    subprocess.run(
        [find_chrome(), "--headless=new", "--disable-gpu",
         f"--user-data-dir={work / 'profile'}",
         "--no-pdf-header-footer", "--virtual-time-budget=5000",
         f"--print-to-pdf={out}", url],
        check=True, capture_output=True, timeout=240)
    if not out.exists():
        raise SystemExit("Chrome ran but wrote no PDF")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--html", action="store_true",
                    help="also keep the intermediate HTML next to the PDF")
    args = ap.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    today = dt.date.today().strftime("%-d %B %Y" if os.name != "nt"
                                     else "%#d %B %Y")
    html = build_html(today)
    if args.html:
        args.out.with_suffix(".html").write_text(html, encoding="utf-8")
    out = to_pdf(html, args.out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
