"""sessions._title_lines reads a transcript backwards: the same title as a forward read of the whole file, also with
lines across block borders. A turn that leaves work in the background is no "hotovo" yet.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
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
from unittest import mock

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import sessions  # noqa: E402


def forward(path) -> str:  # the old way: every line of the file
    with open(path, "rb") as f:
        return sessions._topic([line for line in f if b'"ai-title"' in line])


class TitleTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="orbit-title-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.block = sessions.TITLE_BLOCK
        sessions.TITLE_BLOCK = 1000  # many block borders in a small file
        self.addCleanup(setattr, sessions, "TITLE_BLOCK", self.block)

    def write(self, lines) -> Path:
        path = self.dir / "t.jsonl"
        path.write_bytes(b"".join(json.dumps(x, ensure_ascii=False).encode() + b"\r\n" for x in lines))
        return path

    def test_same_title_as_forward(self):
        filler = [{"type": "user", "text": "x" * (37 * i % 900)} for i in range(200)]
        cases = [
            [{"type": "ai-title", "aiTitle": "Katalog z Německa"}] + filler,
            filler[:50] + [{"type": "ai-title", "aiTitle": "První"}] + filler + [{"type": "ai-title", "aiTitle": "Druhé"}],
            filler + [{"type": "ai-title", "aiTitle": "Na konci"}],
            filler[:120] + [{"type": "ai-title", "aiTitle": "Dlouhé " + "y" * 3000}] + filler[:80],
            filler,
        ]
        for lines in cases:
            path = self.write(lines)
            self.assertEqual(sessions._topic(sessions._title_lines(str(path))), forward(path))
        self.assertEqual(sessions._title_lines(str(self.dir / "missing.jsonl")), [])
        (self.dir / "empty.jsonl").write_bytes(b"")
        self.assertEqual(sessions._title_lines(str(self.dir / "empty.jsonl")), [])

    def test_broken_newest_title_falls_back(self):
        path = self.dir / "t.jsonl"
        path.write_bytes('{"type":"ai-title","aiTitle":"Starý"}\n'.encode() + b'{"type":"user"}\n' * 300 +
                         b'{"type":"ai-title","aiTitle":\n')
        self.assertEqual(sessions._topic(sessions._title_lines(str(path))), "Starý")


class BackgroundWork(unittest.TestCase):
    """A turn that ends with work left running in the background (Claude Code's Stop hook lists it, cc_hook keeps it
    as "background"): the session still works and no "hotovo" is told; the Stop after which nothing is left is."""

    SID = "bg-test"

    def setUp(self):
        sessions.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: [f.unlink() for f in sessions.SESSIONS_DIR.glob(f"{self.SID}.*.json")])
        # Claude Code's own list says idle (its turn ended) later than the Stop: not an interrupted turn
        reg = {self.SID: {"status": "idle", "statusUpdatedAt": (time.time() + 5) * 1000, "cwd": "C:/proj/web"}}
        for name, value in (("_running", lambda: (reg, set())), ("_alive", lambda *a: True),
                            ("_terminal_by_title", lambda topic: 0)):
            patch = mock.patch.object(sessions, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def hook(self, event: str, at: float, **fields) -> None:
        record = dict(session_id=self.SID, hook_event_name=event, cwd="C:/proj/web", time=at, pid=0, hwnd=0, **fields)
        (sessions.SESSIONS_DIR / f"{self.SID}.{event}.json").write_text(json.dumps(record), encoding="utf-8")

    def test_done_only_when_nothing_runs_in_the_background(self):
        tracker, now = sessions.SessionTracker(), time.time()
        self.hook("UserPromptSubmit", now - 60, prompt="Otestuj to")
        tracker.poll()  # the first look tells nothing
        self.hook("Stop", now - 10, last_assistant_message="Testy běží na pozadí, dám vědět.",
                  background=[{"type": "shell", "what": "npm test"}, {"type": "subagent", "what": "Prozkoumej API"},
                              {"type": "subagent", "what": "Najdi chyby"}])
        self.assertEqual(tracker.poll(), [])
        s = tracker.sessions[self.SID]
        self.assertEqual(s.state, "working")
        self.assertIn("Na pozadí běží: příkaz, 2× podagent", s.tooltip())
        self.assertIn("· npm test", s.tooltip())
        self.hook("Stop", now - 2, last_assistant_message="Testy prošly.")  # its work reported back, a new turn
        changes = tracker.poll()
        self.assertEqual([(c[0].id, c[1]) for c in changes], [(self.SID, "done")])
        self.assertEqual((s.state, s.background, s.message), ("done", [], "Testy prošly."))


if __name__ == "__main__":
    unittest.main()
