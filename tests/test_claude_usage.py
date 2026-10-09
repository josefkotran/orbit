"""The limits from Claude's OAuth usage endpoint (claude_usage.fetch_oauth) over a restart of Orbit: an answer under
2 minutes old is shown again without asking, Claude's "too often" (429) holds after a restart too, and meanwhile the
last answer is there to show instead of nothing. No request leaves (requests.get replaced), Orbit's and Claude Code's
folders are temporary ones.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_claude*.py"
"""
import atexit
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import claude_usage, paths  # noqa: E402

ANSWER = {"limits": [{"kind": "session", "percent": 6, "resets_at": "2026-10-09T21:00:00+00:00"},
                     {"kind": "weekly_all", "percent": 38}]}


def reply(status=200, body=None, headers=None):
    return SimpleNamespace(status_code=status, headers=headers or {}, json=lambda: body or ANSWER)


class OAuthOverRestarts(unittest.TestCase):
    def setUp(self):
        folder = paths.claude_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat-test"}}),
                                                  encoding="utf-8")
        claude_usage.OAUTH_CACHE.unlink(missing_ok=True)
        self.addCleanup(lambda: claude_usage.OAUTH_CACHE.unlink(missing_ok=True))
        self.restart()

    @staticmethod
    def restart():
        claude_usage._retry_at = 0.0  # what a new Orbit process starts with

    def age(self, seconds):
        """The kept answer as if it came `seconds` ago."""
        data = json.loads(claude_usage.OAUTH_CACHE.read_text(encoding="utf-8"))
        data["at"] = time.time() - seconds
        claude_usage.OAUTH_CACHE.write_text(json.dumps(data), encoding="utf-8")

    def test_a_restart_right_after_asking_doesnt_ask_again(self):
        with mock.patch.object(claude_usage.requests, "get", return_value=reply()) as get:
            first = claude_usage.fetch_oauth()
            self.assertEqual(get.call_count, 1)
            self.assertNotIn("sk-ant", claude_usage.OAUTH_CACHE.read_text(encoding="utf-8"))  # never the token
            self.restart()
            again = claude_usage.fetch_oauth()
            self.assertEqual(get.call_count, 1)
            self.assertEqual([lim.percent for lim in again.limits], [lim.percent for lim in first.limits])
            self.assertLessEqual(abs((again.fetched_at - first.fetched_at).total_seconds()), 1)  # from then
            self.age(claude_usage.OAUTH_FRESH_S + 5)  # Orbit's next ask, 2 minutes on
            claude_usage.fetch_oauth()
            self.assertEqual(get.call_count, 2)

    def test_too_often_holds_over_a_restart_with_the_last_answer(self):
        with mock.patch.object(claude_usage.requests, "get", return_value=reply()):
            claude_usage.fetch_oauth()
        self.age(200)
        with mock.patch.object(claude_usage.requests, "get", return_value=reply(429)) as get:
            with self.assertRaises(claude_usage.Limited) as caught:
                claude_usage.fetch_oauth()
            self.assertEqual(caught.exception.last.get("weekly_all").percent, 38)
            self.restart()
            with self.assertRaises(claude_usage.Limited) as caught:
                claude_usage.fetch_oauth()
            self.assertEqual(get.call_count, 1)  # the new Orbit waits too
            self.assertIsNotNone(caught.exception.last)
        self.age(claude_usage.OAUTH_SHOW_S + 60)  # too old to show
        self.restart()
        with self.assertRaises(claude_usage.Limited) as caught:
            claude_usage.fetch_oauth()
        self.assertIsNone(caught.exception.last)

    def test_the_wait_is_capped_and_a_broken_file_ignored(self):
        claude_usage.OAUTH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        claude_usage.OAUTH_CACHE.write_text(json.dumps({"retry_at": time.time() + 30 * 86400}), encoding="utf-8")
        with self.assertRaises(claude_usage.Limited):
            claude_usage.fetch_oauth()
        self.assertLessEqual(claude_usage._retry_at, time.time() + 3601)
        self.restart()
        claude_usage.OAUTH_CACHE.write_text("{rozbité", encoding="utf-8")
        with mock.patch.object(claude_usage.requests, "get", return_value=reply()) as get:
            self.assertEqual(claude_usage.fetch_oauth().get("session").percent, 6)
        self.assertEqual(get.call_count, 1)

    def test_an_answer_it_doesnt_understand_isnt_kept(self):
        with mock.patch.object(claude_usage.requests, "get", return_value=reply(body=["ne"])):
            with self.assertRaises(claude_usage.UsageError):
                claude_usage.fetch_oauth()
        self.assertFalse(claude_usage.OAUTH_CACHE.exists())


if __name__ == "__main__":
    unittest.main()
