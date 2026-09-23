"""OpenAI (Codex) limits via `codex app-server` → `account/rateLimits/read`.

This is the same JSON-RPC call the Codex IDE extension and TUI (/status) use.
Codex authenticates with its own stored ChatGPT login; we never touch
~/.codex/auth.json. No turn is started, so no usage is consumed.

Each limit bucket the server reports (keyed by limitId) is kept separate. We
never merge buckets, even if they happen to share a plan.
"""

from __future__ import annotations

from . import locate
from .jsonl import exchange
from .model import AUTH_ERROR, ERROR, NOT_INSTALLED, OK, FetchError, from_epoch, provider, window

ID = "openai"
NAME = "OpenAI"
SOURCE = "codex:account/rateLimits/read"
# Per OpenAI Help Center (checked 2026-09): Codex and ChatGPT Work draw on one
# shared allowance on plans that include both. Only applied to the "codex" bucket.
SHARED_SCOPE = "Codex + ChatGPT Work"
TIMEOUT = 30.0


def fetch_raw() -> dict:
    binary = locate.find("codex")
    if not binary:
        raise FetchError(NOT_INSTALLED, "codex binary not found")

    requests = [
        {"id": 1, "method": "initialize",
         "params": {"clientInfo": {"name": "caelestia_ai_usage", "title": "Caelestia AI usage", "version": "1.0"}}},
        {"method": "initialized"},
        {"id": 2, "method": "account/rateLimits/read"},
    ]

    def pick(msg: dict):
        if msg.get("id") == 1 and "error" in msg:
            raise FetchError(ERROR, f"initialize failed: {msg['error'].get('message')}", retryable=True)
        if msg.get("id") != 2:
            return None
        if "error" in msg:
            text = str(msg["error"].get("message", ""))
            if "authentication" in text.lower() or "login" in text.lower():
                raise FetchError(AUTH_ERROR, text)
            raise FetchError(ERROR, text or "rateLimits/read failed", retryable=True)
        return msg.get("result") or {}

    return exchange([binary, "app-server"], requests, pick, TIMEOUT)


def _label(minutes: int | None) -> tuple[str, str]:
    if not minutes:
        return "short", "Limit"
    kind = "short" if minutes <= 24 * 60 else "weekly"
    if minutes == 10080:
        return kind, "Weekly"
    if minutes % 1440 == 0:
        return kind, f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return kind, f"{minutes // 60}h"
    return kind, f"{minutes}m"


def normalize(raw: dict) -> dict:
    buckets = raw.get("rateLimitsByLimitId") or {}
    if not buckets and raw.get("rateLimits"):
        single = raw["rateLimits"]
        buckets = {single.get("limitId") or "codex": single}
    if not buckets:
        raise FetchError(ERROR, "response contained no rate limit buckets")

    windows = []
    plan = None
    for limit_id, snap in buckets.items():
        if not isinstance(snap, dict):
            continue
        plan = plan or snap.get("planType")
        scope = None if limit_id == "codex" else (snap.get("limitName") or limit_id)
        for slot in ("primary", "secondary"):
            w = snap.get(slot)
            if not isinstance(w, dict) or w.get("usedPercent") is None:
                continue
            minutes = w.get("windowDurationMins")
            kind, label = _label(minutes)
            windows.append(window(f"{limit_id}:{slot}", kind, label, w["usedPercent"],
                                  from_epoch(w.get("resetsAt")), minutes, scope))

    if not windows:
        raise FetchError(ERROR, "response contained no limit windows")

    return provider(ID, NAME, status=OK, source=SOURCE, windows=windows, plan=plan,
                    shared_scope=SHARED_SCOPE if "codex" in buckets else None)
