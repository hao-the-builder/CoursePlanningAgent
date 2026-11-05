"""JSONL action log (Phase 4).

Every run writes one file, `logs/runs/{timestamp}.jsonl`, one JSON object per
line. It is the evidence behind the test log in Phase 7: what went in, which
tools were called, what the validator said, how many times the agent had to
try again, and how it ended.

Lines are written and flushed as they happen, so a run that crashes still
leaves everything up to the crash on disk.

Nothing secret goes in: the log records which backend and model were used,
never a key. A student profile is the person's own input and is recorded in
full so a run can be replayed.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "logs" / "runs"

# Anything whose name looks like this is replaced before it reaches the file.
SECRET = ("key", "token", "secret", "password", "credential")


def _scrub(value: Any) -> Any:
    """Drop anything that looks like a credential, however deeply nested."""
    if isinstance(value, dict):
        return {k: ("<redacted>" if any(s in k.lower() for s in SECRET)
                    else _scrub(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


@dataclass
class RunLog:
    """One run of the agent."""

    path: Path
    started: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    lines: int = 0

    @classmethod
    def open(cls, name: str | None = None, directory: Path | None = None) -> RunLog:
        started = datetime.now(timezone.utc)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        target = (directory or RUNS)
        target.mkdir(parents=True, exist_ok=True)
        log = cls(path=target / f"{name or stamp}.jsonl", started=started)
        log.path.write_text("", encoding="utf-8")
        log.event("run_started", stamp=stamp, python=sys.version.split()[0],
                  backend=os.environ.get("LLM_BACKEND", "stub"))
        return log

    def event(self, kind: str, **fields: Any) -> None:
        """Append one event. Called for every step worth replaying."""
        record = {
            "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "elapsed_s": round(
                (datetime.now(timezone.utc) - self.started).total_seconds(), 3),
            "event": kind,
            **_scrub(fields),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self.lines += 1

    def read(self) -> list[dict]:
        """The run back as a list of events, for tests and the eval report."""
        return [json.loads(line) for line in
                self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def events_of(self, kind: str) -> list[dict]:
        return [e for e in self.read() if e["event"] == kind]
