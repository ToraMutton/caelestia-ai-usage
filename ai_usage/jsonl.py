"""Talk to a CLI over newline-delimited JSON on stdio.

Both Claude Code (stream-json) and Codex (app-server) speak JSONL, so one
small helper covers both. stderr is discarded on purpose: we never want CLI
diagnostics (which could include account details) to end up in our logs.
"""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from typing import Callable

from .model import ERROR, TIMEOUT, FetchError


def exchange(
    cmd: list[str],
    requests: list[dict],
    pick: Callable[[dict], object | None],
    timeout: float,
    env: dict[str, str] | None = None,
) -> object:
    """Send `requests`, then return the first non-None `pick(message)`."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=os.path.expanduser("~"),
            env={**os.environ, **(env or {})},
        )
    except OSError as e:
        raise FetchError(ERROR, f"failed to start {os.path.basename(cmd[0])}: {e.strerror}")

    assert proc.stdin and proc.stdout
    try:
        proc.stdin.write("".join(json.dumps(r) + "\n" for r in requests).encode())
        proc.stdin.flush()

        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        buf = b""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FetchError(TIMEOUT, f"no response within {timeout:.0f}s", retryable=True)
            if not sel.select(remaining):
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                raise FetchError(ERROR, f"process exited early (code {proc.poll()})", retryable=True)
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for line in lines:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                result = pick(msg)
                if result is not None:
                    return result
    finally:
        # Closing stdin makes both CLIs exit cleanly; kill as a fallback.
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
