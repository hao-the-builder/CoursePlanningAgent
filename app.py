"""The Streamlit app (Phase 6).

    streamlit run app.py

Four steps down one column: a form, a short chat, generate, download. One
column on purpose — it is the layout that survives a phone, and a student
checking their plan on the way to class is the likely reader.

Nothing here computes anything. The form builds a StudentProfile, the agent
plans, `planner.validate` judges, and `outputs/` writes the files. This
module's whole job is to collect input, show what came back, and hand over
the downloads.
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

from outputs.docx_builder import build_document  # noqa: E402
from outputs.xlsx_builder import build_workbook  # noqa: E402
from planner.agent import plan_for  # noqa: E402
from planner.intake import ExchangePlan, StudentProfile  # noqa: E402
from planner.llm import LLMUnavailable, backend_name, chat, prompt_text  # noqa: E402
from planner.terms import sort_key, term_sequence  # noqa: E402
from planner.tools import catalog, common_core_for, get_program, list_programs  # noqa: E402
from schema import PlannedCourse, Tier  # noqa: E402

load_dotenv()

# Streamlit Community Cloud supplies configuration through `st.secrets`, not
# through the environment, so planner/llm.py would never see the key. Copy it
# across once, without overwriting anything already set locally. The key is
# only ever read from here — it is never written to a file, a log or an
# output (hard rule 8).
for _name in ("LLM_BACKEND", "ANTHROPIC_API_KEY", "MODEL_FAST", "MODEL_STRONG"):
    try:
        if _name in st.secrets and not os.environ.get(_name):
            os.environ[_name] = str(st.secrets[_name])
    except Exception:          # no secrets.toml at all, which is normal
        break

MAX_GENERATIONS = 3
MAX_CHAT_TURNS = 12
COHORT = "2026-27"

TIER_BADGE = {
    Tier.VERIFIED: ("✅", "verified", "Checked by hand against the official "
                                      "requirement PDF."),
    Tier.AUTO: ("🟡", "auto-extracted", "Read automatically from the official "
                                        "requirement PDF and auto-checked, "
                                        "but not yet verified by a person."),
    Tier.UNSUPPORTED: ("🔴", "unsupported", "This program could not be read "
                                            "reliably. No plan will be "
                                            "produced for it."),
}

st.set_page_config(page_title="HKUST course planner", page_icon="🎓",
                   layout="centered")


# ------------------------------------------------------------- helpers --

def state(key: str, default):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


@st.cache_data(show_spinner=False)
def programs() -> list[dict]:
    return list_programs()


@st.cache_data(show_spinner=False)
def course_choices() -> list[str]:
    return [f"{code} — {course.title}" for code, course
            in sorted(catalog().items())]


def code_of(choice: str) -> str:
    return choice.split(" — ", 1)[0]


def tier_note(code: str) -> None:
    program = get_program(code)
    mark, word, explanation = TIER_BADGE[program.tier]
    body = (f"**{mark} Data tier: {word}.** {explanation}  \n"
            f"Source: {program.source_url}  \n"
            f"**Whatever this app produces, check it with your academic "
            f"advisor before you register.**")
    (st.error if program.tier is Tier.UNSUPPORTED else st.info)(body)


def label_of(row: dict) -> str:
    return f"{row['code']} — {row['title']}"


# ---------------------------------------------------------- 1. the form --

st.title("🎓 HKUST course planner")
st.caption("Turns your degree requirements into a term-by-term plan. It "
           "recommends and writes files — it never registers you for "
           "anything, contacts anyone, or predicts a grade.")

rows = programs()
majors = [r for r in rows if r["kind"] == "major"]
minors = [r for r in rows if r["kind"] == "minor"]

st.header("1 · About you")

cohort = st.selectbox("Intake cohort", [COHORT], index=0,
                      help="Requirements differ by the year you started. "
                           "Only 2026-27 is supported.")

schools = sorted({r["school"] for r in majors if r["school"]})
school = st.selectbox("School", ["Any"] + schools)
visible = [r for r in majors if school == "Any" or r["school"] == school]
visible.sort(key=lambda r: (r["tier"] != "verified", r["code"]))

major_label = st.selectbox(
    "Major", [label_of(r) for r in visible],
    help="Programs with a track (for example Mathematics) are listed once "
         "per track, because the track decides the requirements.")
major = code_of(major_label) if major_label else None

minor_label = st.selectbox("Minor (optional)",
                           ["none"] + [label_of(r) for r in minors])
minor = None if minor_label == "none" else code_of(minor_label)

if major:
    tier_note(major)

st.header("2 · How you want to study")

low, high = st.slider("Credits per term", 3, 21, (12, 18),
                      help="The Academic Regulations allow 12 to 18 in a "
                           "Regular Term without the Dean's approval.")
spread = st.radio("Workload shape",
                  ["even", "front", "back"],
                  format_func={"even": "Even across the degree",
                               "front": "Front-loaded — free up later years",
                               "back": "Back-loaded — gentler start"}.get,
                  horizontal=False)

terms = term_sequence(cohort, 4, use_summer=True, use_winter=True)
regular = [t.label for t in terms if t.is_regular]

free_terms = st.multiselect("Terms to keep free", regular,
                            help="A term with no courses at all.")
graduate_early = st.checkbox("Graduate early if that is possible")

use_summer = st.checkbox("Willing to take summer courses")
use_winter = st.checkbox("Willing to take winter courses")
reserve_summer = st.checkbox("Keep summers for internships")

going = st.checkbox("I want to go on exchange")
exchange = None
if going:
    exchange_terms = st.multiselect("Exchange term(s)", regular,
                                    max_selections=2)
    host = st.text_input("Host university (if you know it)")
    purposes = st.multiselect(
        "Use the exchange for", ["major", "common_core", "minor", "free"],
        default=["major"],
        format_func={"major": "Major requirements",
                     "common_core": "Common Core",
                     "minor": "Minor", "free": "Free electives"}.get)
    exchange = ExchangePlan(terms=exchange_terms, host_university=host or None,
                            purposes=purposes)
    st.caption("Exchange credits are never counted as met until the mapping "
               "is approved. They are shown separately throughout.")

gpa = st.number_input("GPA target (optional)", 0.0, 4.3, 0.0, step=0.1,
                      help="Used for workload advice only. No grade is ever "
                           "predicted.")

with st.expander("Courses you have already done"):
    taken_choices = st.multiselect("Already taken", course_choices())
    taken_term = st.selectbox("…in which term", ["Y1 Fall"] + regular)
    current_choices = st.multiselect("Taking right now", course_choices())
    st.markdown("**Transfer credits**")
    mapped = st.multiselect("Transferred, mapped to an HKUST course",
                            course_choices())
    unspecified = st.number_input(
        "Transferred credits with no named course", 0.0, 60.0, 0.0, step=3.0,
        help="The Academic Regulations call this credit-only transfer. It "
             "counts toward the 120 as free electives and nothing else.")

with st.expander("Anything else worth knowing"):
    direction = st.text_input("Direction within the major",
                              placeholder="AI, systems, finance…")
    career = st.text_input("Career interests",
                           placeholder="industry, grad school, a startup…")
    background = st.text_area("Background", height=70,
                              placeholder="IB / HKDSE / A-level, maths, "
                                          "programming experience…")


def build_profile() -> StudentProfile:
    return StudentProfile(
        cohort=cohort, major=major, minor=minor,
        school=next((r["school"] for r in rows if r["code"] == major), None),
        programme_years=4, workload_min=float(low), workload_max=float(high),
        spread=spread, free_terms=free_terms, graduate_early=graduate_early,
        use_summer=use_summer, use_winter=use_winter,
        reserve_summer_for_internship=reserve_summer, exchange=exchange,
        gpa_target=gpa or None,
        taken=[PlannedCourse(code=code_of(c), term=taken_term, status="taken")
               for c in taken_choices],
        current=[PlannedCourse(code=code_of(c), term="Y1 Fall",
                               status="current") for c in current_choices],
        transfer_credits=[PlannedCourse(code=code_of(c), term="Transfer",
                                        status="transfer")
                          for c in mapped],
        unspecified_transfer_credits=float(unspecified),
        direction=direction, career_interests=career, background=background,
        notes=list(st.session_state.get("notes", [])),
    )


# ---------------------------------------------------------- 3. the chat --

st.header("3 · Anything to add")
st.caption("Optional. Tell the planner anything the form did not cover and "
           "it will ask follow-ups.")

history = state("chat", [])
state("notes", [])

for speaker, message in history:
    with st.chat_message(speaker):
        st.write(message)

if len(history) >= MAX_CHAT_TURNS * 2:
    st.warning(f"That is {MAX_CHAT_TURNS} turns — enough for one sitting. "
               f"Generate a plan, or reload to start again.")
elif prompt := st.chat_input("e.g. I would rather not take 8am classes"):
    history.append(("user", prompt))
    st.session_state["notes"].append(prompt)
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"), st.spinner("Thinking…"):
        try:
            said = "\n".join(f"{who}: {what}" for who, what in history)
            reply = chat(
                f"The student is planning {major or 'a degree'} at HKUST. "
                f"They said:\n\n{said}\n\nAcknowledge it in one sentence and "
                f"ask at most one follow-up question, only if it would change "
                f"the plan. Never promise a grade or an outcome.",
                task="intake", system=prompt_text("system"))
            answer = reply.text.strip() or "Noted."
        except LLMUnavailable as exc:
            answer = (f"Noted — I have written that down. (No model is "
                      f"connected, so I cannot reply properly: {exc})")
        history.append(("assistant", answer))
        st.write(answer)


# ------------------------------------------------------ 4. generate --

st.header("4 · Generate")

used = state("generations", 0)
st.caption(f"Backend: `{backend_name()}` · {used} of {MAX_GENERATIONS} "
           f"generations used this session")

if used >= MAX_GENERATIONS:
    st.warning("You have used this session's generations. Reload the page to "
               "start again.")
    go = False
else:
    go = st.button("Plan my degree", type="primary", use_container_width=True,
                   disabled=not major)

if go:
    profile = build_profile()
    with st.spinner("Reading the requirements, drafting and checking…"):
        try:
            st.session_state["result"] = plan_for(profile, paths=3)
            st.session_state["profile"] = profile
            st.session_state["generations"] = used + 1
        except Exception as exc:                      # noqa: BLE001
            st.session_state["result"] = None
            st.error(f"That did not finish: {exc}")

result = st.session_state.get("result")
profile = st.session_state.get("profile")

if result is not None and profile is not None:
    if result.status == "needs_input":
        st.warning(result.message)
        for question in result.questions:
            st.markdown(f"- {question}")
    elif result.status == "unsupported":
        st.error(result.message)
        st.caption("Hard rule 5: a program that cannot be read reliably does "
                   "not get a plan. Pick a track if your program has one, or "
                   "ask your department.")
    else:
        if result.message:
            st.warning(result.message)

        program = get_program(profile.major)
        minor_program = get_program(profile.minor) if profile.minor else None
        core = common_core_for(profile.major)

        for index, path in enumerate(result.paths, 1):
            report = path.report
            mark = "✅" if path.ok else "⚠️"
            with st.expander(f"{mark} Path {index}: {path.name}",
                             expanded=index == 1):
                if path.summary:
                    st.write(path.summary)

                st.bar_chart(
                    {"credits": {term: credits for term, credits in
                                 sorted(report.per_term.items(),
                                        key=lambda kv: sort_key(kv[0]))}},
                    y="credits", height=200)

                left, middle, right = st.columns(3)
                left.metric("Confirmed credits",
                            f"{report.credits.confirmed:g}")
                middle.metric("Pending exchange",
                              f"{report.credits.exchange_pending:g}")
                right.metric("Problems",
                             f"{len(report.errors)} / "
                             f"{len(report.warnings)} warn")

                if path.why_it_fits:
                    st.markdown("**Why this one**")
                    for reason in path.why_it_fits:
                        st.markdown(f"- {reason}")
                if path.trade_offs:
                    st.markdown("**What it costs you**")
                    for cost in path.trade_offs:
                        st.markdown(f"- {cost}")

                if report.errors:
                    st.error("Unresolved problems — these must be settled "
                             "before you register:")
                    for issue in report.errors:
                        st.markdown(f"- {issue.message}")
                with st.expander(f"Things to check "
                                 f"({len(report.warnings)})"):
                    for issue in report.warnings + report.infos:
                        st.markdown(f"- {issue.message}")

        st.header("5 · Download")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, path in enumerate(result.paths, 1):
                book = build_workbook(path, profile, program, minor_program,
                                      core, catalog())
                buffer = io.BytesIO()
                book.save(buffer)
                name = f"{profile.major}-path{index}-{stamp}.xlsx"
                archive.writestr(name, buffer.getvalue())
                st.download_button(
                    f"⬇️ Path {index}: {path.name} (.xlsx)",
                    buffer.getvalue(), file_name=name,
                    mime="application/vnd.openxmlformats-officedocument."
                         "spreadsheetml.sheet",
                    use_container_width=True)

            document = build_document(result, profile, program, minor_program,
                                      core, catalog())
            buffer = io.BytesIO()
            document.save(buffer)
            doc_name = f"{profile.major}-plan-{stamp}.docx"
            archive.writestr(doc_name, buffer.getvalue())
            st.download_button(
                "⬇️ The write-up for all paths (.docx)", buffer.getvalue(),
                file_name=doc_name,
                mime="application/vnd.openxmlformats-officedocument."
                     "wordprocessingml.document",
                use_container_width=True)

        st.download_button("⬇️ Everything, zipped", bundle.getvalue(),
                           file_name=f"{profile.major}-plans-{stamp}.zip",
                           mime="application/zip",
                           use_container_width=True)
        if result.log_path:
            st.caption(f"Run log: `{result.log_path.name}`")

st.divider()
st.caption("Built for a course project. Requirements come from HKUST's "
           "official 2026-27 Program & Course Catalog and Academic "
           "Regulations; every plan shows its data tier and its sources. "
           "Verify with your academic advisor before you register.")
