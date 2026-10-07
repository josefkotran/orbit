"""onboarding.ClaudeConnection: a first check of Claude Code that fails (a slow start of Windows, an update in
progress) is repeated soon, not only in 5 minutes. claude_setup.status is replaced: no claude.exe is run.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import logging
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import claude_setup, onboarding  # noqa: E402

APP = QApplication.instance() or QApplication([])
OK = claude_setup.Status(installed=True, exe="claude.exe", version="2.1.288", logged_in=True, method="claude.ai")


class FirstCheck(unittest.TestCase):
    def setUp(self):
        self.saved = claude_setup.status, onboarding.ClaudeConnection.RECHECK_MS, \
            getattr(onboarding.ClaudeConnection, "QUICK_RECHECK_MS", None)
        onboarding.ClaudeConnection.RECHECK_MS = 3000  # stands for the 5 minutes
        if self.saved[2] is not None:
            onboarding.ClaudeConnection.QUICK_RECHECK_MS = (100, 200, 400)

    def tearDown(self):
        claude_setup.status, onboarding.ClaudeConnection.RECHECK_MS = self.saved[:2]
        if self.saved[2] is not None:
            onboarding.ClaudeConnection.QUICK_RECHECK_MS = self.saved[2]

    def connected_after(self, answers) -> float:
        answers = list(answers)
        claude_setup.status = lambda timeout=30: answers.pop(0) if len(answers) > 1 else answers[0]
        conn = onboarding.ClaudeConnection()
        t0 = time.monotonic()
        conn.refresh()
        while not conn.connected and time.monotonic() - t0 < 10:
            APP.processEvents()
            time.sleep(0.01)
        self.assertTrue(conn.connected)
        return time.monotonic() - t0

    def test_failed_first_check_is_repeated_soon(self):
        took = self.connected_after([claude_setup.Status(installed=True, error="Claude Code neodpovídá."), OK])
        self.assertLess(took, 1.5)

    def test_missing_exe_during_an_update_is_repeated_soon(self):
        took = self.connected_after([claude_setup.Status(), claude_setup.Status(), OK])
        self.assertLess(took, 1.5)

    def test_not_logged_in_waits_the_long_interval(self):
        took = self.connected_after([claude_setup.Status(installed=True, exe="claude.exe"), OK])
        self.assertGreater(took, 2.5)


if __name__ == "__main__":
    unittest.main()
