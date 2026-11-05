"""Phase 6 tests: the Streamlit flow, driven headlessly.

`AppTest` runs `app.py` the way Streamlit does, so these exercise the real
widgets and the real agent — on the stub backend, so no model is called.
What they cannot check is how it looks; phone width is a visual check and is
noted as such in the README.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(REPO / "app.py")
warnings.filterwarnings("ignore")


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "stub")


def started() -> AppTest:
    return AppTest.from_file(APP, default_timeout=180).run()


def select(app: AppTest, label: str):
    return next(s for s in app.selectbox if s.label == label)


def pick_major(app: AppTest, code: str) -> AppTest:
    box = select(app, "Major")
    choice = next(o for o in box.options if o.startswith(f"{code} —"))
    return box.set_value(choice).run()


@pytest.fixture(scope="module")
def planned() -> AppTest:
    """One full run, reused by the tests that read its results."""
    warnings.filterwarnings("ignore")
    app = AppTest.from_file(APP, default_timeout=300).run()
    box = next(s for s in app.selectbox if s.label == "Major")
    app = box.set_value(next(o for o in box.options
                             if o.startswith("COMP —"))).run()
    return app.button[0].click().run()


# --------------------------------------------------------------- it runs --

def test_the_app_starts_without_an_exception():
    app = started()
    assert not app.exception
    assert app.title[0].value.endswith("HKUST course planner")
    assert [h.value for h in app.header][:4] == [
        "1 · About you", "2 · How you want to study", "3 · Anything to add",
        "4 · Generate"]


def test_the_caption_says_what_the_app_will_not_do():
    """The autonomy dial, where the student can see it."""
    text = " ".join(c.value for c in started().caption)
    assert "never registers you" in text
    assert "predicts a grade" in text or "predict a grade" in text


def test_only_the_supported_cohort_is_offered():
    cohort = select(started(), "Intake cohort")
    assert cohort.options == ["2026-27"]


def test_the_major_list_covers_the_catalog_and_names_its_tracks():
    options = select(started(), "Major").options
    assert len(options) >= 100
    assert any(o.startswith("MATH-STA —") for o in options)
    assert any("Statistics Track" in o for o in options)


# ------------------------------------------------------------- the tier --

def test_an_auto_extracted_program_shows_an_amber_badge_and_its_source():
    app = pick_major(started(), "COMP")
    note = app.info[0].value
    assert "auto-extracted" in note
    assert "academic advisor" in note
    assert "ugadmin.hkust.edu.hk" in note


def test_an_unsupported_program_shows_a_red_badge_before_anything_is_planned():
    """Hard rule 5, visible at the point the student picks the program."""
    app = pick_major(started(), "MATH")
    assert app.error, "an unsupported program must not look fine"
    assert "unsupported" in app.error[0].value
    assert "No plan will be produced" in app.error[0].value


def test_planning_an_unsupported_program_refuses_and_offers_no_download():
    app = pick_major(started(), "MATH")
    app = app.button[0].click().run()
    assert not app.exception
    messages = " ".join(e.value for e in app.error)
    assert "cannot be planned reliably" in messages
    assert app.download_button == []


# -------------------------------------------------------------- results --

def test_a_supported_major_produces_paths_with_charts_and_metrics(planned):
    assert not planned.exception
    assert len(planned.expander) >= 3
    labels = [e.label for e in planned.expander]
    assert sum(1 for label in labels if label.startswith(("✅ Path", "⚠️ Path"))) >= 2
    assert planned.metric, "no credit metrics were shown"
    assert any(m.label == "Confirmed credits" for m in planned.metric)
    assert any(m.label == "Pending exchange" for m in planned.metric)


def test_every_path_offers_a_spreadsheet_and_there_is_one_document(planned):
    labels = [b.label for b in planned.download_button]
    sheets = [label for label in labels if label.endswith("(.xlsx)")]
    documents = [label for label in labels if label.endswith("(.docx)")]
    assert len(sheets) >= 2
    assert len(documents) == 1
    assert any("zipped" in label for label in labels)


# ------------------------------------------------------- abuse limits --

def test_the_session_has_a_generation_limit():
    import app as module

    assert module.MAX_GENERATIONS <= 5
    assert module.MAX_CHAT_TURNS <= 20

    app = pick_major(started(), "COMP")
    for _ in range(module.MAX_GENERATIONS):
        app = app.button[0].click().run()
    # The counter is read when the page renders, so the limit shows on the
    # run after the last generation, not during it.
    app = app.run()
    warnings_shown = " ".join(w.value for w in app.warning)
    assert "used this session's generations" in warnings_shown
    assert app.button == [] or app.button[0].disabled


def test_the_footer_names_the_sources_and_the_advisor():
    text = " ".join(c.value for c in started().caption)
    assert "Academic Regulations" in text
    assert "academic advisor" in text
