"""Polite, robots-aware HTTP shared by the Phase 1 fetchers.

Hard rule 7: no scraping of pages whose robots.txt disallows it. Every request
in this project goes through Fetcher.get, which checks robots.txt for the host
first and refuses rather than asks forgiveness.

Hard rule 10: raw source files are kept unchanged in raw/. A file that already
exists on disk is never re-downloaded or rewritten, so a re-run is cheap and
cannot silently alter evidence collected earlier.

Provenance: every saved file appends one JSON line to raw/_manifest.jsonl, and
raw/SOURCES.md is rendered from that ledger.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "raw"
MANIFEST = RAW / "_manifest.jsonl"

# Descriptive and honest, with no personal contact details in an outbound
# header. Set COURSE_PLANNER_UA in the environment to add your own contact.
UA = "HKUST-course-planner/0.1 (student course-planning project; polite crawler)"

DEFAULT_DELAY = 1.5  # seconds between requests to the same host


def _utf8_stdout() -> None:
    """Keep progress output printable on a non-UTF-8 console (e.g. GBK)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


class Blocked(RuntimeError):
    """robots.txt disallows this URL, so we stop instead of fetching it."""


@dataclass
class _Rules:
    parser: urllib.robotparser.RobotFileParser | None
    crawl_delay: float | None
    note: str


