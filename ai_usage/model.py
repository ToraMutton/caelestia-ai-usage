"""Normalized data model shared by all providers.

Everything the widget sees goes through these helpers so that every provider
emits the same shape. Timestamps are always ISO 8601 in UTC; the UI converts
them to local time.
"""

from __future__ import annotations

from datetime import datetime, timezone

SCHEMA_VERSION = 1

# Provider status codes. The UI keys its error display on these.
OK = "ok"
AUTH_ERROR = "auth_error"  # CLI installed but not logged in
UNSUPPORTED = "unsupported"  # logged in, but plan limits don't apply (API key etc.)
NOT_INSTALLED = "not_installed"  # CLI binary not found
TIMEOUT = "timeout"
ERROR = "error"  # anything else: protocol, parse, network
NOT_FETCHED = "not_fetched"  # nothing attempted yet (empty cache)


class FetchError(Exception):
    """Raised by provider modules; carries a status code for the output."""

    def __init__(self, status: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.message = message
        self.retryable = retryable


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def from_epoch(value: int | float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc)


def window(
    wid: str,
    kind: str,
    label: str,
    used_percent: float,
    resets_at: datetime | None,
    window_minutes: int | None = None,
    scope: str | None = None,
) -> dict:
    """One rate-limit window. kind is "short" (<= 1 day) or "weekly"."""
    return {
        "id": wid,
        "kind": kind,
        "label": label,
        "scope": scope,
        "used_percent": round(float(used_percent), 1),
        "resets_at": iso(resets_at),
        "window_minutes": window_minutes,
    }


def provider(
    pid: str,
    name: str,
    *,
    status: str,
    source: str,
    windows: list[dict] | None = None,
    plan: str | None = None,
    shared_scope: str | None = None,
    error: str | None = None,
    fetched_at: datetime | None = None,
) -> dict:
    now = now_utc()
    return {
        "id": pid,
        "name": name,
        "status": status,
        "error": {"code": status, "message": error} if error else None,
        "plan": plan,
        "source": source,
        "shared_scope": shared_scope,
        # When this data was obtained. Differs from attempted_at for stale data.
        "fetched_at": iso(fetched_at or now) if status == OK else None,
        "attempted_at": iso(now),
        "stale": False,
        "windows": windows or [],
    }


def document(providers: list[dict], mode: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso(now_utc()),
        "mode": mode,
        "providers": providers,
    }
