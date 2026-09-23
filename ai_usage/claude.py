"""Claude subscription limits via Claude Code's `get_usage` control request.

How it works: we start `claude -p` in stream-json mode and send two control
requests (`initialize`, `get_usage`) but never a user prompt, so no model call
is made and no usage is consumed. Claude Code fetches the numbers with its own
login; this script never reads or sends the OAuth token.

Caveat: `get_usage` is the data behind the /usage command and is exposed in the
Agent SDK (`usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET`). It is
marked experimental, so a Claude Code update may rename or reshape it. All
knowledge of that shape lives in this module.
"""

from __future__ import annotations

from . import locate
from .jsonl import exchange
from .model import AUTH_ERROR, ERROR, NOT_INSTALLED, OK, UNSUPPORTED, FetchError, parse_iso, provider, window

ID = "claude"
NAME = "Claude"
SOURCE = "claude-code:get_usage"
# Per Claude Help Center: Pro/Max limits are shared by claude.ai (web, desktop,
# mobile) and Claude Code.
SHARED_SCOPE = "Claude apps + Claude Code"
TIMEOUT = 40.0

# Documented windows only. Unknown keys in the response are ignored rather than
# guessed at.
_WINDOWS = [
    ("five_hour", "short", "5h", 300, None),
    ("seven_day", "weekly", "Weekly", 10080, None),
    ("seven_day_opus", "weekly", "Weekly", 10080, "Opus"),
    ("seven_day_sonnet", "weekly", "Weekly", 10080, "Sonnet"),
]


def fetch_raw() -> dict:
    binary = locate.find("claude")
    if not binary:
        raise FetchError(NOT_INSTALLED, "claude binary not found")

    cmd = [
        binary,
        "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        # Don't run user hooks, MCP servers or write a session transcript.
        "--setting-sources", "",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]
    requests = [
        {"type": "control_request", "request_id": "init", "request": {"subtype": "initialize"}},
        {"type": "control_request", "request_id": "usage",
         "request": {"subtype": "get_usage", "skip_behaviors": True}},
    ]

    def pick(msg: dict):
        if msg.get("type") != "control_response":
            return None
        resp = msg.get("response") or {}
        if resp.get("request_id") != "usage":
            return None
        if resp.get("subtype") != "success":
            raise FetchError(ERROR, f"get_usage failed: {resp.get('error') or 'unknown error'}", retryable=True)
        return resp.get("response") or {}

    return exchange(cmd, requests, pick, TIMEOUT, env={"ENABLE_CLAUDEAI_MCP_SERVERS": "false"})


def normalize(raw: dict) -> dict:
    plan = raw.get("subscription_type")
    limits = raw.get("rate_limits")

    if not raw.get("rate_limits_available"):
        if plan is None:
            # Same answer Claude Code gives when there is no login at all.
            raise FetchError(AUTH_ERROR, "Claude Code is not logged in to a claude.ai account")
        raise FetchError(UNSUPPORTED, f"plan limits are not available for this login ({plan})")
    if not isinstance(limits, dict):
        raise FetchError(ERROR, "usage endpoint returned no rate limits", retryable=True)

    windows = []
    for key, kind, label, minutes, scope in _WINDOWS:
        w = limits.get(key)
        if isinstance(w, dict) and w.get("utilization") is not None:
            windows.append(window(key, kind, label, w["utilization"], parse_iso(w.get("resets_at")), minutes, scope))

    for m in limits.get("model_scoped") or []:
        if m.get("utilization") is not None and m.get("display_name"):
            windows.append(window(f"model:{m['display_name']}", "weekly", "Weekly", m["utilization"],
                                  parse_iso(m.get("resets_at")), 10080, m["display_name"]))

    if not windows:
        raise FetchError(ERROR, "response contained no known limit windows")

    return provider(ID, NAME, status=OK, source=SOURCE, windows=windows, plan=plan, shared_scope=SHARED_SCOPE)
