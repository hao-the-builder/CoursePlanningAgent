"""Streamlit UI for the HKUST course planning agent (Phase 6).

Flow: form (every field in CLAUDE.md section 1.1, transfer credits as an
editable table, the exchange section only when exchange is Yes, a free-term
picker built from term_sequence) -> chat (direction, career interests,
background, follow-ups) -> generate (per-path summary, a credits-per-term mini
chart, validation status) -> download (one .xlsx per path plus one .docx).

The data tier badge and "verify with your advisor" stay prominent. Session
limits cap generations and chat turns. Works at phone width.

Run: streamlit run app.py
"""


def main() -> None:
    raise NotImplementedError("Phase 6")


if __name__ == "__main__":
    main()
