"""Assemble a Hugging Face Space that serves the tool service.

Dify has to reach the tool service from the internet, and a Space is free,
needs no card and runs the `Dockerfile` this repo already has. But a Space has
to be *public* for Dify to call it without credentials, and pushing this whole
repo would publish the lot: the source PDFs, the tests, the coursework
documents. So this copies out only what the service reads.

    python scripts/make_space.py

Then follow `dify/DEPLOY.md` to push `deploy/space/` to the Space.

Nothing here is a secret. `TOOL_API_TOKEN` is set in the Space's own secret
store, never written to a file, and the service refuses to start without it.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "deploy" / "space"

# What the service imports, and what it reads. Verified by importing
# `service.tool_api` and reading `sys.modules`: no Streamlit, no model SDK,
# no PDF tooling, because the service answers from `data/` and calls no model.
TREES = ["planner", "service", "data"]
FILES = ["schema.py", "Dockerfile"]

# A Space is configured by the YAML block at the top of its README, and
# `app_port` has to match the port the container listens on. Everything else
# here is the description a visitor sees.
README = """---
title: HKUST Course Planner Tools
emoji: "\N{GRADUATION CAP}"
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8601
pinned: false
---

# Course planner tools

A read-only HTTP service over HKUST's published undergraduate requirements,
for the 2026-27 cohort. It answers four questions - search courses, read a
program's requirement rules, draft a plan, validate a plan - and is called by
a Dify workflow that does the planning.

It holds no personal data, writes nothing, and calls no language model.

`GET /health` is open, and reports how many programs and courses are loaded.
Everything under `/tools/` needs a bearer token, so this service answers
lookups for the workflow that owns the token and nobody else.

Source: a private repository; this Space carries only the service and the
data it reads.
"""


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    for tree in TREES:
        shutil.copytree(REPO / tree, OUT / tree,
                        ignore=shutil.ignore_patterns(
                            "__pycache__", "*.pyc", "*.issues.md"))
    for name in FILES:
        shutil.copy2(REPO / name, OUT / name)

    (OUT / "README.md").write_text(README, encoding="utf-8")

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    count = sum(1 for f in OUT.rglob("*") if f.is_file())
    print(f"wrote {OUT.relative_to(REPO)} - {count} files, "
          f"{total / 1_048_576:.1f} MB")
    print()
    print("Left out on purpose: raw/ (the source PDFs), tests/, outputs/,")
    print("app.py, pipeline/, and every document in the repo root.")
    print()
    print("Next: dify/DEPLOY.md, 'Phase 1 - Hugging Face Spaces'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
