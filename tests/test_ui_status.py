"""What Orbit is busy with, in words next to the circles (24 Oct, Pepa: the orange mic is fine, "ale chápu, že to
někomu nemusí docvaknout"): "Přepisuji…" / "Claude kontroluje přepis…" in a small pill beside the circles, on the
side facing the screen's middle, only after a moment (a quick transcription shows nothing), under a bubble's card,
going with the circles and away with them.

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

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRectF  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import ui  # noqa: E402

SHOWN = ui.StatusChip.DELAY_MS + 250  # its delay and its fade


class Status(unittest.TestCase):
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
        self.geo = QGuiApplication.primaryScreen().availableGeometry()
        self.b = ui.FloatingButton(lambda: 0.0)
        self.b.place_button(self.geo.topLeft() + QPoint(self.geo.width() - 140, self.geo.height() - 120))
        self.b.set_state("busy")
        self.b.show()
        self.chip = self.b._status

    def tearDown(self):
        if not self.elsewhere:
            self.b.hide()
            self.b.close()
            self.chip.close()

    def pill(self):
        """The pill on the screen (without its shadow)."""
        s = self.chip.SHADOW
        return self.chip.geometry().adjusted(s, s, -s, -s)

    def test_the_words_come_after_a_moment_beside_the_circles(self):
        if self.elsewhere:
            return
        self.b.set_status("Přepisuji…")
        self.assertFalse(self.chip.isVisible())  # a quick transcription shows nothing
        QTest.qWait(SHOWN)
        self.assertTrue(self.chip.isVisible())
        self.assertEqual(self.chip.text, "Přepisuji…")
        circles = self.b.bubble_anchor()[0]
        pill = self.pill()
        self.assertLessEqual(abs(pill.center().y() - circles.center().y()), 1)
        self.assertLess(pill.right(), circles.left())  # the button is right of the middle: the words left of it
        self.b.place_button(self.geo.topLeft() + QPoint(60, self.geo.height() - 120))
        circles, pill = self.b.bubble_anchor()[0], self.pill()
        self.assertGreater(pill.left(), circles.right())  # left of the middle: right of it, and it went with it
        self.assertLessEqual(abs(pill.center().y() - circles.center().y()), 1)

    def test_the_phase_changes_in_place(self):
        if self.elsewhere:
            return
        self.b.set_status("Přepisuji…")
        QTest.qWait(SHOWN)
        self.b.set_status("Claude kontroluje přepis…")
        self.assertEqual(self.chip.text, "Claude kontroluje přepis…")  # at once, no new delay
        self.assertTrue(self.chip.isVisible())
        self.assertLess(self.pill().right(), self.b.bubble_anchor()[0].left())  # wider, still clear of the circles

    def test_a_quick_one_shows_nothing_and_done_hides_it(self):
        if self.elsewhere:
            return
        self.b.set_status("Přepisuji…")
        QTest.qWait(ui.StatusChip.DELAY_MS // 3)
        self.b.set_status("")
        QTest.qWait(SHOWN)
        self.assertFalse(self.chip.isVisible())
        self.b.set_status("Přepisuji…")
        QTest.qWait(SHOWN)
        self.b.set_status("")
        QTest.qWait(400)
        self.assertFalse(self.chip.isVisible())

    def test_it_goes_with_the_button_and_comes_back_with_it(self):
        if self.elsewhere:
            return
        self.b.set_status("Přepisuji…")
        QTest.qWait(SHOWN)
        self.b.hide()
        QTest.qWait(400)
        self.assertFalse(self.chip.isVisible())
        self.b.show()
        QTest.qWait(SHOWN)
        self.assertTrue(self.chip.isVisible())

    def test_folded_it_is_beside_the_icon(self):
        if self.elsewhere:
            return
        self.b.set_collapsed(True)
        self.b.set_status("Přepisuji…")
        QTest.qWait(SHOWN)
        icon, pill = self.b.bubble_anchor()[0], self.pill()
        self.assertEqual(icon.width(), self.b.ICON_D)
        self.assertLess(pill.right(), icon.left())
        self.assertLessEqual(abs(pill.center().y() - icon.center().y()), 1)

    def test_a_bubble_covers_it(self):
        if self.elsewhere:
            return
        bubble = ui.Bubble("done", "Kontrola přepisu", "Opraveno: Pouští → Pushni. Klikni sem a vrátím původní.")
        bubble.show_near(*self.b.bubble_anchor())
        self.b.set_status("Claude kontroluje přepis…")  # it comes while the bubble is up: the bubble stays on top
        QTest.qWait(SHOWN + 200)  # (the bubble's slide too)
        card = bubble._card().translated(bubble.geometry().topLeft())
        self.assertTrue(card.contains(QRectF(self.pill())), (card, self.pill()))
        bubble.close()


if __name__ == "__main__":
    unittest.main()
