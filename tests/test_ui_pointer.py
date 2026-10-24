"""A mouse button for dictation acts where the pointer is (17 Oct, Pepa: "kde mám myš, tam to [má] mluvit, musím na
to úplně kliknout"): a Claude session driving Chrome kept bringing Chrome to the front and three dictations in a row
went into Chrome instead of the terminal under the mouse. inserter.pointed finds the window a click would bring to
the front (real off-screen windows, the pointer replaced, nothing activated); main.Dictation._follow_pointer brings
it there on a stub.

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
from ctypes import wintypes
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

from app import inserter, main  # noqa: E402

user32 = ctypes.WinDLL("user32")
user32.CreateWindowExW.restype = ctypes.c_void_p
user32.CreateWindowExW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint] + \
    [ctypes.c_int] * 4 + [ctypes.c_void_p] * 4
user32.DestroyWindow.argtypes = [ctypes.c_void_p]
user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
X, Y = -32000, -30500  # off every screen


class Pointed(unittest.TestCase):
    """Windows far off every screen, owned by a hidden one (no taskbar button), shown without activation."""

    def setUp(self):
        self.made = []
        self.owner = self.window(0, 0, visible=False)

    def tearDown(self):
        for hwnd in reversed(self.made):
            user32.DestroyWindow(hwnd)

    def window(self, ex: int, n: int, visible: bool = True) -> int:
        # WS_POPUP, SS_NOTIFY (a static control is see-through for the mouse without it)
        hwnd = user32.CreateWindowExW(ex, "STATIC", "orbit-test", 0x80000000 | 0x100, X + 80 * n, Y, 60, 60,
                                      getattr(self, "owner", None), None, None, None)
        self.assertTrue(hwnd)
        self.made.append(hwnd)
        if visible:
            user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        return hwnd

    def under(self, n: int) -> int:
        """inserter.pointed() with the pointer in the middle of window n."""
        def cursor(point):
            point._obj.x, point._obj.y = X + 80 * n + 30, Y + 30
            return True
        with mock.patch.object(inserter._user32, "GetCursorPos", cursor):
            return inserter.pointed()

    def test_an_ordinary_window(self):
        terminal = self.window(0, 1)
        self.assertEqual(self.under(1), terminal)

    def test_windows_that_never_take_focus(self):
        self.window(0x08000000, 1)  # WS_EX_NOACTIVATE: Orbit's button, its bubbles
        self.window(0x80, 2)  # WS_EX_TOOLWINDOW: popups, palettes
        self.assertEqual(self.under(1), 0)
        self.assertEqual(self.under(2), 0)

    def test_a_disabled_window(self):
        busy = self.window(0, 1)
        ctypes.windll.user32.EnableWindow(wintypes.HWND(busy), False)  # (a modal dialog's owner)
        self.assertEqual(self.under(1), 0)

    def test_nothing_there(self):
        self.assertEqual(self.under(5), 0)


class FollowPointer(unittest.TestCase):
    """main.Dictation._follow_pointer on a stub, the windows and focus_window replaced."""

    def setUp(self):
        self.d = SimpleNamespace(cfg={"ptt": {"kind": "mouse", "code": 6}})
        self.focused = []

    def follow(self, pointed=11, front=22):
        with mock.patch.object(main.inserter, "pointed", lambda: pointed), \
                mock.patch.object(main.inserter, "foreground", lambda: front), \
                mock.patch.object(main.inserter, "same_window", lambda a, b: a == b), \
                mock.patch.object(main.inserter, "app_name", lambda h: {11: "WindowsTerminal", 22: "chrome"}[h]), \
                mock.patch.object(main.sessions, "focus_window", lambda h: self.focused.append(h) or True):
            main.Dictation._follow_pointer(self.d)

    def test_the_terminal_under_the_mouse_comes_to_the_front(self):
        with self.assertLogs("orbit", "INFO") as logs:
            self.follow()
        self.assertEqual(self.focused, [11])
        self.assertIn("WindowsTerminal", logs.output[0])
        self.assertIn("chrome", logs.output[0])

    def test_already_in_front(self):
        self.follow(pointed=22)
        self.assertEqual(self.focused, [])

    def test_nothing_to_bring(self):  # over the taskbar, Orbit's button, a menu
        self.follow(pointed=0)
        self.assertEqual(self.focused, [])

    def test_a_key_leaves_the_window_in_front_alone(self):
        self.d.cfg["ptt"] = {"kind": "key", "code": 0xA3}
        self.follow()
        self.assertEqual(self.focused, [])


if __name__ == "__main__":
    unittest.main()
