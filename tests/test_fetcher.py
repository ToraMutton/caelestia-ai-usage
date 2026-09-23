"""Run with: python3 -m unittest discover -s tests"""

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai_usage import claude, cli, codex  # noqa: E402
from ai_usage.model import AUTH_ERROR, OK, UNSUPPORTED, FetchError  # noqa: E402

MOCK = ROOT / "mock"


def load(scenario, pid):
    return json.loads((MOCK / scenario / f"{pid}.json").read_text())


def run_cli(*args):
    out = StringIO()
    with redirect_stdout(out):
        cli.main(["--json", *args])
    return json.loads(out.getvalue())


class ClaudeNormalize(unittest.TestCase):
    def test_windows(self):
        p = claude.normalize(load("normal", "claude"))
        self.assertEqual(p["status"], OK)
        self.assertEqual(p["plan"], "pro")
        self.assertEqual([(w["id"], w["kind"], w["used_percent"]) for w in p["windows"]],
                         [("five_hour", "short", 42.0), ("seven_day", "weekly", 17.0)])
        self.assertEqual(p["windows"][0]["resets_at"], "2099-01-01T05:00:00+00:00")

    def test_unknown_keys_ignored(self):
        ids = [w["id"] for w in claude.normalize(load("normal", "claude"))["windows"]]
        self.assertNotIn("nimbus_quill", ids)

    def test_model_windows_kept_separate(self):
        raw = load("normal", "claude")
        raw["rate_limits"]["seven_day_opus"] = {"utilization": 5, "resets_at": None}
        raw["rate_limits"]["model_scoped"] = [{"display_name": "Fable", "utilization": 12, "resets_at": None}]
        scopes = [w["scope"] for w in claude.normalize(raw)["windows"]]
        self.assertEqual(scopes, [None, None, "Opus", "Fable"])

    def test_not_logged_in(self):
        with self.assertRaises(FetchError) as cm:
            claude.normalize(load("auth_error", "claude"))
        self.assertEqual(cm.exception.status, AUTH_ERROR)

    def test_plan_without_limits(self):
        with self.assertRaises(FetchError) as cm:
            claude.normalize(load("unsupported", "claude"))
        self.assertEqual(cm.exception.status, UNSUPPORTED)


class CodexNormalize(unittest.TestCase):
    def test_windows(self):
        p = codex.normalize(load("normal", "openai"))
        self.assertEqual(p["plan"], "plus")
        self.assertEqual([(w["label"], w["kind"], w["used_percent"]) for w in p["windows"]],
                         [("5h", "short", 88.0), ("Weekly", "weekly", 49.0)])
        self.assertEqual(p["shared_scope"], codex.SHARED_SCOPE)

    def test_buckets_not_merged(self):
        raw = load("normal", "openai")
        raw["rateLimitsByLimitId"]["other"] = {
            "limitId": "other", "limitName": "Other model",
            "primary": {"usedPercent": 3, "windowDurationMins": 300, "resetsAt": None},
        }
        windows = codex.normalize(raw)["windows"]
        self.assertEqual(len(windows), 3)
        self.assertEqual(windows[2]["scope"], "Other model")

    def test_labels(self):
        self.assertEqual(codex._label(300), ("short", "5h"))
        self.assertEqual(codex._label(10080), ("weekly", "Weekly"))
        self.assertEqual(codex._label(1440), ("short", "1d"))
        self.assertEqual(codex._label(43200), ("weekly", "30d"))


class Cli(unittest.TestCase):
    def test_statuses_are_distinct(self):
        doc = run_cli("--mock", "unsupported")
        self.assertEqual({p["id"]: p["status"] for p in doc["providers"]},
                         {"claude": "unsupported", "openai": "not_installed"})

    def test_stale_carry_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "usage.json"
            good = run_cli("--mock", "normal", "--cache-file", str(cache))
            bad = run_cli("--mock", "partial_failure", "--cache-file", str(cache))
            openai = next(p for p in bad["providers"] if p["id"] == "openai")
            self.assertEqual(openai["status"], "timeout")
            self.assertTrue(openai["stale"])
            self.assertEqual(openai["windows"], good["providers"][1]["windows"])
            self.assertEqual(openai["fetched_at"], good["providers"][1]["fetched_at"])
            # The provider that succeeded is fresh.
            self.assertFalse(bad["providers"][0]["stale"])

    def test_expired_windows_not_carried_over(self):
        fresh = {"status": "timeout", "windows": [], "stale": False}
        prev = {"status": "ok", "fetched_at": "x", "windows": [
            {"id": "a", "resets_at": "2000-01-01T00:00:00+00:00"},
            {"id": "b", "resets_at": "2099-01-01T00:00:00+00:00"},
        ]}
        merged = cli.merge_stale(fresh, prev)
        self.assertEqual([w["id"] for w in merged["windows"]], ["b"])

    def test_max_age_uses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "usage.json"
            run_cli("--mock", "normal", "--cache-file", str(cache))
            doc = run_cli("--mock", "auth_error", "--cache-file", str(cache), "--max-age", "300")
            self.assertEqual(doc["mode"], "cache")
            self.assertEqual(doc["providers"][0]["status"], "ok")

    def test_cached_without_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = run_cli("--cached", "--cache-file", str(Path(tmp) / "none.json"))
            self.assertTrue(all(p["status"] == "not_fetched" for p in doc["providers"]))


if __name__ == "__main__":
    unittest.main()
