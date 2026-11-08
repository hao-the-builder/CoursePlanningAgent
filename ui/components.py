"""HTML fragments for `app.py`.

Each one renders data the validator already computed. Nothing here decides
anything: a term is "heavy" here for exactly the reason it is heavy in the
spreadsheet, and the words match the workbook's legend so the two cannot
disagree in front of the student.
"""
from __future__ import annotations

import html

import streamlit as st

from planner.terms import sort_key

# The same thresholds the workbook writes into its load-tag formula
# (outputs/xlsx_builder.py): 18 and over is heavy, under 12 is light, zero is
# a free term. One source of meaning, two renderings.
HEAVY = 18.0
LIGHT = 12.0


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def write(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def hero(title: str, lede: str, eyebrow: str = "") -> None:
    write(f'<div class="hero">'
          f'{f"<p class=\'eyebrow\'>{_esc(eyebrow)}</p>" if eyebrow else ""}'
          f'<h1>{_esc(title)}</h1>'
          f'<p class="lede">{_esc(lede)}</p>'
          f'</div>')


def step_note(text: str) -> None:
    """The line under a numbered step heading."""
    write(f'<p class="step-note">{_esc(text)}</p>')


def pill(text: str, kind: str = "flat") -> str:
    return f'<span class="pill {kind}">{_esc(text)}</span>'


def chips(*pills: str) -> None:
    write(f'<div class="chips">{"".join(p for p in pills if p)}</div>')


def term_class(label: str, credits: float, exchange_terms: set[str]) -> str:
    if label in exchange_terms:
        return "exchange"
    if credits <= 0:
        return "free"
    if credits >= HEAVY:
        return "heavy"
    if credits < LIGHT:
        return "light"
    return ""


def term_strip(per_term: dict[str, float], exchange_terms: set[str]) -> None:
    """One bar per term, height by credits, colour by what the load means.

    A bar chart would draw a 9-credit term and a free term as the same kind of
    thing, differing only in height. They are not the same thing — one needs
    checking against the minimum load, the other is a term the student asked
    to keep — so the colour carries the tag and the number is always printed.
    """
    if not per_term:
        return
    order = sorted(per_term.items(), key=lambda kv: sort_key(kv[0]))
    tallest = max([c for _, c in order] + [1.0])
    cells = []
    for label, credits in order:
        kind = term_class(label, credits, exchange_terms)
        height = max(4, round(62 * credits / tallest))
        short = label.replace("Y", "Y").replace(" ", "<br>")
        cells.append(
            f'<div class="t {kind}">'
            f'<span class="n">{credits:g}</span>'
            f'<span class="bar" style="height:{height}px"></span>'
            f'<span class="l">{short}</span>'
            f'</div>')
    write(f'<div class="strip">{"".join(cells)}</div>')

    keys = [("var(--accent)", "normal"), ("#c9a227", "light — check minimum"),
            ("#a12a22", "heavy"), ("var(--line-strong)", "free"),
            ("#2f7d8f", "exchange")]
    shown = {term_class(label, c, exchange_terms) for label, c in order}
    wanted = {"": "normal", "light": "light — check minimum", "heavy": "heavy",
              "free": "free", "exchange": "exchange"}
    legend = "".join(
        f'<span><i style="background:{colour}"></i>{_esc(name)}</span>'
        for colour, name in keys
        if name in {wanted[k] for k in shown})
    write(f'<div class="legend">{legend}</div>')

