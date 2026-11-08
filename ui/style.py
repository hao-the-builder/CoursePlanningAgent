"""The stylesheet.

Written against the `apple-design` skill in `D:/Skills for AI`, which is a
translation of Apple's design talks for the web. The parts of it that earn
their place in a form-and-tables app, and what they mean here:

* **Typography (§15).** Tracking is size-specific — tight and negative on the
  display line, near zero on body, slightly positive on the small uppercase
  labels. Leading runs inverse to size. Hierarchy comes from weight, size and
  leading together, not size alone. The system font is the default because it
  already ships optical sizing and legibility tuning.
* **Response (§1).** Feedback lives on the press: every control has an
  `:active` state that fires in 100ms. Nothing waits for a release to show it
  was hit.
* **Materials (§12).** The top bar is a translucent layer with content
  scrolling under it, and the seam where they meet is a soft gradient rather
  than a 1px rule. One level of translucency only — a light material on a
  light material stops being legible.
* **Restraint (§16.6).** Motion is used where it explains something (a result
  arriving, a press landing) and nowhere else. No decorative animation.
* **Accessibility (§14).** Reduced motion, reduced transparency and increased
  contrast each get an answer, because a gentler equivalent is the point, not
  switching the feedback off.

The surface is Streamlit, so this is written against its DOM: the
`data-testid` hooks are Streamlit's own and are the stable way in. Where a
rule targets one, the comment says which widget it is.
"""
from __future__ import annotations

import streamlit as st

# HKUST navy, matching .streamlit/config.toml's primaryColor, plus the
# semantic colours the spreadsheet legend already uses, so a warning means the
# same thing in the browser and in the workbook.
TOKENS = """
:root {
  --ink:            #11161d;
  --ink-2:          #39414d;
  --ink-3:          #68717e;
  --ink-4:          #8c94a1;
  --line:           #e3e6eb;
  --line-strong:    #cfd4dc;
  --ground:         #f6f7f9;
  --surface:        #ffffff;
  --surface-sunk:   #f1f3f6;
  --accent:         #1f3864;
  --accent-press:   #16294a;
  --accent-wash:    #eef1f7;
  --ok:             #1b6b45;
  --ok-wash:        #e8f4ee;
  --warn:           #8a5a00;
  --warn-wash:      #fdf5e4;
  --bad:            #a12a22;
  --bad-wash:       #fbeceb;

  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 16px;

  --shadow-sm: 0 1px 2px rgba(17, 22, 29, .06);
  --shadow-md: 0 2px 6px rgba(17, 22, 29, .07), 0 8px 24px rgba(17, 22, 29, .05);
}
"""