class RobotsGate:
    """One robots.txt decision per host, cached for the run.

    Interpretation, following RFC 9309:
      200 + text  -> parse and obey
      404 / 410   -> no robots.txt, everything allowed
      401 / 403   -> treat the whole host as disallowed
      5xx / error -> fail closed; we do not fetch what we could not check
      non-text    -> some hosts redirect robots.txt to a homepage; that is not
                     a robots file, so treat it as absent
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._hosts: dict[str, _Rules] = {}

    def _load(self, origin: str) -> _Rules:
        url = f"{origin}/robots.txt"
        try:
            r = self._client.get(url, follow_redirects=True)
        except httpx.HTTPError as exc:
            return _Rules(None, None, f"unreachable ({type(exc).__name__}) - failing closed")

        if r.status_code in (401, 403):
            return _Rules(None, None, f"HTTP {r.status_code} - host treated as disallowed")
        if r.status_code >= 500:
            return _Rules(None, None, f"HTTP {r.status_code} - failing closed")
        if r.status_code >= 400:
            return _Rules(_allow_all(), None, f"HTTP {r.status_code} - no robots.txt, all allowed")

        ctype = r.headers.get("content-type", "")
        if "text/plain" not in ctype:
            return _Rules(_allow_all(), None,
                          f"robots.txt served as {ctype.split(';')[0] or 'unknown'} - treated as absent")

        p = urllib.robotparser.RobotFileParser()
        p.parse(r.text.splitlines())
        delay = p.crawl_delay(UA) or p.crawl_delay("*")
        return _Rules(p, float(delay) if delay else None, "robots.txt parsed")

    def rules(self, url: str) -> _Rules:
        u = urlparse(url)
        origin = f"{u.scheme}://{u.netloc}"
        if origin not in self._hosts:
            self._hosts[origin] = self._load(origin)
            print(f"  robots {origin}: {self._hosts[origin].note}")
        return self._hosts[origin]

    def allows(self, url: str) -> bool:
        r = self.rules(url)
        if r.parser is None:
            return False
        return r.parser.can_fetch(UA, url)


def _allow_all() -> urllib.robotparser.RobotFileParser:
    p = urllib.robotparser.RobotFileParser()
    p.parse([])  # no rules at all == nothing disallowed
    return p


@dataclass
class Fetcher:
    """A throttled client that records what it saved."""

    delay: float = DEFAULT_DELAY
    timeout: float = 45.0
    saved: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        import os

        ua = os.environ.get("COURSE_PLANNER_UA", UA)
        self._client = httpx.Client(
            headers={"User-Agent": ua, "Accept-Language": "en"},
            timeout=self.timeout,
            follow_redirects=True,
        )
        self._gate = RobotsGate(self._client)
        self._last: dict[str, float] = {}

    # ------------------------------------------------------------ requests --

    def _wait(self, url: str) -> None:
        host = urlparse(url).netloc
        gap = max(self.delay, self._gate.rules(url).crawl_delay or 0)
        since = time.monotonic() - self._last.get(host, 0.0)
        if since < gap:
            time.sleep(gap - since)
        self._last[host] = time.monotonic()

    def get(self, url: str, *, attempts: int = 3) -> httpx.Response:
        """Fetch a URL after clearing it with robots.txt."""
        if not self._gate.allows(url):
            raise Blocked(f"robots.txt disallows {url}")
        last: Exception | None = None
        for i in range(1, attempts + 1):
            self._wait(url)
            try:
                r = self._client.get(url)
                if r.status_code >= 500 and i < attempts:
                    last = httpx.HTTPError(f"HTTP {r.status_code}")
                    time.sleep(self.delay * 2 * i)
                    continue
                r.raise_for_status()
                return r
            except httpx.HTTPError as exc:
                last = exc
                if i < attempts:
                    time.sleep(self.delay * 2 * i)
        raise RuntimeError(f"giving up on {url}: {last}")

    # --------------------------------------------------------------- saving --

    def save(self, url: str, dest: Path, *, area: str, note: str = "",
             expect: str | None = None) -> str:
        """Download url to dest unless dest already exists.

        expect: a substring the content-type must contain, so an HTML error
        page is never written to disk as a .pdf.

        Returns "skipped", "saved" or "failed".
        """
        rel = dest.relative_to(REPO)
        if dest.exists():
            self.skipped.append(dest)
            return "skipped"
        try:
            r = self.get(url)
            ctype = r.headers.get("content-type", "").lower()
            if expect and expect not in ctype:
                raise RuntimeError(f"expected {expect}, got {ctype.split(';')[0]!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
        except (Blocked, RuntimeError, httpx.HTTPError) as exc:
            self.failed.append((url, str(exc)))
            print(f"  FAILED {rel}: {exc}")
            return "failed"

        record(area=area, path=rel.as_posix(), url=str(r.url), data=r.content, note=note)
        self.saved.append(dest)
        print(f"  saved  {rel}  ({len(r.content):,} bytes)")
        return "saved"

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -------------------------------------------------------------- summary --

    def report(self, label: str) -> None:
        print(f"\n{label}: {len(self.saved)} saved, {len(self.skipped)} already present, "
              f"{len(self.failed)} failed")
        for url, why in self.failed:
            print(f"  ! {url}\n      {why}")


# ------------------------------------------------------------- provenance --

def record(*, area: str, path: str, url: str, data: bytes, note: str = "") -> None:
    """Append one provenance line for a saved file."""
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "area": area,
        "path": path,
        "url": url,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "downloaded": date.today().isoformat(),
        "note": note,
    }
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    rows: dict[str, dict] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["path"]] = row  # last write wins
    return sorted(rows.values(), key=lambda r: (r["area"], r["path"]))


AREA_TITLES = {
    "requirements": "Requirement PDFs — `raw/requirements/`",
    "requirements-index": "Program catalog pages — `raw/requirements/_index/`",
    "catalog": "Course catalog — `raw/catalog/`",
    "catalog-index": "Course catalog index — `raw/catalog/_index/`",
    "common_core": "Common Core — `raw/common_core/`",
    "regulations": "Regulations — `raw/regulations/`",
}


def render_sources() -> None:
    """Rebuild raw/SOURCES.md from the provenance ledger."""
    rows = load_manifest()
    by_area: dict[str, list[dict]] = {}
    for r in rows:
        by_area.setdefault(r["area"], []).append(r)

    out: list[str] = [
        "# Sources",
        "",
        "Provenance for everything under `raw/`: where each file came from and when it",
        "was downloaded. Nothing in `raw/` is ever hand-edited — all derived data goes",
        "in `data/`.",
        "",
        f"Generated from `raw/_manifest.jsonl` by `pipeline/fetcher.py` on "
        f"{datetime.now(timezone.utc).date().isoformat()}. "
        f"**{len(rows)} files.**",
        "",
        "Every request was cleared against the host's `robots.txt` first "
        "(see *Robots* below).",
        "",
    ]

    for area in list(AREA_TITLES) + [a for a in by_area if a not in AREA_TITLES]:
        items = by_area.get(area)
        if not items:
            continue
        out += [f"## {AREA_TITLES.get(area, area)}", "",
                f"{len(items)} files.", "",
                "| File | URL | Downloaded | Bytes | SHA-256 (first 12) | Note |",
                "|---|---|---|---|---|---|"]
        for r in items:
            name = r["path"].split("/", 1)[-1]
            out.append(
                f"| `{name}` | <{r['url']}> | {r['downloaded']} | {r['bytes']:,} | "
                f"`{r['sha256'][:12]}` | {r.get('note', '')} |"
            )
        out.append("")

    out += [
        "## Robots",
        "",
        "| Host | Decision |",
        "|---|---|",
        "| `prog-crs.hkust.edu.hk` | no `robots.txt` (404) — fetching allowed |",
        "| `ugadmin.hkust.edu.hk` | `robots.txt` redirects to a homepage, i.e. absent — allowed |",
        "| `uce.ust.hk` | no `robots.txt` (404) — allowed |",
        "| `acadreg.ust.hk` | no blanket disallow — allowed |",
        "| `cle.hkust.edu.hk`, `legal.hkust.edu.hk` | no blanket disallow — allowed |",
        "| `registry.hkust.edu.hk` | Drupal defaults; only `/admin/`, `/user/*`, `/search/` "
        "disallowed — content allowed |",
        "| **`w5.ab.ust.hk`** | **`User-agent: * / Disallow: /` — never fetched.** |",
        "",
        "## TODO / blocked",
        "",
        "- **Term offerings** — the class schedule site (`w5.ab.ust.hk/wcq`) sets",
        "  `Disallow: /`, so it is not fetched (hard rule 7, and CLAUDE.md Phase 1 task 5).",
        "  `data/offerings.json` stays empty and `check_offering` emits a",
        '  "verify on the class schedule" warning rather than a made-up answer.',
        "  Offering data needs a manual export if it is wanted later.",
        "- Any regulation that could not be found on an official page is listed in",
        "  `raw/regulations/GAPS.md` for the developer. A validator with no sourced",
        '  threshold warns "verify" — hard rule 11 forbids inventing one.',
        "",
    ]
    (RAW / "SOURCES.md").write_text("\n".join(out), encoding="utf-8")
    print(f"  wrote raw/SOURCES.md ({len(rows)} files)")
