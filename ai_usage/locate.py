"""Find the Claude Code / Codex binaries.

Order: explicit env var, then $PATH, then the copies Zed installs for its
external agents (this machine has no global install, only Zed's).
"""

from __future__ import annotations

import glob
import os
import shutil

ZED_AGENTS = os.path.expanduser("~/.local/share/zed/external_agents")

_CANDIDATES = {
    "claude": (
        "AI_USAGE_CLAUDE_BIN",
        f"{ZED_AGENTS}/registry/npx/claude-acp/node_modules/@anthropic-ai/claude-agent-sdk-linux-*/claude",
    ),
    "codex": (
        "AI_USAGE_CODEX_BIN",
        f"{ZED_AGENTS}/registry/npx/codex-acp/node_modules/@openai/codex-linux-*/vendor/*/bin/codex",
    ),
}


def find(name: str) -> str | None:
    env_var, zed_glob = _CANDIDATES[name]
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit if os.access(explicit, os.X_OK) else None
    on_path = shutil.which(name)
    if on_path:
        return on_path
    for path in sorted(glob.glob(zed_glob)):
        if os.access(path, os.X_OK):
            return path
    return None
