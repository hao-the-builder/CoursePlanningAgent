"""No test may call a real model.

`planner/llm.py` reads `LLM_BACKEND` from the environment and `app.py` also
loads `.env`, which on a developer machine says `subscription` — the
developer's own Claude plan. The per-test `monkeypatch` fixtures that set the
stub backend are function-scoped, and pytest builds higher-scoped fixtures
first, so a module-scoped fixture is created *before* them: a full run of
tests/test_app.py quietly planned a degree against the real model and timed
out after five minutes.

Setting the variable here, at collection time, closes that for every test in
every module. A test that wants a different backend still sets it with
monkeypatch, which is restored afterwards.
"""
from __future__ import annotations

import os

os.environ["LLM_BACKEND"] = "stub"
