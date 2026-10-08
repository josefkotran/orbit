"""Session colours by folder (app/colors.py and Dictation._tint_sessions on a stub): the user's choice wins, the others
get a stable colour nobody chose, each terminal is tinted once per colour and gets its own background back when the
setting goes off. No terminal is touched: colors.tint_sessions is replaced, tint() only meets consoles without a window.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
import logging
import os
import shutil
import subprocess
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

from app import colors, main  # noqa: E402

PEPA = {"hommel-portal": "green", "m-tex": "orange", "mtex-portal": "orange", "orbit": "blue"}


class ColorFor(unittest.TestCase):
    def test_choice_wins_and_others_get_what_is_left(self):
        self.assertEqual(colors.color_for(r"C:\Users\josef\hommel-portal", PEPA), "green")
        self.assertEqual(colors.color_for("C:/Users/josef/M-tex", PEPA), "orange")
        others = {colors.color_for(f"C:/x/{name}", PEPA) for name in ("pepa", "smetanka", "koral", "kucharka",
                                                                        "apertia", "lastrep", "pingo", "shorts")}
        self.assertTrue(others <= {"purple", "cyan", "pink", "yellow"}, others)  # not chosen, never red
        self.assertGreater(len(others), 1)
        self.assertEqual(colors.color_for("C:/x/pepa", PEPA), colors.color_for(r"D:\jinde\Pepa", PEPA))  # stable
        self.assertEqual(colors.color_for("C:/x/pepa", {"pepa": "nesmysl"}), colors.color_for("C:/x/pepa", {}))

    def test_shade_is_dark(self):
        for color in colors.COLORS:
            shade = colors.shade(color)
            self.assertRegex(shade, r"^#[0-9a-f]{6}$")
            self.assertLess(max(int(shade[i:i + 2], 16) for i in (1, 3, 5)), 0x40, color)  # text stays readable
        self.assertEqual(colors.shade("green"), "#132a1f")

    def test_no_window_no_tint(self):
        self.assertFalse(colors.tint(4_000_000_000 % 2**31, "#132a1f"))  # no such process
        hidden = subprocess.Popen("cmd.exe /k", executable=os.path.join(os.environ["SystemRoot"], "System32",
                                                                        "cmd.exe"),
                                  startupinfo=subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW,
                                                                     wShowWindow=0),
                                  creationflags=subprocess.CREATE_NEW_CONSOLE, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.5)
            self.assertFalse(colors.tint(hidden.pid, "#132a1f"))  # its console has no visible window: left alone
        finally:
            hidden.kill()


class TintSessions(unittest.TestCase):
    def setUp(self):
        self.cfg = {"folder_colors": dict(PEPA), "tint_sessions": True}
        self.d = SimpleNamespace(cfg=self.cfg, _tinted={})
        patch = mock.patch.object(main.colors, "tint_sessions")
        self.sent = patch.start()
        self.addCleanup(patch.stop)

    def tint(self, *sessions):
        self.sent.reset_mock()
        main.Dictation._tint_sessions(self.d, list(sessions))
        return self.sent.call_args.args[0] if self.sent.called else []

    def test_once_per_colour_and_back_when_off(self):
        hhw = SimpleNamespace(pid=11, cwd=r"C:\Users\josef\hommel-portal", folder="hommel-portal")
        orbit = SimpleNamespace(pid=12, cwd=r"C:\Users\josef\orbit", folder="orbit")
        self.assertEqual(self.tint(hhw, orbit), [(11, colors.shade("green")), (12, colors.shade("blue"))])
        self.assertEqual(self.tint(hhw, orbit), [])  # every second: nothing new
        self.cfg["folder_colors"]["orbit"] = "purple"
        self.assertEqual(self.tint(hhw, orbit), [(12, colors.shade("purple"))])
        self.assertEqual(self.tint(hhw), [])  # orbit's session ended
        self.cfg["tint_sessions"] = False
        self.assertEqual(self.tint(hhw), [(11, None)])  # its own background again
        self.assertEqual(self.tint(hhw, SimpleNamespace(pid=13, cwd="C:/x/pepa", folder="pepa")), [])


if __name__ == "__main__":
    unittest.main()
