"""The fold and unfold animation (16 Oct, Pepa: "když to chci minimalizovat, ať to udělá nějakou mega cool animaci …
když to odminimalizovávám, ať to udělá hezkou animaci a načte se okno"): its first frame is what was on the screen and
its last one what the button then shows, the button changes at once and shows nothing meanwhile, the mic opening ends
it, and it plays only for the user's click or the menu with Windows' animation effects on.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
import logging
import math
import os
import shutil
import subprocess
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

from PySide6.QtCore import QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QHideEvent, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import foldfx, ui  # noqa: E402

PAD = foldfx.PAD


def same(a: QImage, b: QImage, tolerance: int = 2) -> bool:
    """The same picture (each channel within tolerance)."""
    a, b = a.convertToFormat(QImage.Format_ARGB32), b.convertToFormat(QImage.Format_ARGB32)
    if a.size() != b.size():
        return False
    if a == b:
        return True
    return all(max(abs(ca - cb) for ca, cb in zip(a.pixelColor(x, y).getRgb(), b.pixelColor(x, y).getRgb()))
               <= tolerance for y in range(a.height()) for x in range(a.width()))


def opaque_outside(image: QImage, keep: QRect) -> int:
    """How many pixels outside keep aren't see-through."""
    return sum(1 for y in range(0, image.height(), 2) for x in range(0, image.width(), 2)
               if not keep.contains(x, y) and image.pixelColor(x, y).alpha() > 8)


def mouse(at: QPointF, button=Qt.LeftButton, origin: QPoint = QPoint()):
    return SimpleNamespace(button=lambda: button, position=lambda: QPointF(at),
                           globalPosition=lambda: QPointF(at) + QPointF(origin))