CSS = TOKENS + """
/* ---------------------------------------------------------- the page -- */

html, body, [data-testid="stAppViewContainer"] {
  background: var(--ground);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui,
               "Helvetica Neue", Arial, sans-serif;
  font-synthesis-weight: none;
  -webkit-font-smoothing: antialiased;
}
[data-testid="stMainBlockContainer"] {
  max-width: 48rem;
  padding: 1.25rem 1rem 5rem;
}

/* The top bar is a material, not a strip: content passes under it (§12). */
[data-testid="stHeader"] {
  background: rgba(246, 247, 249, .72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: none;
}
/* Scroll edge, not a divider: the seam fades instead of ruling. */
[data-testid="stHeader"]::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: -14px;
  height: 14px; pointer-events: none;
  background: linear-gradient(rgba(246, 247, 249, .55), rgba(246, 247, 249, 0));
}

/* ------------------------------------------------------- typography -- */

h1, h2, h3, h4 { color: var(--ink); font-weight: 650; }
h1 { font-size: clamp(1.9rem, 5vw, 2.4rem); line-height: 1.06;
     letter-spacing: -.024em; }
h2 { font-size: 1.12rem; line-height: 1.25; letter-spacing: -.012em; }
h3 { font-size: 1rem;    line-height: 1.3;  letter-spacing: -.008em; }
p, li, [data-testid="stMarkdownContainer"] p {
  font-size: .95rem; line-height: 1.58; letter-spacing: 0; color: var(--ink-2);
}
[data-testid="stCaptionContainer"] p {
  font-size: .82rem; line-height: 1.5; letter-spacing: .004em;
  color: var(--ink-3);
}
strong { font-weight: 620; color: var(--ink); }
code { font-size: .86em; background: var(--surface-sunk);
       padding: .08em .34em; border-radius: 5px; color: var(--ink-2); }

/* ------------------------------------------------------------ hero -- */

.hero { padding: .5rem 0 1.25rem; }
.hero .eyebrow {
  font-size: .72rem; font-weight: 600; letter-spacing: .1em;
  text-transform: uppercase; color: var(--ink-4); margin: 0 0 .5rem;
}
.hero .lede {
  font-size: 1.02rem; line-height: 1.5; color: var(--ink-2);
  margin: .55rem 0 0; max-width: 34rem;
}

/* ----------------------------------------------------------- steps -- */

.step-note { margin: .15rem 0 .85rem; font-size: .84rem;
             color: var(--ink-3); line-height: 1.5; max-width: 36rem; }

/* A section header Streamlit renders — numbered steps keep st.header so the
   page still has a real heading outline for a screen reader. */
[data-testid="stHeadingWithActionElements"] { margin-top: 1.6rem; }

/* ----------------------------------------------------------- cards -- */

/* A container given `key="card-…"` carries the class `st-key-card-…`, which
   is the documented hook; the old border-wrapper test id is gone. */
[class*="st-key-card-"] {
  background: var(--surface);
  border: 1px solid var(--line) !important;
  border-radius: var(--r-lg) !important;
  box-shadow: var(--shadow-sm);
  padding: .9rem 1rem !important;
}

/* --------------------------------------------------------- controls -- */

[data-testid="stWidgetLabel"] p {
  font-size: .85rem; font-weight: 560; color: var(--ink-2);
  letter-spacing: .002em;
}
[data-baseweb="select"] > div, [data-baseweb="input"] > div,
[data-testid="stTextArea"] textarea, [data-testid="stNumberInputContainer"] {
  border-radius: var(--r-sm) !important;
  border-color: var(--line-strong) !important;
  background: var(--surface) !important;
  transition: border-color 120ms ease, box-shadow 120ms ease;
}
[data-baseweb="select"] > div:focus-within, [data-baseweb="input"] > div:focus-within,
[data-testid="stTextArea"] textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(31, 56, 100, .14) !important;
}

/* Feedback on the press, not the release (§1). */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius: var(--r-sm);
  border: 1px solid var(--line-strong);
  font-weight: 560; letter-spacing: -.003em;
  transition: transform 100ms ease-out, background 120ms ease,
              border-color 120ms ease, box-shadow 120ms ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: var(--accent); color: var(--accent);
}
.stButton > button:active, .stDownloadButton > button:active {
  transform: scale(.985);
}
.stButton > button[kind="primary"] {
  background: var(--accent); border-color: var(--accent); color: #fff;
  box-shadow: var(--shadow-sm);
}
.stButton > button[kind="primary"]:hover {
  background: var(--accent-press); border-color: var(--accent-press);
  color: #fff;
}
.stDownloadButton > button {
  background: var(--surface); text-align: left;
}

/* --------------------------------------------------------- metrics -- */

[data-testid="stMetric"] {
  background: var(--surface-sunk); border-radius: var(--r-md);
  padding: .6rem .75rem;
}
[data-testid="stMetricLabel"] p {
  font-size: .68rem !important; font-weight: 600; letter-spacing: .07em;
  text-transform: uppercase; color: var(--ink-3);
}
[data-testid="stMetricValue"] {
  font-size: 1.35rem; font-weight: 640; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; color: var(--ink);
}

/* ------------------------------------------------------- disclosure -- */

[data-testid="stExpander"] details {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-md); box-shadow: var(--shadow-sm);
  overflow: hidden;
}
[data-testid="stExpander"] summary {
  padding: .7rem .9rem; font-weight: 580; letter-spacing: -.006em;
  transition: background 120ms ease;
}
[data-testid="stExpander"] summary:hover { background: var(--surface-sunk); }
[data-testid="stExpander"] details[open] summary {
  border-bottom: 1px solid var(--line);
}

/* ------------------------------------------------------- the plan -- */

.pill {
  display: inline-flex; align-items: center; gap: .3rem;
  font-size: .73rem; font-weight: 600; letter-spacing: .01em;
  padding: .2rem .5rem; border-radius: 999px; white-space: nowrap;
}
.pill.ok   { background: var(--ok-wash);   color: var(--ok); }
.pill.warn { background: var(--warn-wash); color: var(--warn); }
.pill.bad  { background: var(--bad-wash);  color: var(--bad); }
.pill.flat { background: var(--surface-sunk); color: var(--ink-3); }

.chips { display: flex; flex-wrap: wrap; gap: .35rem; margin: .1rem 0 .9rem; }

/* The term strip: one bar per term, height by credits, colour by load tag.
   It replaces a generic bar chart because the tags are the point — a light
   term and a free term mean different things and must not look alike. */
.strip { display: flex; align-items: flex-end; gap: .25rem;
         margin: .2rem 0 .9rem; min-height: 5.5rem; }
.strip .t { flex: 1 1 0; display: flex; flex-direction: column;
            align-items: center; gap: .3rem; min-width: 0; }
.strip .bar { width: 100%; max-width: 2.1rem; border-radius: 5px 5px 2px 2px;
              background: var(--accent); }
.strip .t.light .bar    { background: #c9a227; }
.strip .t.heavy .bar    { background: #a12a22; }
.strip .t.free .bar     { background: var(--line-strong); }
.strip .t.exchange .bar { background: #2f7d8f; }
.strip .n  { font-size: .7rem; font-weight: 620; color: var(--ink-2);
             font-variant-numeric: tabular-nums; }
.strip .l  { font-size: .62rem; color: var(--ink-4); letter-spacing: .01em;
             text-align: center; line-height: 1.2; }

.legend { display: flex; flex-wrap: wrap; gap: .75rem; margin: -.4rem 0 .9rem;
          font-size: .7rem; color: var(--ink-4); }
.legend span { display: inline-flex; align-items: center; gap: .3rem; }
.legend i { width: .5rem; height: .5rem; border-radius: 2px; display: block; }

/* ------------------------------------------------------------ chat -- */

[data-testid="stChatMessage"] {
  background: transparent; padding: .15rem 0; gap: .6rem;
}
[data-testid="stChatMessageContent"] {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-md); padding: .6rem .8rem;
  box-shadow: var(--shadow-sm);
}
[data-testid="stChatMessageAvatarUser"] + [data-testid="stChatMessageContent"] {
  background: var(--accent-wash); border-color: #dbe2ee;
}
[data-testid="stChatInput"] {
  border-radius: var(--r-md); border-color: var(--line-strong);
}

/* --------------------------------------------------------- notices -- */

[data-testid="stAlert"] { border-radius: var(--r-md); border: 1px solid var(--line); }
[data-testid="stAlert"] p { font-size: .88rem; line-height: 1.5; }

hr { border-color: var(--line); }

/* ------------------------------------------------------- the phone -- */

@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding: .75rem .9rem 4rem; }
  .strip { min-height: 4.5rem; gap: .18rem; }
  .strip .l { font-size: .56rem; }
  [data-testid="stMetricValue"] { font-size: 1.15rem; }
}

/* --------------------------------------------- what the reader asked -- */

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: .01ms !important; animation-iteration-count: 1 !important; }
  .stButton > button, .stDownloadButton > button { transition: background 120ms ease; }
  .stButton > button:active, .stDownloadButton > button:active { transform: none; }
}
@media (prefers-reduced-transparency: reduce) {
  [data-testid="stHeader"] { background: var(--ground); backdrop-filter: none;
                             -webkit-backdrop-filter: none; }
  [data-testid="stHeader"]::after { display: none; }
}
@media (prefers-contrast: more) {
  :root { --line: #9aa2ae; --line-strong: #6c7684; --ink-3: #4a5260;
          --ink-4: #4a5260; }
  [class*="st-key-card-"],
  [data-testid="stExpander"] details { box-shadow: none; }
}
"""


def inject() -> None:
    """Put the stylesheet on the page. Call once, before anything renders."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
