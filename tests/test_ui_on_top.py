"""The button behind other programs' windows (17 Oct, Pepa: "Orbit goes behind the browser, with two Chromes open
I don't see it"): Windows had pushed it below ordinary windows and left it flagged topmost. winutil finds that on
real (off-screen, never activated) Win32 windows and puts it back; main.Dictation does it every second on a stub,
not while a full-screen game, video or presentation is in front.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
import ctypes
import logging
import os
import shutil
import sys
import tempfile
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
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import main, winutil  # noqa: E402

user32 = ctypes.WinDLL("user32")
user32.CreateWindowExW.restype = ctypes.c_void_p
user32.CreateWindowExW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint] + \
    [ctypes.c_int] * 4 + [ctypes.c_void_p] * 4
user32.DestroyWindow.argtypes = [ctypes.c_void_p]
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.c_uint]
NO_MOVE = 0x0001 | 0x0002 | 0x0010  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE


class RealWindows(unittest.TestCase):
    """Windows far off every screen, shown without activation: nothing to see, focus stays where it is."""

    def window(self, topmost: bool) -> int:
        ex = 0x08000000 | 0x80 | (0x8 if topmost else 0)  # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW (| WS_EX_TOPMOST)
        hwnd = user32.CreateWindowExW(ex, "STATIC", "orbit-test", 0x80000000 | 0x10000000,  # WS_POPUP | WS_VISIBLE
                                      -32000 + 60 * len(self.made), -31000, 50, 50, None, None, None, None)
        self.assertTrue(hwnd)
        self.made.append(hwnd)
        return hwnd

    def setUp(self):
        self.made = []

    def tearDown(self):
        for hwnd in self.made:
            user32.DestroyWindow(hwnd)

    def test_on_top(self):
        button = self.window(topmost=True)
        self.window(topmost=False)  # an ordinary window shown later: still below it
        self.assertTrue(winutil.is_topmost(button))
        self.assertEqual(winutil.windows_above(button), [])

    def test_pushed_down_and_back(self):
        button = self.window(topmost=True)
        user32.SetWindowPos(button, ctypes.c_void_p(-2), 0, 0, 0, 0, NO_MOVE)  # HWND_NOTOPMOST (someone else)
        browser = self.window(topmost=False)
        self.assertFalse(winutil.is_topmost(button))
        self.assertIn(browser, winutil.windows_above(button))
        self.assertTrue(winutil.put_on_top(button))
        self.assertTrue(winutil.is_topmost(button))
        self.assertEqual(winutil.windows_above(button), [])

    def test_hidden_and_minimized_windows_dont_count(self):
        button = self.window(topmost=True)
        user32.SetWindowPos(button, ctypes.c_void_p(-2), 0, 0, 0, 0, NO_MOVE)
        hidden, small = self.window(topmost=False), self.window(topmost=False)
        user32.ShowWindow(ctypes.c_void_p(hidden), 0)  # SW_HIDE
        user32.ShowWindow(ctypes.c_void_p(small), 7)  # SW_SHOWMINNOACTIVE
        above = winutil.windows_above(button)
        self.assertNotIn(hidden, above)
        self.assertNotIn(small, above)


class KeepOnTop(unittest.TestCase):
    """main.Dictation._keep_button_on_top on a stub, winutil replaced."""

    def setUp(self):
        self.d = SimpleNamespace(button=SimpleNamespace(isVisible=lambda: True, winId=lambda: 42), _buried_logged=0.0)
        self.put = []

    def tick(self, above=(), topmost=True, quiet=True):
        with mock.patch.object(winutil, "windows_above", lambda h: list(above)), \
                mock.patch.object(winutil, "is_topmost", lambda h: topmost), \
                mock.patch.object(winutil, "accepts_notifications", lambda: quiet), \
                mock.patch.object(winutil, "put_on_top", self.put.append), \
                mock.patch.object(main.inserter, "app_name", lambda h: "chrome"):
            main.Dictation._keep_button_on_top(self.d)

    def test_on_top_nothing_happens(self):
        with self.assertNoLogs("orbit"):
            self.tick()
        self.assertEqual(self.put, [])

    def test_behind_the_browser_comes_back(self):
        with self.assertLogs("orbit", "INFO") as logs:
            self.tick(above=[7, 8])
            self.tick(above=[7])  # pushed down again within a minute: back on top, the log says it once
        self.assertEqual(self.put, [42, 42])
        self.assertEqual(len(logs.records), 1)
        self.assertIn("chrome", logs.output[0])

    def test_lost_topmost_comes_back(self):
        self.tick(topmost=False)
        self.assertEqual(self.put, [42])

    def test_not_over_a_full_screen_game_or_video(self):
        self.tick(above=[7], quiet=False)
        self.assertEqual(self.put, [])

    def test_hidden_button_is_left_alone(self):
        self.d.button.isVisible = lambda: False
        self.tick(above=[7])
        self.assertEqual(self.put, [])


if __name__ == "__main__":
    unittest.main()
