"""hotkey.PushToTalk without hooks (they ignore simulated input, so _handle is called directly).

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import logging
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import hotkey  # noqa: E402

RCTRL = 0xA3


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Latch(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.clock = Clock()
        self.saved = hotkey.time.monotonic
        hotkey.time.monotonic = self.clock
        self.ptt = hotkey.PushToTalk({"kind": "key", "code": RCTRL}, lambda: self.calls.append("press"),
                                     lambda: self.calls.append("release"))

    def tearDown(self):
        hotkey.time.monotonic = self.saved

    def key(self, down, code=RCTRL, after=0.033):
        self.clock.now += after
        return self.ptt._handle(down, "key", code)

    def test_repeats_after_the_cap_start_nothing(self):
        self.key(True)
        for _ in range(10):
            self.key(True)  # Windows repeats the held key
        self.ptt.reset()  # the 5-minute cap ended the recording
        for _ in range(50):
            self.assertTrue(self.key(True))  # still swallowed
        self.assertTrue(self.key(False))
        self.assertEqual(self.calls, ["press"])
        self.key(True, after=0.5)  # a real new press
        self.key(False)
        self.assertEqual(self.calls, ["press", "press", "release"])

    def test_release_missed_on_the_lock_screen(self):
        self.key(True)
        self.key(True)
        self.ptt.reset()  # the secure desktop: its key-up never comes
        self.key(True, after=60)  # back at the desktop, a new press
        self.assertEqual(self.calls, ["press", "press"])

    def test_check_stuck_leaves_a_latched_key(self):
        self.key(True)
        self.key(True)
        self.ptt.reset()
        self.clock.now += 5
        self.assertFalse(self.ptt.check_stuck())
        self.assertEqual(self.calls, ["press"])

    def test_mouse_button_is_not_latched(self):
        ptt = hotkey.PushToTalk({"kind": "mouse", "code": hotkey.MOUSE_X2}, lambda: self.calls.append("press"),
                                lambda: self.calls.append("release"))
        ptt._handle(True, "mouse", hotkey.MOUSE_X2)
        ptt.reset()
        ptt._handle(False, "mouse", hotkey.MOUSE_X2)
        ptt._handle(True, "mouse", hotkey.MOUSE_X2)
        self.assertEqual(self.calls, ["press", "press"])

    def test_normal_hold(self):
        self.key(True)
        self.key(True)
        self.key(False)
        self.key(True, after=0.2)
        self.key(False)
        self.assertEqual(self.calls, ["press", "release", "press", "release"])


if __name__ == "__main__":
    unittest.main()
