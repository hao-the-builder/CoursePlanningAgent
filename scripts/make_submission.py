"""Build the submission document: one .docx, and a .pdf if Word is there.

The brief asks for a demo link, a test log of about 300 words, and three to
five scenarios for reviewers to start from. The log and the scenarios already
live in `TEST_LOG.md` and `SAMPLE_QUERIES.md`, so this reads those files
rather than restating them - a submission that disagrees with the repo is
worse than no submission.

    python scripts/make_submission.py

Writes `submission/`. Convert to PDF by opening the .docx in Word and using
Save As -> PDF, or let this script do it (it tries Word automation on
Windows).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "submission"
NAME = "HKUST-Course-Planner-Submission"

GREY = RGBColor(0x55, 0x55, 0x55)

COVER = """The prototype plans an HKUST undergraduate degree term by term, for the
2026-27 intake. A student says what they are studying, how heavy they want
each term, whether they want the load front- or back-loaded and which terms
they want to keep free; the agent returns a term-by-term plan that satisfies
the programme's published requirements, or says plainly why no plan can.

It runs as a Dify workflow. Every course code, credit value, prerequisite and
requirement rule comes from a small read-only service over HTTP, which reads
data extracted from HKUST's own published PDFs. The model's only job is to
choose between options the data allows and explain the result, so it cannot
invent a course that reaches the student: every plan is checked by a validator
before it is returned, and checked again afterwards.
"""

ACCESS = """## The demo link

**https://kxhijnfqbggbqkjrpsqzbd.streamlit.app**

Nothing to install and nothing to sign in to. Fill in the form, press
generate, and you get two or three term-by-term plans, each with its credit
totals, its validation result and downloadable `.xlsx` and `.docx` files. The
course data ships with the app, so this link does not depend on anyone's
machine being switched on.

**What is running there.** Every plan, every credit total and every
requirement check is deterministic Python over data extracted from HKUST's
published PDFs - which is all of the planning. What the link does not include
is the model-written prose, because it runs with no language model configured.
The app says so where that prose would be, rather than leaving a blank that
reads like an error. Nothing shown is a model's guess.

## The agentic workflow

The planning agent proper runs as a **Dify workflow**, submitted as
`dify/course-planner.yml` and as an export from the live app. It is the same
deterministic tools, reached over HTTP, with a model choosing between the
options the data allows and explaining the result.

**Its data service is not hosted.** Several free providers refused a sign-up
or wanted a card in the time available, so the HTTP service the workflow calls
still runs on the developer's machine. To see the workflow end to end, start
it yourself - two commands, no account, no API key, about two minutes:

```
pip install -r service/requirements.txt
python -m service.tool_api --host 0.0.0.0 --port 8601
```

Then open http://localhost:8601/health. It should report 129 programs, 5 of
them human-verified, and 1649 courses. That endpoint needs no token, so it
confirms the data side on its own. `dify/SETUP.md` has the rest: importing the
workflow and pointing it at your own address. The run on page 5 of this
document came from exactly that path.

This is stated plainly because a link with a condition attached is worth more
than one that fails silently.
"""

FILES = """| File | What it is |
|---|---|
| `dify/course-planner.yml` | The workflow itself, importable into any Dify |
| `dify/README.md` | Why it is built this way, and what runs where |
| `dify/SETUP.md` | How to run it, step by step |
| `dify/DEPLOY.md` | How to put the data service online |
| `dify/openapi.json` | The four tools as a standard API description |
| `TEST_LOG.md` | The test log, also reproduced in this document |
| `SAMPLE_QUERIES.md` | The scenarios, also reproduced in this document |
| `DECISIONS.md` | Every design decision, with its reasoning and how to reverse it |

