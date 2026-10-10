"""The limits from Claude's OAuth usage endpoint (claude_usage.fetch_oauth) over a restart of Orbit: an answer under
2 minutes old is shown again without asking, Claude's "too often" (429) holds after a restart too, and meanwhile the
last answer is there to show instead of nothing. And on top of the sessions' own figures (claude_usage.combined): the
endpoint asked every 10 minutes only, its 429 leaving the bars as they are. No request leaves (requests.get replaced),
Orbit's and Claude Code's folders are temporary ones.

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
from datetime import datetime, timezone
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


class _Endpoint(unittest.TestCase):
    """A token in a temporary Claude Code folder, no kept answer, a fresh Orbit process."""

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


class OAuthOverRestarts(_Endpoint):
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


def iso(seconds_from_now: float) -> str:
    return datetime.fromtimestamp(time.time() + seconds_from_now, timezone.utc).isoformat()


FABLE = {"limits": [{"kind": "session", "percent": 30, "resets_at": iso(3600)},
                    {"kind": "weekly_all", "percent": 40, "resets_at": iso(86400)},
                    {"kind": "weekly_scoped", "percent": 55, "resets_at": iso(86400),
                     "scope": {"model": {"display_name": "Fable"}}}]}


class SessionsFiguresFirst(_Endpoint):
    """claude_usage.combined (usage_source "oauth"): the 5-hour and the weekly limit as the sessions report them
    (status line or orbit-mozek mod files), the endpoint asked only every 10 minutes on top, for Fable; its 429 no
    longer empties the panel. Without the sessions' figures the endpoint alone, as before."""

    def setUp(self):
        super().setUp()
        self.status = claude_usage.STATUS_DIR
        shutil.rmtree(self.status, ignore_errors=True)
        self.status.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.status, True)
        claude_usage._failed = None
        self.addCleanup(setattr, claude_usage, "_failed", None)

    def report(self, session="s1", five=20.0, week=35.0, age=0.0, resets=3600, suffix=".mod.json"):
        """What the orbit-mozek mod (or, with suffix .json, Orbit's status line) leaves after an answer."""
        record = {"session_id": session, "time": time.time() - age, "source": "orbit-mozek", "rate_limits": {
            "five_hour": {"used_percentage": five, "resets_at": iso(resets)},
            "seven_day": {"used_percentage": week, "resets_at": iso(5 * 86400)}}}
        (self.status / f"{session}{suffix}").write_text(json.dumps(record), encoding="utf-8")

    def asked_ago(self, seconds):
        data = json.loads(claude_usage.OAUTH_CACHE.read_text(encoding="utf-8"))
        data["asked_at"] = time.time() - seconds
        claude_usage.OAUTH_CACHE.write_text(json.dumps(data), encoding="utf-8")

    def rows(self, usage):
        return [(lim.label, lim.percent) for lim in usage.limits]

    def test_the_sessions_figures_with_fable_on_top_asked_rarely(self):
        self.report(five=20, week=35)
        with mock.patch.object(claude_usage.requests, "get", return_value=reply(body=FABLE)) as get:
            usage = claude_usage.combined()
            self.assertEqual(get.call_count, 1)
            # the endpoint's answer is newer here: its 5 h and week count; Fable only it has
            self.assertEqual(self.rows(usage), [("5 h", 30), ("Týden", 40), ("Fable", 55)])
            self.report(five=33, week=41)  # a session answered since
            for _ in range(5):  # Orbit reads every 5 s
                usage = claude_usage.combined()
            self.assertEqual(get.call_count, 1)
            self.assertEqual(self.rows(usage), [("5 h", 33), ("Týden", 41), ("Fable", 55)])
            self.restart()  # a new Orbit doesn't ask again either
            claude_usage.combined()
            self.assertEqual(get.call_count, 1)
            self.age(claude_usage.OAUTH_FRESH_S + 5)
            self.asked_ago(claude_usage.OAUTH_EVERY_S + 1)
            claude_usage.combined()
            self.assertEqual(get.call_count, 2)
            self.age(claude_usage.OAUTH_FRESH_S + 5)
            claude_usage.combined(force=True)  # the menu's "Obnovit"
            self.assertEqual(get.call_count, 3)

    def test_not_asked_while_claude_code_isnt_used(self):
        with mock.patch.object(claude_usage.requests, "get", return_value=reply(body=FABLE)) as get:
            self.report(age=60)
            claude_usage.combined()
            self.assertEqual(get.call_count, 1)
            self.age(claude_usage.OAUTH_FRESH_S + 5)
            (self.status / "s1.mod.json").unlink()
            self.report(age=claude_usage.OAUTH_EVERY_S + 100)  # the last answer in a session: before the last ask
            self.asked_ago(claude_usage.OAUTH_EVERY_S + 1)
            usage = claude_usage.combined()
            self.assertEqual(get.call_count, 1)  # nothing moved since: not asked (overnight, say)
            self.assertEqual(usage.get("weekly_scoped").percent, 55)  # Fable from the last answer
            self.report(age=5)  # a session answered
            claude_usage.combined()
            self.assertEqual(get.call_count, 2)

    def test_too_often_keeps_the_bars(self):
        self.report(five=20, week=35, suffix=".json")  # Orbit's status line's file reads the same
        with mock.patch.object(claude_usage.requests, "get", return_value=reply(429, headers={"Retry-After": "3600"})) \
                as get:
            usage = claude_usage.combined()  # no error: the sessions' figures stand
            self.assertEqual(self.rows(usage), [("5 h", 20), ("Týden", 35)])
            self.assertEqual(usage.source, "combined")
            self.asked_ago(claude_usage.OAUTH_EVERY_S + 1)
            self.assertEqual(self.rows(claude_usage.combined()), [("5 h", 20), ("Týden", 35)])
            self.assertEqual(get.call_count, 1)  # the hour's pause holds

    def test_newest_report_wins_and_an_ended_window_drops(self):
        with mock.patch.object(claude_usage.requests, "get", return_value=reply(body=FABLE)):
            claude_usage.fetch_oauth()
        self.age(600)  # the endpoint's answer is 10 min old
        self.report("old", five=10, week=30, age=1800)  # half an hour old: the endpoint's newer
        self.report("new", five=31, week=41, age=60)
        self.asked_ago(60)
        usage = claude_usage.combined()
        self.assertEqual(self.rows(usage), [("5 h", 31), ("Týden", 41), ("Fable", 55)])
        for name in ("old", "new"):
            (self.status / f"{name}.mod.json").unlink()
        self.report(five=99, age=60, resets=-60)  # its 5-hour window is over: not 99 %
        self.assertEqual(self.rows(claude_usage.combined()), [("5 h", 30), ("Týden", 35), ("Fable", 55)])

    def test_without_the_sessions_figures_the_endpoint_alone(self):
        with mock.patch.object(claude_usage.requests, "get", return_value=reply(429)) as get:
            with self.assertRaises(claude_usage.Limited):
                claude_usage.combined()
            with self.assertRaises(claude_usage.Limited):  # every 5 s the same, without asking again
                claude_usage.combined()
            self.assertEqual(get.call_count, 1)
        claude_usage._retry_at = 0.0  # the pause is over
        data = json.loads(claude_usage.OAUTH_CACHE.read_text(encoding="utf-8"))
        claude_usage.OAUTH_CACHE.write_text(json.dumps(dict(data, retry_at=0)), encoding="utf-8")
        self.asked_ago(claude_usage.OAUTH_ALONE_S + 1)
        with mock.patch.object(claude_usage.requests, "get", return_value=reply(body=FABLE)) as get:
            self.assertEqual(self.rows(claude_usage.combined()), [("5 h", 30), ("Týden", 40), ("Fable", 55)])
            self.assertEqual(claude_usage.combined().source, "oauth")
            self.assertEqual(get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
