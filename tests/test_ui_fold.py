"""Orbit folded into its icon (13 Oct, Pepa: "celé to okno … se bude dát minimalizovat a bude to jenom jako ikonka
Orbitu … podle toho, kde to mám umístěné; když na tu ikonku kliknu, tak se to celý zase rozbalí"): the fold button
in the panel's top right corner, the icon in the mic's square (the saved place doesn't move), a click unfolds, a
press is never push-to-talk, a drag moves it; Dictation saves it (on a stub).

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
from unittest import mock

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import config, main, ui  # noqa: E402


def mouse(at: QPointF, button=Qt.LeftButton, origin: QPoint = QPoint()):
    """A mouse event at a point of the widget (origin: where the widget is, for the global position)."""
    return SimpleNamespace(button=lambda: button, position=lambda: QPointF(at),
                           globalPosition=lambda: QPointF(at) + QPointF(origin))


class Fold(unittest.TestCase):
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
        self.b._auto_align = lambda: None  # (it goes by where the button is on the screen) the panel above, right
        self.b.set_claude(True)
        self.b.set_usage_visible(True)
        self.b.set_claude_version({"installed": "2.1.296", "latest": "2.1.296", "state": "current", "target": "",
                                   "tip": ""})
        self.b._align, self.b._below = "right", False
        self.b._relayout()
        self.b.place_button(QPoint(900, 500))
        self.b.set_state("idle")
        self.got = []
        for name in ("pressed", "released", "collapse_toggled", "moved", "menu_requested"):
            getattr(self.b, name).connect(lambda *a, name=name: self.got.append((name, *a)))

    def click(self, at: QPointF):
        self.b.mousePressEvent(mouse(at))
        self.b.mouseReleaseEvent(mouse(at))

    def test_the_fold_button_folds_into_the_icon_where_the_mic_is(self):
        if self.elsewhere:
            return
        mic = self.b.mapToGlobal(self.b._button_center().toPoint())
        place, size = self.b.button_pos(), self.b.size()
        fold = self.b._collapse_rect()
        self.click(fold.center())
        self.assertEqual(self.got, [("collapse_toggled", True)])
        self.assertEqual(self.b.size().width(), self.b._side)
        self.assertEqual(self.b.size().height(), self.b._side)
        self.assertEqual(self.b.button_pos(), place)  # the saved place stays
        self.assertEqual(self.b.mapToGlobal(self.b._button_center().toPoint()), mic)  # the icon sits on the mic
        anchor, panel = self.b.bubble_anchor()
        self.assertEqual((anchor.width(), panel), (self.b.ICON_D, None))
        self.assertEqual((self.b._dots(), self.b._version_layout()[0].isEmpty(), self.b._collapse_rect().isEmpty()),
                         ([], True, True))
        self.click(QPointF(self.b._side / 2, self.b._side / 2))  # a click on the icon unfolds it all
        self.assertEqual(self.got[-1], ("collapse_toggled", False))
        self.assertEqual((self.b.size(), self.b.button_pos()), (size, place))

    def test_its_own_chip_right_of_the_colours(self):
        """Pepa, 13 Oct: "dej to vedle barev, ale samostatná bublinka, barvy posuň doleva" (in 1.2.0 a thin grey dash
        in the panel's header read as punctuation after the countdown and wasn't found)."""
        if self.elsewhere:
            return
        fold, panel, dots = self.b._collapse_rect(), self.b._panel, self.b._dots()
        self.assertLessEqual(fold.bottom(), panel.top())  # in the strip above the panel, not in it
        self.assertLessEqual(panel.right() - fold.right(), 3)  # at its right end
        self.assertEqual(fold.center().y(), dots[0][1].y())
        pill_right = dots[-1][1].x() + self.b.PILL_H / 2
        self.assertLess(pill_right, fold.left())  # the colours moved left of it
        chips = [self.b._agent_center(), self.b._history_center(), self.b._new_center()]
        for c in [c for c in chips if c is not None]:
            self.assertLess(c.x() + self.b.AGENT_D / 2, dots[0][1].x())  # and the chips with them, nothing overlaps
        image = self.b.grab().toImage()
        dash = image.pixelColor(fold.center().toPoint())
        chip = image.pixelColor(QPointF(fold.left() + 6, fold.center().y()).toPoint())
        self.assertGreater(dash.lightness(), 190)  # the white dash
        self.assertGreater(chip.alpha(), 200)  # on the chip's own disc
        self.b.set_agent(True)
        self.assertLess(self.b._agent_center().x() + self.b.AGENT_D / 2, dots[0][1].x())

    def test_a_press_on_the_icon_is_never_push_to_talk(self):
        if self.elsewhere:
            return
        self.b.set_collapsed(True)
        center = QPointF(self.b._side / 2, self.b._side / 2)
        self.b.mousePressEvent(mouse(center))
        self.assertEqual(self.got, [])
        self.b.mouseReleaseEvent(mouse(center))
        self.assertEqual(self.got, [("collapse_toggled", False)])

    def test_dragged_it_moves_and_stays_folded(self):
        if self.elsewhere:
            return
        self.b.set_collapsed(True)
        start, origin = QPointF(36, 36), self.b.pos()
        self.b.mousePressEvent(mouse(start, origin=origin))
        with mock.patch.object(self.b, "move") as move:
            self.b.mouseMoveEvent(mouse(start + QPointF(40, -30), origin=origin))
        self.b.mouseReleaseEvent(mouse(start + QPointF(40, -30), origin=origin))
        move.assert_called_with(origin + QPoint(40, -30))
        self.assertEqual([g[0] for g in self.got], ["moved"])
        self.assertTrue(self.b._collapsed)

    def test_folded_right_click_is_orbits_menu(self):
        if self.elsewhere:
            return
        self.b.set_collapsed(True)
        self.b.mousePressEvent(mouse(QPointF(36, 36), Qt.RightButton))
        self.assertEqual([g[0] for g in self.got], ["menu_requested"])

    def test_painted_folded(self):
        if self.elsewhere:
            return
        self.b.set_collapsed(True)
        self.assertTrue(self.b._speaker_area().isEmpty())  # the speaker's repaints don't reach into the icon
        image = self.b.grab().toImage()
        self.assertEqual(image.pixelColor(2, 36).alpha(), 0)  # outside the icon: see-through
        self.assertGreater(image.pixelColor(36, 22).alpha(), 200)
        self.b.set_state("recording")
        red = self.b.grab().toImage().pixelColor(22, 36)  # the icon's left edge: red while it listens
        self.assertGreater(red.red(), 180)
        self.assertLess(red.green(), 120)


class Saved(unittest.TestCase):
    """Dictation._set_collapsed on a stub: config, the menu's check mark, the button."""

    def test_saved_and_in_sync(self):
        saved, shown, checks = [], [], []
        action = SimpleNamespace(isChecked=lambda: bool(checks and checks[-1]), setChecked=checks.append)
        d = SimpleNamespace(cfg={"collapsed": False}, collapse_action=action,
                            button=SimpleNamespace(set_collapsed=lambda on, animate=False: shown.append((on, animate))))
        with mock.patch.object(config, "save", side_effect=lambda cfg: saved.append(dict(cfg))):
            main.Dictation._set_collapsed(d, True)
            main.Dictation._set_collapsed(d, True)  # the menu's toggled after the button's click: nothing new saved
        # the menu's fold is animated too (the button's own click already was, the second call changes nothing)
        self.assertEqual((len(saved), saved[0]["collapsed"], checks, shown),
                         (1, True, [True], [(True, True), (True, True)]))
        self.assertIs(config.DEFAULTS["collapsed"], False)


if __name__ == "__main__":
    unittest.main()