The workflow file contains no password. The service address and token are
supplied at run time and a Dify export leaves secrets blank, so the file is
safe to hand in as it stands.
"""


# --------------------------------------------------------------- rendering --

def add_markdown(document: Document, text: str) -> None:
    """Enough Markdown for the files in this repo: headings, tables, lists,
    fenced code, block quotes and inline bold or code."""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]

        if line.startswith("```"):
            index += 1
            block = []
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            para = document.add_paragraph()
            run = para.add_run("\n".join(block))
            run.font.name = "Consolas"
            run.font.size = Pt(8.5)
            para.paragraph_format.left_indent = Inches(0.25)
            para.paragraph_format.space_after = Pt(10)
            continue

        if line.startswith("|") and index + 1 < len(lines) \
                and set(lines[index + 1].replace("|", "").strip()) <= set("-: "):
            rows = []
            while index < len(lines) and lines[index].startswith("|"):
                cells = [c.strip() for c in lines[index].strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):
                    rows.append(cells)
                index += 1
            width = max(len(r) for r in rows)
            table = document.add_table(rows=0, cols=width)
            table.style = "Light Grid Accent 1"
            for position, cells in enumerate(rows):
                cursor = table.add_row().cells
                for column in range(width):
                    value = cells[column] if column < len(cells) else ""
                    cursor[column].text = ""
                    para = cursor[column].paragraphs[0]
                    add_inline(para, value, bold=position == 0)
                    for run in para.runs:
                        run.font.size = Pt(9)
            document.add_paragraph()
            continue

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            document.add_heading(line.lstrip("# ").strip(), level=min(level, 3))
            index += 1
            continue

        if line.startswith(("- ", "* ")):
            para = document.add_paragraph(style="List Bullet")
            add_inline(para, line[2:])
            index += 1
            continue

        if line.startswith("> "):
            para = document.add_paragraph()
            add_inline(para, line[2:])
            para.paragraph_format.left_indent = Inches(0.3)
            for run in para.runs:
                run.font.color.rgb = GREY
                run.italic = True
            index += 1
            continue

        if line.strip() == "---":
            index += 1
            continue

        if line.strip():
            para = document.add_paragraph()
            add_inline(para, line)
            # Join wrapped lines into one paragraph.
            index += 1
            while index < len(lines) and lines[index].strip() \
                    and not lines[index].startswith(("#", "|", "- ", "* ",
                                                     "> ", "```")) \
                    and lines[index].strip() != "---":
                para.add_run(" ")
                add_inline(para, lines[index])
                index += 1
            continue

        index += 1


def add_inline(para, text: str, bold: bool = False) -> None:
    """**bold** and `code`, which is all these documents use."""
    for piece in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**"):
            run = para.add_run(piece[2:-2])
            run.bold = True
        elif piece.startswith("`") and piece.endswith("`"):
            run = para.add_run(piece[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
        else:
            run = para.add_run(piece)
        if bold:
            run.bold = True


def read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def strip_title(text: str) -> str:
    """Drop a file's own H1; this document supplies its own headings."""
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:]).lstrip("\n")
    return text


def main() -> int:
    OUT.mkdir(exist_ok=True)
    document = Document()

    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    title = document.add_heading("HKUST Course Planning Agent", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    subtitle = document.add_paragraph()
    run = subtitle.add_run("Prototype, test log and reviewer scenarios "
                           "· cohort 2026-27")
    run.italic = True
    run.font.color.rgb = GREY

    document.add_heading("What it does", level=1)
    add_markdown(document, COVER)

    add_markdown(document, ACCESS)

    document.add_page_break()
    document.add_heading("Scenarios to try first", level=1)
    add_markdown(document, strip_title(read("SAMPLE_QUERIES.md")))

    document.add_page_break()
    document.add_heading("Test log", level=1)
    add_markdown(document, strip_title(read("TEST_LOG.md")))

    document.add_page_break()
    document.add_heading("An actual run", level=1)
    add_markdown(document,
                 "Produced by the workflow's own code, against the live data "
                 "service, for the first scenario above. Nothing here is "
                 "retyped.\n")
    add_markdown(document, strip_title(read("dify/example-run.md")))

    document.add_page_break()
    document.add_heading("Files submitted alongside this document", level=1)
    add_markdown(document, FILES)

    docx = OUT / f"{NAME}.docx"
    document.save(docx)
    print(f"wrote {docx.relative_to(REPO)}")

    pdf = OUT / f"{NAME}.pdf"
    if to_pdf(docx, pdf):
        print(f"wrote {pdf.relative_to(REPO)}")
    else:
        print(f"could not make a PDF automatically. Open {docx.name} in Word "
              f"and use File -> Save As -> PDF.")
    return 0


def to_pdf(docx: Path, pdf: Path) -> bool:
    """Ask Word to export it. Word is the one converter on this machine."""
    script = (
        "$word = New-Object -ComObject Word.Application; "
        "$word.Visible = $false; "
        f"$doc = $word.Documents.Open('{docx}', [ref]$false, [ref]$true); "
        f"$doc.SaveAs([ref]'{pdf}', [ref]17); "
        "$doc.Close([ref]$false); $word.Quit()")
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                              capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and pdf.exists()


if __name__ == "__main__":
    sys.exit(main())
