"""The speaker button left of the mic (FloatingButton, Dictation on a stub) and the 5-hour forecast in the panel's
header: a click while Orbit reads stops that and nothing more (until 10 Oct it muted Orbit for good), otherwise it
mutes or unmutes; a right click has its own menu; anything read lights it up and is kept for "Přečíst znovu"; a
repaint of the speaker alone paints what a full one does; the forecast never shows without the time the limit
resets (Pepa, 10 Oct: a bare "dojde v 15:51" said nothing).

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
from datetime import datetime, timedelta, timezone
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

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontMetricsF, QImage, QRegion  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import claude_usage, main, ui  # noqa: E402
from app.claude_usage import Limit, Usage  # noqa: E402


def event(button, at: QPointF):
    return SimpleNamespace(button=lambda: button, position=lambda: QPointF(at),
                           globalPosition=lambda: QPointF(at))


class Button(unittest.TestCase):
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
        self.button = ui.FloatingButton(lambda: 0.0)
        self.got = []
        for name in ("stop_reading", "mute_toggled", "speaker_menu_requested", "menu_requested"):
            getattr(self.button, name).connect(lambda *a, name=name: self.got.append(name))

    def click(self, at: QPointF):
        self.button.mousePressEvent(event(Qt.LeftButton, at))
        self.button.mouseReleaseEvent(event(Qt.LeftButton, at))

    def test_a_click_while_reading_stops_it_otherwise_it_mutes(self):
        if self.elsewhere:
            return
        speaker = self.button._speaker_center()
        self.click(speaker)
        self.button.set_reading(True)
        self.click(speaker)
        self.assertEqual(self.got, ["mute_toggled", "stop_reading"])

    def test_what_it_showed_when_pressed_counts(self):
        if self.elsewhere:
            return
        speaker = self.button._speaker_center()
        self.button.set_reading(True)
        self.button.mousePressEvent(event(Qt.LeftButton, speaker))
        self.button.set_reading(False)  # the answer ended while the mouse was down: the user meant stop, not mute
        self.button.mouseReleaseEvent(event(Qt.LeftButton, speaker))
        self.assertEqual(self.got, ["stop_reading"])

    def test_a_right_click_on_the_speaker_has_its_own_menu(self):
        if self.elsewhere:
            return
        self.button.mousePressEvent(event(Qt.RightButton, self.button._speaker_center()))
        self.button.mousePressEvent(event(Qt.RightButton, self.button._button_center()))
        self.assertEqual(self.got, ["speaker_menu_requested", "menu_requested"])

    def test_it_lights_up_under_the_mouse_and_waves_only_while_reading(self):
        if self.elsewhere:
            return
        b = self.button
        b.mouseMoveEvent(event(Qt.NoButton, b._speaker_center()))
        self.assertTrue(b._speaker_hover)
        b.mouseMoveEvent(event(Qt.NoButton, b._button_center()))
        self.assertFalse(b._speaker_hover)
        self.assertFalse(b._wave_timer.isActive())
        b.set_reading(True)
        self.assertTrue(b._wave_timer.isActive())
        b.set_reading(False)
        self.assertFalse(b._wave_timer.isActive())
        self.assertIn("Klikni a Orbit ztlumíš", b._speaker_tooltip())
        b.set_reading(True)
        self.assertIn("Klikni a přestanu", b._speaker_tooltip())

    def test_the_speaker_alone_paints_what_a_whole_repaint_does(self):
        if self.elsewhere:
            return
        b = self.button
        b.set_claude(True)
        b.set_usage_visible(True)
        b.set_usage(Usage([Limit("session", "5 h", "5hodinové okno", 40, None)]), None)
        area = b._speaker_area()
        for change in (lambda: b.set_reading(True), lambda: setattr(b, "_wave", 2),
                       lambda: setattr(b, "_speaker_hover", True), lambda: b.set_muted(True)):
            before = QImage(b.size(), QImage.Format_ARGB32_Premultiplied)
            before.fill(0)
            b.render(before)
            change()
            whole = QImage(b.size(), QImage.Format_ARGB32_Premultiplied)
            whole.fill(0)
            b.render(whole)
            with mock.patch.object(b, "_paint_panel") as panel:  # the short way: the panel isn't painted
                b.render(before, area.topLeft(), QRegion(area))  # only the speaker's square, over the old one
            panel.assert_not_called()
            self.assertEqual(before, whole)


class HeaderNote(unittest.TestCase):
    def setUp(self):
        if not QApplication.instance():
            self.app = QApplication([])
        self.now = datetime.now(timezone.utc)
        self.button = SimpleNamespace(_usage_error=None, _stale=lambda: False, _forecast=None, _usage=Usage(
            [Limit("session", "5 h", "5hodinové okno", 62, self.now + timedelta(hours=2, minutes=14))]))
        font = QFont("Segoe UI")
        font.setPixelSize(11)
        self.metrics = QFontMetricsF(font)

    def note(self, room=370.0):
        return ui.FloatingButton._header_note(self.button, room, self.metrics)

    def test_the_forecast_always_with_when_the_limit_resets(self):
        self.button._forecast = self.now + timedelta(hours=1, minutes=5)
        eta = claude_usage.clock(self.button._forecast)
        resets = claude_usage.clock(self.button._usage.limits[0].resets_at)
        warning, rest, _ = self.note(10_000.0)
        self.assertTrue(warning.startswith("Při tomhle tempu vyčerpáš limit 5 h"))
        longest = self.metrics.horizontalAdvance(warning + rest)
        warning, rest, _ = self.note(longest - 1)  # (offscreen fonts are wider: measured, not a number of pixels)
        self.assertLess(self.metrics.horizontalAdvance(warning + rest), longest - 1)  # a shorter wording that fits
        for room in (10_000.0, longest - 1, 10.0):
            warning, rest, icon = self.note(room)
            self.assertIn(eta, warning)
            self.assertIn(resets, rest)
            self.assertFalse(icon)

    def test_without_a_forecast_when_it_resets(self):
        warning, rest, icon = self.note(10_000.0)
        self.assertEqual(warning, "")
        self.assertTrue(rest.startswith("limit 5 h se obnoví v "))
        self.assertIn("(za 2 h 1", rest)
        self.assertTrue(icon)

    def test_the_sentence_says_how_long_it_would_wait(self):
        eta = datetime(2026, 10, 10, 13, 51, tzinfo=timezone.utc)
        text = claude_usage.forecast_text(eta, eta + timedelta(hours=1, minutes=29))
        self.assertIn(claude_usage.clock(eta), text)
        self.assertIn(claude_usage.clock(eta + timedelta(hours=1, minutes=29)), text)
        self.assertIn("čekalo 1 h 29 min", text)
        self.assertTrue(claude_usage.forecast_text(eta, None).endswith(f"v {claude_usage.clock(eta)}."))


class Dictation(unittest.TestCase):
    """Dictation's side of the speaker on a stub: no voice, no sound card."""

    def setUp(self):
        self.said, self.stopped, self.reading = [], [], []
        speaker = SimpleNamespace(say=self.said.append)
        self.d = SimpleNamespace(
            cfg={"muted": False}, _speech=[], _speaking=False, _reading_artifact=False, _said_at=0.0,
            _agent_state="idle", _last_speech=("", ""), _speaker=lambda: speaker,
            _set_agent_state=lambda state: setattr(self.d, "_agent_state", state), _agent_rest=lambda: "idle",
            _stop_speech=lambda artifacts_only=False: self.stopped.append(artifacts_only),
            button=SimpleNamespace(set_reading=self.reading.append, set_muted=lambda on: None))
        self.d._speak = lambda text, wait=False, kind="", force=False: self.said.append((text, kind, force))

    def say(self, text, kind=""):
        self.d._speech.append((text, kind))
        main.Dictation._say_next(self.d)

    def test_anything_read_lights_the_speaker_and_is_kept_for_again(self):
        self.say("Hotovo: Ceník Profodu. Ceník je hotový.")
        self.assertEqual(self.reading, [True])
        self.assertEqual(self.d._last_speech, ("Hotovo: Ceník Profodu. Ceník je hotový.", ""))
        self.say("Mám to poslat?", "confirm")  # a question to answer now isn't "the last" to read again
        self.say("Ahoj, tímhle hlasem…", "preview")
        self.assertEqual(self.d._last_speech[0], "Hotovo: Ceník Profodu. Ceník je hotový.")
        main.Dictation._say_next(self.d)  # the queue is empty: done
        self.assertEqual(self.reading[-1], False)

    def test_stopping_doesnt_mute(self):
        main.Dictation._stop_reading(self.d)
        self.assertEqual(self.stopped, [False])
        self.assertEqual(self.reading, [False])
        self.assertFalse(self.d.cfg["muted"])

    def test_read_again_even_muted(self):
        self.d.cfg["muted"] = True
        self.d._last_speech = ("Artefakt z relace m-tex: …", "artifact")
        main.Dictation._reread_last(self.d)
        self.assertEqual(self.said, [("Artefakt z relace m-tex: …", "artifact", True)])

    def test_unmuting_chimes_muting_stops_the_reading(self):
        with mock.patch.object(main.config, "save"), mock.patch.object(main.winutil, "play") as play:
            main.Dictation._toggle_mute(self.d)
            self.assertTrue(self.d.cfg["muted"])
            self.assertEqual(self.stopped, [False])
            play.assert_not_called()
            main.Dictation._toggle_mute(self.d)
            play.assert_called_once_with("info")


if __name__ == "__main__":
    unittest.main()
