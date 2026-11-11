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
LINK = RGBColor(0x0B, 0x57, 0xD0)
PALE = "EAF3EA"

APP_URL = "https://kxhijnfqbggbqkjrpsqzbd.streamlit.app"

COVER = """The prototype plans an HKUST undergraduate degree term by term, for the
2026-27 intake. A student says what they are studying, how heavy they want
each term, whether they want the load front- or back-loaded and which terms
they want to keep free; the agent returns a term-by-term plan that satisfies
the programme's published requirements, or says plainly why no plan can.

How it is built. Every course code, credit value, prerequisite and requirement
rule comes from structured data extracted from HKUST's own published PDFs, and
the agent reaches it through deterministic Python rather than recalling it. The model's only job is to
choose between options the data allows and explain the result, so it cannot
invent a course that reaches the student: every plan is checked by a validator
before it is returned, and checked again afterwards.
"""

ACCESS = """## How to use it

Open the link above. There is nothing to install, nothing to sign in to and no
key to obtain. Choose a major, say how heavy you want each term and whether
you want the load front- or back-loaded, name any term you want kept free, and
press **Plan my degree**.

You get two or three complete term-by-term plans. Each shows its credits per
term, whether it passed every check, and what could not be checked. Each plan
downloads as a spreadsheet whose totals are live Excel formulas - edit the plan
and the progress figures follow - and one document covers all of them.

**Start with the five scenarios on the next page.** They are ordered so the
most informative comes first, and every setting is given.

## What to expect, and what it will not do

**It may need to wake up.** The host puts an idle app to sleep. If you are
shown a button asking to get the app back up, press it and give it about half
a minute. That is the host, not the app.

**No written explanations on the hosted version.** It runs with no language
model configured, so where the system would normally explain its reasoning you
will find a line saying no model ran. Every plan, credit total, prerequisite
check and requirement check is deterministic Python over HKUST's published
data, so nothing factual is missing - and nothing shown is a model's guess.
The agentic version, a Dify workflow that adds a model's reasoning on top of
the same tools, is submitted as a file rather than hosted; `dify/SETUP.md`
runs it in about two minutes.

**One intake cohort.** 2026-27 only. Requirements differ by the year a student
started, and we extracted one year.

**Three levels of confidence in the data, and the app shows which you are
getting.** 5 programs have been checked line by line against the official PDF
by a person. 92 more were extracted by machine and carry a visible warning.
32 refuse to be planned at all, because their rules could not be read reliably
- scenario 4 is one of those, and the refusal is the feature.

**No term-offering data.** HKUST's class schedule disallows automated access,
so no course in any plan has been checked against the terms it is actually
offered in. Every plan says so. This is the largest single gap and it is not
one we can close without permission.

**Nothing here is endorsed by HKUST**, and every plan says to check it with an
academic advisor before registering. The agent only recommends and writes
files: it never registers for a course, emails anyone or submits anything.
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

def add_hyperlink(para, url: str, text: str, size: float = 10.5,
                  bold: bool = False):
    """A clickable link. python-docx has no API for one, so the relationship
    and the `w:hyperlink` element are written by hand. Word carries it
    through to the PDF, so the link works in the submitted file."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    part = para.part
    relation = part.relate_to(url, RT.HYPERLINK, is_external=True)

    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), relation)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")

    colour = OxmlElement("w:color")
    colour.set(qn("w:val"), "0B57D0")
    properties.append(colour)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(underline)
    points = OxmlElement("w:sz")
    points.set(qn("w:val"), str(int(size * 2)))
    properties.append(points)
    if bold:
        properties.append(OxmlElement("w:b"))

    run.append(properties)
    label = OxmlElement("w:t")
    label.text = text
    run.append(label)
    link.append(run)
    para._p.append(link)
    return link


def shade(cell, colour: str) -> None:
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    fill = OxmlElement("w:shd")
    fill.set(qn("w:val"), "clear")
    fill.set(qn("w:fill"), colour)
    cell._tc.get_or_add_tcPr().append(fill)


def add_link_banner(document, url: str) -> None:
    """The first thing on the page: what to click, and what it is."""
    table = document.add_table(rows=1, cols=1)
    cell = table.rows[0].cells[0]
    shade(cell, PALE)

    label = cell.paragraphs[0]
    run = label.add_run("THE PROTOTYPE — TRY IT HERE")
    run.bold = True
    run.font.size = Pt(8.5)
    run.font.color.rgb = GREY
    label.paragraph_format.space_after = Pt(2)

    address = cell.add_paragraph()
    add_hyperlink(address, url, url, size=14, bold=True)
    address.paragraph_format.space_after = Pt(2)

    note = cell.add_paragraph()
    run = note.add_run("Nothing to install and no sign-in. Choose a major, "
                       "set how heavy you want each term, and press generate.")
    run.font.size = Pt(9.5)
    run.font.color.rgb = GREY
    document.add_paragraph()

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

    add_link_banner(document, APP_URL)

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