class FoldFxTest(unittest.TestCase):
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
        self.b = ui.FloatingButton(lambda: 0.0)
        self.b._timer.stop()
        self.b._auto_align = lambda: None  # (it goes by where the button is on the screen) the panel above, right
        self.b._wanted_align = lambda pos: ("right", False)
        self.b.set_claude(True)
        self.b.set_usage_visible(True)
        self.b.set_claude_version({"installed": "2.1.301", "latest": "2.1.301", "state": "current", "target": "",
                                   "tip": ""})
        self.b._align, self.b._below = "right", False
        self.b._relayout()
        self.b.place_button(QPoint(900, 500))
        self.b.set_state("idle")
        self.b._state = "idle"
        self.visible = mock.patch.object(self.b, "isVisible", lambda: True)
        self.effects = mock.patch.object(foldfx, "animations_on", lambda: True)

    def tearDown(self):
        if not self.elsewhere:
            self.b._end_fx()
            self.b.close()

    def folded_icon(self) -> QImage:
        """The button's own folded paint (no animation), and back."""
        self.b.set_collapsed(True)
        icon = self.b.grab().toImage()
        self.b.set_collapsed(False)
        return icon

    def overlay(self, folding: bool) -> foldfx.FoldFx:
        full = QRect(self.b.pos(), self.b.size())
        center = QPointF(self.b.button_pos()) + QPointF(self.b._side / 2, self.b._side / 2)
        return foldfx.FoldFx(self.b._snapshot(full.size()), full, center, folding, self.b._paint_icon,
                             self.b.ICON_D / 2, seed=1)

    def icon_square(self, fx: foldfx.FoldFx) -> QRect:
        side = self.b._side
        return QRect(round(fx._c.x() - side / 2), round(fx._c.y() - side / 2), side, side)

    def test_frames_begin_and_end_where_the_button_does(self):
        if self.elsewhere:
            return
        panel = self.b.grab().toImage()
        icon = self.folded_icon()
        fold, unfold = self.overlay(True), self.overlay(False)
        picture = QRect(PAD, PAD, panel.width(), panel.height())
        self.assertTrue(same(fold.frame(0).copy(picture), panel))  # folding: first what's on the screen
        self.assertEqual(opaque_outside(fold.frame(0), picture), 0)
        last = fold.frame(1)
        self.assertTrue(same(last.copy(self.icon_square(fold)), icon))  # last: the icon the button then shows
        self.assertEqual(opaque_outside(last, self.icon_square(fold)), 0)  # no star or wave left over
        first = unfold.frame(0)
        self.assertTrue(same(first.copy(self.icon_square(unfold)), icon))  # unfolding: from the icon
        self.assertEqual(opaque_outside(first, self.icon_square(unfold)), 0)
        self.assertTrue(same(unfold.frame(1).copy(picture), panel))  # to the panel as the button shows it
        self.assertEqual(opaque_outside(unfold.frame(1), picture), 0)

    def test_in_between_it_moves_and_reaches_past_the_window(self):
        if self.elsewhere:
            return
        fold, unfold = self.overlay(True), self.overlay(False)
        self.assertGreater(len(fold._stars), 30)  # stars on the panel's parts
        ends = [fold.frame(0), fold.frame(1)]
        for u in (0.2, 0.4, 0.6, 0.8):
            frame = fold.frame(u)
            self.assertFalse(any(same(frame, end, 0) for end in ends), u)
        # the shock wave past the mic's square, beyond where the button's window ends (the animation's own window)
        window = QRect(PAD, PAD, self.b.width(), self.b.height())
        self.assertGreater(opaque_outside(fold.frame(0.75), window), 0)
        self.assertGreater(opaque_outside(unfold.frame(0.5), window), 0)

    def test_the_moon_goes_behind_the_planet(self):
        if self.elsewhere:
            return

        def blue(moon):
            image = QImage(80, 80, QImage.Format_ARGB32_Premultiplied)
            image.fill(Qt.transparent)
            p = QPainter(image)
            p.setRenderHint(QPainter.Antialiasing)
            self.b._paint_icon(p, QPointF(40, 40), 1.5, 24, moon)  # (spin 24: the orbit level)
            p.end()
            return sum(1 for y in range(80) for x in range(80)
                       if (c := image.pixelColor(x, y)).blue() > 150 and c.blue() - c.red() > 60 and c.alpha() > 200)

        self.assertGreater(blue(math.pi / 2), 5)  # in front of the planet
        self.assertEqual(blue(-math.pi / 2), 0)  # behind it
        self.assertGreater(blue(None), 5)

    def test_folding_plays_over_the_button_that_folded_at_once(self):
        if self.elsewhere:
            return
        place, before = self.b.button_pos(), QRect(self.b.pos(), self.b.size())
        panel = self.b.grab().toImage()
        with self.visible, self.effects:
            self.b.set_collapsed(True, animate=True)
        fx = self.b._fx
        self.assertIsNotNone(fx)
        fx.stop()
        self.assertTrue(fx._folding)
        self.assertEqual((self.b.width(), self.b.height(), self.b.button_pos()),
                         (self.b._side, self.b._side, place))  # what a click does is already the icon's
        self.assertEqual(fx.geometry(), before.adjusted(-PAD, -PAD, PAD, PAD))
        self.assertTrue(same(fx._shot.toImage(), panel))
        self.assertEqual(opaque_outside(self.b.grab().toImage(), QRect()), 0)  # the button shows nothing meanwhile
        fx.finished.emit()
        self.assertIsNone(self.b._fx)
        self.assertGreater(self.b.grab().toImage().pixelColor(36, 22).alpha(), 200)  # now the icon is the button's

    def test_unfolding_shows_the_panel_it_is_about_to_be(self):
        if self.elsewhere:
            return
        self.b.set_collapsed(True)
        place = self.b.button_pos()
        with self.visible, self.effects:
            self.b.set_collapsed(False, animate=True)
        fx = self.b._fx
        fx.stop()
        self.assertFalse(fx._folding)
        self.assertEqual(self.b.button_pos(), place)
        self.assertFalse(self.b._collapse_rect().isEmpty())  # its chips are where they'll be
        self.assertEqual(fx.geometry(), QRect(self.b.pos(), self.b.size()).adjusted(-PAD, -PAD, PAD, PAD))
        fx.finished.emit()
        self.assertTrue(same(fx._shot.toImage(), self.b.grab().toImage()))

    def test_the_mic_opening_ends_it_at_once(self):
        """Privacy: red the moment it listens, not after the animation."""
        if self.elsewhere:
            return
        with self.visible, self.effects:
            self.b.set_collapsed(True, animate=True)
        self.b._fx.stop()
        self.b.set_state("recording")
        self.assertIsNone(self.b._fx)
        red = self.b.grab().toImage().pixelColor(22, 36)
        self.assertGreater(red.red(), 180)
        self.assertLess(red.green(), 120)
        with self.visible, self.effects:
            self.b.set_collapsed(False, animate=True)
        self.b._fx.stop()
        self.b.set_agent_state("listening")
        self.assertIsNone(self.b._fx)
        self.b.set_agent_state("idle")
        with self.visible, self.effects:
            self.b.set_collapsed(True, animate=True)
        self.b._fx.stop()
        self.b.hideEvent(QHideEvent())  # (the tests' button is never shown, so hide() sends nothing)
        self.assertIsNone(self.b._fx)

    def test_clicked_again_mid_way(self):
        if self.elsewhere:
            return
        with self.visible, self.effects:
            self.b.set_collapsed(True, animate=True)
            first = self.b._fx
            first.stop()
            self.b.set_collapsed(False, animate=True)
        self.b._fx.stop()
        self.assertIsNot(self.b._fx, first)
        self.assertFalse(self.b._fx._folding)
        self.assertFalse(self.b._collapsed)

    def test_only_when_asked_seen_and_wanted(self):
        if self.elsewhere:
            return
        self.b.set_collapsed(True, animate=True)  # not on the screen (the tests', or the button hidden)
        self.assertIsNone(self.b._fx)
        self.b.set_collapsed(False)
        with self.visible, mock.patch.object(foldfx, "animations_on", lambda: False):  # Windows' effects off
            self.b.set_collapsed(True, animate=True)
        self.assertIsNone(self.b._fx)
        self.assertTrue(self.b._collapsed)
        with self.visible, self.effects:
            self.b.set_collapsed(False)  # at start (main's own call)
        self.assertIsNone(self.b._fx)
        with self.visible, self.effects:  # the fold chip's click
            fold = self.b._collapse_rect().center()
            self.b.mousePressEvent(mouse(fold))
            self.b.mouseReleaseEvent(mouse(fold))
        self.assertIsNotNone(self.b._fx)
        self.assertIsInstance(foldfx.animations_on(), bool)


if __name__ == "__main__":
    unittest.main()
