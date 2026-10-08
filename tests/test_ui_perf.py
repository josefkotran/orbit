"""Small things off Orbit's hot paths: the session panel repaints only when its rows change (the turning screwdrivers
of working sessions only their own squares), and a kept recording is written after the text is on its way to the
window.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
from PySide6.QtGui import QRegion  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import main, ui  # noqa: E402
from app.sessions import Session  # noqa: E402


class FakeTimer:
    def __init__(self):
        self.on = False

    def isActive(self):
        return self.on

    def start(self):
        self.on = True

    def stop(self):
        self.on = False


class SessionRepaintTest(unittest.TestCase):
    def test_repaints_only_when_rows_change(self):
        calls = []
        button = SimpleNamespace(_sessions=[], _session_rows=[], _sessions_look=ui.FloatingButton._sessions_look,
                                 _relayout=lambda: calls.append("relayout"), _auto_align=lambda: None,
                                 update=lambda: calls.append("update"), _work_timer=FakeTimer())

        def poll(state="working", context=0.31, message=""):
            return [Session(id="a", cwd="C:/m-tex", topic="Katalog", state=state, context_pct=context * 100,
                            message=message),
                    Session(id="b", cwd="C:/orbit", state="idle")]
        ui.FloatingButton.set_sessions(button, poll())
        self.assertEqual(calls, ["relayout", "update"])
        button._session_rows = [("row a", button._sessions[0]), ("row b", button._sessions[1])]  # as painted
        calls.clear()
        fresh = poll(message="nová odpověď")  # nothing the rows show
        ui.FloatingButton.set_sessions(button, fresh)
        self.assertEqual(calls, [])
        self.assertIs(button._session_rows[0][1], fresh[0])  # a click or tooltip sees the current session
        ui.FloatingButton.set_sessions(button, poll(context=0.314))  # still 31 %
        self.assertEqual(calls, [])
        ui.FloatingButton.set_sessions(button, poll(context=0.32))
        self.assertEqual(calls, ["update"])
        calls.clear()
        ui.FloatingButton.set_sessions(button, poll(state="done", context=0.32))
        self.assertEqual(calls, ["update"])
        self.assertFalse(button._work_timer.on)  # nothing works: no screwdriver turns

    def test_screwdrivers_turn_in_their_squares_only(self):
        app = QApplication.instance()
        if app is not None and not isinstance(app, QApplication):  # another test's QGuiApplication: a widget
            # needs a QApplication, so this one runs in a process of its own
            test = f"{__name__}.SessionRepaintTest.test_screwdrivers_turn_in_their_squares_only"
            run = subprocess.run([sys.executable, "-m", "unittest", test], cwd=Path(__file__).parent,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            return
        app or QApplication([])
        button = ui.FloatingButton(lambda: 0.0)
        button.set_claude(True)
        button.set_usage_visible(True)
        button.set_sessions([Session(id="a", cwd="C:/m-tex", topic="Katalog", state="working"),
                             Session(id="b", cwd="C:/orbit", topic="Barvy", state="idle")])
        self.assertTrue(button._work_timer.isActive())
        button.grab()  # a full paint: where the screwdriver is
        self.assertEqual(len(button._work_icons), 1)
        square = QRegion(button._work_icons[0].toAlignedRect())
        self.assertTrue(button._only_work_icons(square))
        self.assertFalse(button._only_work_icons(square + QRegion(0, 0, 40, 40)))
        before = button._work_angle()
        button._work_tick()
        self.assertNotEqual(button._work_angle(), before)
        self.assertEqual(ui.STATE_LABELS["idle"], "hotovo")  # only "pracuje" and "hotovo" (and what needs the user)
        button.set_sessions([Session(id="b", cwd="C:/orbit", topic="Barvy", state="done")])
        self.assertFalse(button._work_timer.isActive())


class SaveAfterTextTest(unittest.TestCase):
    def test_recording_is_saved_after_the_text_goes(self):
        order = []
        bridge = SimpleNamespace(dictated=SimpleNamespace(emit=lambda take: order.append(("text", take.stem))),
                                 agent_heard=SimpleNamespace(emit=lambda *a: order.append("agent")),
                                 transcribe_failed=SimpleNamespace(emit=lambda *a: order.append("failed")))
        d = SimpleNamespace(bridge=bridge, _recording_stem=lambda: "20261008-120000",
                            _save_recording=lambda audio, text, stem: order.append(("save", text, stem)))
        take = main.Take("")
        take.texts, take.raw, take.audio, take.target = ["Ahoj."], ["Ahoj."], [np.zeros(160, np.int16)], 5
        main.Dictation._finish_take(d, take, [], True, True, False)
        # the history entry knows its recording before the file is written
        self.assertEqual(order, [("text", "20261008-120000"), ("save", "Ahoj.", "20261008-120000")])
        order.clear()
        take.stem = ""
        main.Dictation._finish_take(d, take, [], True, False, False)  # not kept
        self.assertEqual(order, [("text", "")])


if __name__ == "__main__":
    unittest.main()
