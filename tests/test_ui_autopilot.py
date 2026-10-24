"""The Autopilot in the UI (app/ui.py, app/autopilotview.py, Dictation on a stub): the phone above the panel is there
only with Claude, left of the +, with how many sessions are on it, and opens the window; a session on it has a phone
and its round or next call in its row (and the row repaints when that changes); the window lists the running sessions,
starts one with its goal and interval, shows its report and last call, and keeps only a phone number it can call;
Dictation moves the sessions on with the overview, marks them for the panel and tells what happened in a bubble. Bland
and the session's mod are replaced: nothing is called.

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

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import autopilot, main, sessions, ui  # noqa: E402
from app.autopilotview import AutopilotWindow  # noqa: E402

SID = "3f1c2a9e-0000-4000-8000-000000000001"
OTHER = "3f1c2a9e-0000-4000-8000-000000000002"


def session(sid: str = SID, name: str = "Ceník Profodu", folder: str = "m-tex") -> sessions.Session:
    return sessions.Session(sid, cwd=f"C:\\Users\\jana\\{folder}", topic=name, state="done")


def pilot(stage: str = "working") -> autopilot.Pilot:
    p = autopilot.Pilot(SID, "Ceník Profodu", "m-tex", "Dodělej import", stage=stage, round=2,
                        report="Co jsem udělal: import.", next_call=0.0)
    p.calls.append(autopilot.Call(at=1_760_000_000, round=1, id="c1", result="answered", summary="Chce slevy.",
                                  transcript="Jana: Přidej slevy.", minutes=2.5, price=0.31))
    return p


class Widgets(unittest.TestCase):
    def setUp(self):
        self.elsewhere = False
        app = QApplication.instance()
        if app is not None and not isinstance(app, QApplication):  # another test's QGuiApplication: widgets need a
            # QApplication, so this test runs in a process of its own
            run = subprocess.run([sys.executable, "-m", "unittest", self.id().removeprefix("tests.")],
                                 cwd=Path(__file__).parent, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            self.elsewhere = True
            return
        self.app = app or QApplication([])

    def click(self, button, at: QPointF) -> None:
        button._press_global = button.mapToGlobal(at.toPoint())
        button._dragging = button._press_on_button = button._press_on_speaker = False
        button.mouseReleaseEvent(SimpleNamespace(button=lambda: Qt.LeftButton, position=lambda: QPointF(at)))

    def test_the_phone_left_of_the_plus_only_with_claude(self):
        if self.elsewhere:
            return
        button = ui.FloatingButton(lambda: 0.0)
        button.set_usage_visible(True)
        button.set_claude(False)
        self.assertIsNone(button._phone_center())
        button.set_claude(True)
        button.set_agent(True)  # the strip at its fullest
        phone, new = button._phone_center(), button._new_center()
        self.assertEqual(phone.y(), new.y())
        self.assertAlmostEqual(new.x() - phone.x(), button.AGENT_D + 6)
        self.assertGreater(phone.x() - button.AGENT_D / 2, button._dictations_center().x() + button.AGENT_D / 2)
        got = []
        button.autopilot_clicked.connect(lambda: got.append(True))
        self.click(button, phone)
        self.assertEqual(got, [True])
        button.set_autopilot_count(2)
        self.assertEqual(button._autopilots, 2)
        button.grab()  # paints with its number

    def test_a_session_on_it_shows_in_its_row(self):
        if self.elsewhere:
            return
        button = ui.FloatingButton(lambda: 0.0)
        button.set_usage_visible(True)
        s = session()
        button.set_sessions([s])
        shown = button._sessions_shown
        s.autopilot, s.autopilot_note = "kolo 2", "Autopilot: pracuje na kole 2."
        button.set_sessions([s])  # the same object, changed in place (as the tracker does)
        self.assertNotEqual(button._sessions_shown, shown)
        button.grab()
        self.assertIn("Autopilot: pracuje na kole 2.", s.tooltip())

    def test_the_window_lists_starts_and_shows(self):
        if self.elsewhere:
            return
        window = AutopilotWindow({"autopilot_phone": "", "autopilot_key": ""}, lambda: {"m-tex": "orange"})
        self.addCleanup(window.close)
        window.show_state([session(), session(OTHER, "Web", "orbit")], {})
        self.assertEqual(window.list.count(), 2)
        self.assertEqual(window._current, SID)
        self.assertFalse(window.setup.isHidden())
        self.assertTrue(window.running.isHidden())
        asked = []
        window.start_requested.connect(lambda *a: asked.append(a))
        window.goal.setPlainText("Dodělej import")
        window.interval.setCurrentIndex(window.interval.findData(1800))
        window.start.click()
        self.assertEqual(asked, [(SID, "Dodělej import", 1800)])

        window.show_state([session(), session(OTHER, "Web", "orbit")], {SID: pilot()})
        self.assertTrue(window.setup.isHidden())
        self.assertFalse(window.running.isHidden())
        self.assertIn("kole 2", window.state.text())
        self.assertEqual(window.report.toPlainText(), "Co jsem udělal: import.")
        self.assertIn("Jana: Přidej slevy.", window.transcript.toPlainText())
        self.assertIn("0,31 $", window.call_meta.text())
        self.assertFalse(window.call.isEnabled())  # it works: no call now
        window.show_state([session(), session(OTHER, "Web", "orbit")], {SID: pilot("paused")})
        self.assertEqual(window.call.text(), "Pokračovat")
        self.assertTrue(window.call.isEnabled())
        window.choose(OTHER)
        self.assertEqual(window._current, OTHER)
        window.show_state([], {})
        self.assertTrue(window.detail.isHidden())

    def test_the_window_keeps_only_a_number_it_can_call(self):
        if self.elsewhere:
            return
        window = AutopilotWindow({"autopilot_phone": "", "autopilot_key": "dpapi:x"}, lambda: {})
        self.addCleanup(window.close)
        self.assertIn("uložený", window.key.placeholderText())
        saved = []
        window.settings_saved.connect(saved.append)
        window.phone.setText("12")
        window.save.click()
        self.assertEqual(saved, [])
        self.assertIn("Tohle číslo neznám", window.calls_status.text())
        window.phone.setText("602 123 456")
        window.save.click()
        self.assertEqual(saved, [{"phone": "+420602123456", "key": None, "voice": "", "quiet": True}])
        window.key.setText("sk-new")
        window.save.click()
        self.assertEqual(saved[-1]["key"], "sk-new")
        self.assertEqual(window.key.text(), "")  # not left in the field


class Driving(unittest.TestCase):
    def test_dictation_moves_it_on_marks_the_rows_and_tells(self):
        s, told = session(), []
        ap = SimpleNamespace(pilots={SID: pilot("waiting")}, tick=lambda found: None,
                             drain_events=lambda: [("waiting", SID, "Ceník Profodu", "Hovor nikdo nezvedl.")])
        d = SimpleNamespace(autopilot=ap, tracker=SimpleNamespace(sessions={SID: s}), autopilot_window=None,
                            button=SimpleNamespace(set_autopilot_count=lambda n: told.append(("count", n))),
                            _notify=lambda text, **kw: told.append((text, kw["kind"], kw["note"])))
        main.Dictation._drive_autopilot(d, [s])
        self.assertEqual(s.autopilot, autopilot.clock_text(0.0))
        self.assertIn("zavolám v", s.autopilot_note)
        self.assertEqual(told, [("count", 1), ("Hovor nikdo nezvedl.", "waiting", "autopilot")])
        ap.pilots.clear()
        ap.drain_events = lambda: []
        main.Dictation._drive_autopilot(d, [s])
        self.assertEqual((s.autopilot, s.autopilot_note), ("", ""))  # off: its row is as before

    def test_it_needs_the_session_overview(self):
        d = SimpleNamespace(claude=SimpleNamespace(connected=True),
                            cfg={"claude_hooks": True, "show_sessions": False})
        self.assertIn("přehled relací", main.Dictation._autopilot_ready(d))
        d.cfg["show_sessions"] = True
        self.assertEqual(main.Dictation._autopilot_ready(d), "")


if __name__ == "__main__":
    unittest.main()
