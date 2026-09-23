"""Command line entry point: fetch, normalize, cache, print."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import claude, codex
from .model import ERROR, NOT_FETCHED, NOT_INSTALLED, OK, FetchError, document, now_utc, parse_iso, provider

PROVIDERS = {claude.ID: claude, codex.ID: codex}
DEFAULT_CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ai-usage" / "usage.json"
MOCK_ROOT = Path(__file__).resolve().parent.parent / "mock"
RETRY_DELAY = 2.0


def fetch_one(mod, mock_dir: Path | None) -> dict:
    """Fetch and normalize one provider; failures become a status entry."""
    for attempt in range(2):
        try:
            raw = load_mock(mock_dir, mod.ID) if mock_dir else mod.fetch_raw()
            return mod.normalize(raw)
        except FetchError as e:
            if e.retryable and attempt == 0 and not mock_dir:
                time.sleep(RETRY_DELAY)
                continue
            return provider(mod.ID, mod.NAME, status=e.status, source=mod.SOURCE, error=e.message)
        except Exception as e:  # a bug or an unexpected response shape
            return provider(mod.ID, mod.NAME, status=ERROR, source=mod.SOURCE,
                            error=f"unexpected {type(e).__name__}: {e}")
    raise AssertionError("unreachable")


def load_mock(mock_dir: Path, pid: str) -> dict:
    """Mock files hold the raw CLI response, or {"__error__": {...}} to simulate a failure."""
    path = mock_dir / f"{pid}.json"
    if not path.exists():
        raise FetchError(NOT_INSTALLED, f"no mock file {path.name}")
    data = json.loads(path.read_text())
    if "__error__" in data:
        err = data["__error__"]
        raise FetchError(err["status"], err["message"], err.get("retryable", False))
    return data


def merge_stale(fresh: dict, previous: dict | None) -> dict:
    """On failure, carry over the last good windows, flagged stale.

    Windows whose reset time has passed are dropped: after a reset the old
    percentage says nothing about the current window.
    """
    if fresh["status"] == OK or not previous or not previous.get("windows"):
        return fresh
    now = now_utc()
    kept = [w for w in previous["windows"] if not (parse_iso(w["resets_at"]) and parse_iso(w["resets_at"]) <= now)]
    if not kept:
        return fresh
    return {**fresh, "windows": kept, "stale": True, "plan": previous.get("plan"),
            "shared_scope": previous.get("shared_scope"), "fetched_at": previous.get("fetched_at")}


def read_cache(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def write_cache(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    os.replace(tmp, path)


def cache_is_fresh(doc: dict | None, ids: list[str], max_age: float) -> bool:
    if not doc:
        return False
    by_id = {p["id"]: p for p in doc.get("providers", [])}
    now = now_utc()
    for pid in ids:
        attempted = parse_iso((by_id.get(pid) or {}).get("attempted_at"))
        if not attempted or (now - attempted).total_seconds() > max_age:
            return False
    return True


def run(ids: list[str], cache_path: Path | None, mock_dir: Path | None, max_age: float | None) -> dict:
    lock = None
    if cache_path:
        # Serialize concurrent runs (e.g. timer + manual refresh) so the CLIs aren't spawned twice.
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        lock = open(cache_path.with_suffix(".lock"), "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        previous = read_cache(cache_path) if cache_path else None
        if max_age is not None and cache_is_fresh(previous, ids, max_age):
            return {**previous, "mode": "cache"}

        with ThreadPoolExecutor(len(ids)) as pool:
            fresh = list(pool.map(lambda pid: fetch_one(PROVIDERS[pid], mock_dir), ids))

        prev_by_id = {p["id"]: p for p in (previous or {}).get("providers", [])}
        results = [merge_stale(p, prev_by_id.get(p["id"])) for p in fresh]
        doc = document(results, "mock" if mock_dir else "live")
        if cache_path:
            write_cache(cache_path, doc)
        return doc
    finally:
        if lock:
            lock.close()


def fmt_local(value: str | None) -> str:
    dt = parse_iso(value)
    if not dt:
        return "-"
    local = dt.astimezone()
    return local.strftime("%H:%M" if local.date() == datetime.now().astimezone().date() else "%m/%d %H:%M")


def fmt_remaining(value: str | None) -> str:
    dt = parse_iso(value)
    if not dt:
        return ""
    secs = int((dt - now_utc()).total_seconds())
    if secs <= 0:
        return "(reset)"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"(in {d}d {h}h)" if d else f"(in {h}h {m}m)" if h else f"(in {m}m)"


def print_human(doc: dict) -> None:
    for p in doc["providers"]:
        plan = f" ({p['plan']})" if p.get("plan") else ""
        stale = " [stale]" if p.get("stale") else ""
        print(f"{p['name']}{plan}  {p['status']}{stale}  fetched {fmt_local(p.get('fetched_at'))}")
        if p.get("shared_scope"):
            print(f"  shared by: {p['shared_scope']}")
        if p.get("error"):
            print(f"  error: {p['error']['message']}")
        for w in p["windows"]:
            name = w["label"] + (f" · {w['scope']}" if w.get("scope") else "")
            print(f"  {name:<16} {w['used_percent']:>5.1f}%  resets {fmt_local(w['resets_at'])} {fmt_remaining(w['resets_at'])}")
        print()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ai-usage", description="Claude / OpenAI subscription usage")
    ap.add_argument("--json", action="store_true", help="print normalized JSON")
    ap.add_argument("--provider", action="append", choices=list(PROVIDERS), help="limit to a provider (repeatable)")
    ap.add_argument("--cached", action="store_true", help="print the cache without fetching")
    ap.add_argument("--max-age", type=float, metavar="SEC", help="reuse the cache if it is newer than SEC")
    ap.add_argument("--mock", metavar="SCENARIO", help=f"read raw responses from mock/SCENARIO (or a directory path)")
    ap.add_argument("--cache-file", type=Path, help=f"cache path (default {DEFAULT_CACHE}; disabled with --mock unless given)")
    args = ap.parse_args(argv)

    ids = args.provider or list(PROVIDERS)
    mock_dir = None
    if args.mock:
        mock_dir = Path(args.mock) if os.sep in args.mock else MOCK_ROOT / args.mock
        if not mock_dir.is_dir():
            ap.error(f"mock scenario not found: {mock_dir}")
    cache_path = args.cache_file or (None if mock_dir else DEFAULT_CACHE)

    if args.cached:
        doc = read_cache(cache_path) if cache_path else None
        if not doc:
            doc = document([provider(pid, PROVIDERS[pid].NAME, status=NOT_FETCHED, source=PROVIDERS[pid].SOURCE,
                                     error="no cached data yet") for pid in ids], "cache")
        else:
            doc = {**doc, "mode": "cache"}
    else:
        doc = run(ids, cache_path, mock_dir, args.max_age)

    if args.json:
        json.dump(doc, sys.stdout, indent=1)
        sys.stdout.write("\n")
    else:
        print_human(doc)
    return 0
