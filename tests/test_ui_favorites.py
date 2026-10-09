"""The + above the panel (favorites.py, favoritesview.py, Dictation on a stub): it's there only with Claude connected
and opens its menu away from the panel, the menu offers the favourite folders that exist (by name, in their colour),
a click opens a session there (favorites.start_session replaced: no window, no Claude), "Vybrat složky…" keeps what
was switched on, and a new repo is made, becomes a favourite and gets its session.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from app import colors, config, favorites, main, ui  # noqa: E402
from app.favoritesview import FavoritesDialog, NewRepoDialog  # noqa: E402


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
        self.dir = tempfile.mkdtemp(prefix="orbit-test-fav-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.ondra, self.orbit = os.path.join(self.dir, "ondra"), os.path.join(self.dir, "orbit")
        for folder in (self.ondra, self.orbit):
            os.mkdir(folder)

    def stub(self, connected=True, folders=()):
        opened = []
        d = SimpleNamespace(cfg={"favorite_folders": list(folders), "folder_colors": {"orbit": "blue"}},
                            claude=SimpleNamespace(connected=connected), opened=opened,
                            _open_favorite=opened.append, _new_repo=lambda: opened.append("nové repo"),
                            _choose_favorites=lambda: opened.append("vybrat"),
                            open_wizard=lambda page="": opened.append(f"průvodce {page}"))
        return d

    def test_plus_only_with_claude_and_its_menu_opens_away_from_the_panel(self):
        if self.elsewhere:
            return
        button = ui.FloatingButton(lambda: 0.0)
        button.set_usage_visible(True)
        button.set_claude(False)
        self.assertIsNone(button._new_center())
        button.set_claude(True)
        plus, clock = button._new_center(), button._history_center()
        self.assertLess(plus.x(), clock.x())  # left of the history's clock
        self.assertEqual(plus.y(), clock.y())
        got = []
        button.new_session_clicked.connect(lambda at, up: got.append((at, up)))
        button._press_global = button.mapToGlobal(plus.toPoint())
        button._dragging = button._press_on_button = button._press_on_speaker = False
        button.mouseReleaseEvent(SimpleNamespace(button=lambda: Qt.LeftButton, position=lambda: QPointF(plus)))
        self.assertEqual(len(got), 1)
        at, up = got[0]
        self.assertEqual(up, not button._below)
        local = button.mapFromGlobal(at)
        self.assertTrue(local.y() > plus.y() if not up else local.y() < plus.y())

    def test_the_menu(self):
        if self.elsewhere:
            return
        menu = QMenu()
        d = self.stub(connected=False)
        main.Dictation._fill_favorites(d, menu)
        self.assertEqual([a.text() for a in menu.actions()], ["Připojit Clauda…"])
        d = self.stub(folders=[self.orbit, os.path.join(self.dir, "smazana"), self.ondra])
        main.Dictation._fill_favorites(d, menu)
        texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        self.assertEqual(texts, ["Nová relace Claude Code ve složce", "ondra", "orbit", "Nové repo…",
                                 "Vybrat složky a barvy…"])  # by name, a folder that's gone left out
        menu.actions()[2].trigger()  # orbit
        self.assertEqual(d.opened, [self.orbit])
        self.assertEqual(menu.actions()[2].data(), self.orbit)
        self.assertTrue(menu.actions()[2].toolTip().startswith(self.orbit))
        main.Dictation._fill_favorites(d, menu, heading=False)  # in Orbit's menu, under its own title
        self.assertEqual(menu.actions()[0].text(), "ondra")
        d = self.stub()
        main.Dictation._fill_favorites(d, menu)
        self.assertIn("Zatím tu žádná složka není", [a.text() for a in menu.actions()])

    def test_a_right_click_asks_for_the_colour(self):
        if self.elsewhere:
            return
        menu = ui.FolderMenu()
        d = self.stub(folders=[self.ondra])
        main.Dictation._fill_favorites(d, menu)
        asked = []
        menu.right_clicked.connect(lambda folder, at: asked.append(folder))
        ondra = next(a for a in menu.actions() if a.data() == self.ondra)
        at = menu.actionGeometry(ondra).center()

        def release(button):
            menu.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(at), QPointF(menu.mapToGlobal(at)),
                                               button, Qt.NoButton, Qt.NoModifier))
        release(Qt.RightButton)
        self.assertEqual(asked, [self.ondra])
        self.assertEqual(d.opened, [])  # not opened
        title = menu.actions()[0]  # no folder: a right click does what it always does
        release_at = menu.actionGeometry(title).center()
        menu.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(release_at),
                                           QPointF(menu.mapToGlobal(release_at)), Qt.RightButton, Qt.NoButton,
                                           Qt.NoModifier))
        self.assertEqual(asked, [self.ondra])

    def test_the_colour_menu(self):
        if self.elsewhere:
            return
        set_to, refilled = [], []
        owner = ui.FolderMenu()
        owner.addAction("ondra").setData(self.ondra)
        owner.popup(QPoint(10, 10))
        d = SimpleNamespace(cfg={"folder_colors": {"ondra": "pink"}}, favorites_menu=None,
                            _set_folder_color=lambda name, color: set_to.append((name, color)),
                            _fill_favorites=lambda menu, heading=True: refilled.append((menu, heading)))
        main.Dictation._favorite_color(d, owner, self.ondra, QPoint(20, 20))
        # over the + menu, which stays open: a popup opened in its place while Qt still handled the right click was
        # closed at once on Windows (the colours never showed; offscreen doesn't do that, so it's checked this way)
        self.assertIs(d._folder_menu.parent(), owner)
        self.assertTrue(owner.isVisible())
        actions = d._folder_menu.actions()
        self.assertEqual(actions[0].text(), "Barva složky ondra")
        self.assertTrue(next(a for a in actions if a.text() == "růžová").isChecked())
        next(a for a in actions if a.text() == "zelená").trigger()
        next(a for a in actions if a.text().startswith("Automaticky")).trigger()
        self.assertEqual(set_to, [("ondra", "green"), ("ondra", None)])
        self.assertEqual(refilled, [(owner, True), (owner, True)])  # its dot in the new colour at once
        d._folder_menu.close()
        owner.close()

    def test_a_folders_dot_changes_its_colour(self):
        if self.elsewhere:
            return
        dialog = FavoritesDialog([self.ondra], [self.orbit], {"ondra": "pink"})
        chosen = []
        dialog.color_chosen.connect(lambda folder, color: chosen.append((folder, color)))
        dots = dict(dialog._dots)
        dots[self.ondra].click()
        actions = dialog._color_menu.actions()
        self.assertEqual(actions[0].text(), "Barva složky ondra")
        next(a for a in actions if a.text() == "oranžová").trigger()
        next(a for a in actions if a.text().startswith("Automaticky")).trigger()
        self.assertEqual(chosen, [(self.ondra, "orange"), (self.ondra, "")])
        before = dots[self.ondra].icon().pixmap(16, 16).toImage().pixelColor(8, 8)
        dialog.set_colors({"ondra": "green"})  # what Orbit then saved
        after = dots[self.ondra].icon().pixmap(16, 16).toImage().pixelColor(8, 8)
        self.assertNotEqual(before, after)
        self.assertEqual(after.name().upper(), colors.accent("green").upper())
        dialog._color_menu.close()

    def test_a_click_opens_a_session_and_a_failure_says_why(self):
        if self.elsewhere:
            return
        failed, done = [], threading.Event()
        d = SimpleNamespace(bridge=SimpleNamespace(favorite_failed=SimpleNamespace(
            emit=lambda folder, text: (failed.append((folder, text)), done.set()))))
        with mock.patch.object(favorites, "start_session", return_value=(False, "Složka neexistuje.")) as start:
            main.Dictation._open_favorite(d, self.ondra)
            self.assertTrue(done.wait(5))
        start.assert_called_once_with(self.ondra)
        self.assertEqual(failed, [(self.ondra, "Složka neexistuje.")])

    def test_choosing_folders(self):
        if self.elsewhere:
            return
        dialog = FavoritesDialog([self.ondra], [self.orbit, self.ondra], {})
        self.assertEqual(dialog.folders(), [self.ondra])
        rows = dict(dialog._rows)
        rows[self.orbit].setChecked(True)
        rows[self.ondra].setChecked(False)
        extra = os.path.join(self.dir, "jina")
        os.mkdir(extra)
        dialog.include(extra)  # "Přidat složku…" (or a new repo while this is open)
        dialog.include(self.orbit.upper())  # already there: its row, not a second one
        self.assertEqual(len(dialog._rows), 3)
        saved = []
        dialog.saved.connect(saved.append)
        dialog._save()
        self.assertEqual(len(saved), 1)
        self.assertCountEqual(saved[0], [extra, self.orbit])  # (the menu orders them by name)

    def test_new_repo(self):
        if self.elsewhere:
            return
        dialog = NewRepoDialog(self.dir)
        created = []
        dialog.created.connect(lambda path, problem: created.append((path, problem)))
        dialog.name.setText("con")
        self.assertFalse(dialog.create.isEnabled())
        dialog.name.setText("ondra")  # already there
        dialog.git.setChecked(False)
        dialog._create()
        self.assertEqual(created, [])
        self.assertIn("už existuje", dialog.error.text())
        dialog.name.setText("novy")
        self.assertEqual(dialog.preview.text(), f"Vznikne {Path(self.dir) / 'novy'}")
        dialog._create()
        self.assertEqual(created, [(os.path.join(self.dir, "novy"), "")])
        self.assertTrue(os.path.isdir(created[0][0]))

    def test_a_new_repo_becomes_a_favourite_and_opens(self):
        if self.elsewhere:
            return
        self.addCleanup(lambda: config.CONFIG_PATH.unlink(missing_ok=True))
        d = self.stub(folders=[self.orbit])
        d.favorites_dialog = FavoritesDialog([self.orbit], [], {})
        d.favorites_dialog.show()
        notes = []
        d._notify = lambda text, **kw: notes.append(text)
        main.Dictation._repo_created(d, self.ondra, "")
        self.assertEqual(d.cfg["favorite_folders"], [self.orbit, self.ondra])
        self.assertEqual(config.load()["favorite_folders"], [self.orbit, self.ondra])  # saved
        self.assertEqual(d.opened, [self.ondra])
        self.assertIn(self.ondra, d.favorites_dialog.folders())  # its Uložit keeps the new one
        self.assertEqual(notes, [])
        main.Dictation._repo_created(d, self.ondra, "git tu není nainstalovaný, složka je bez gitu.")
        self.assertEqual(d.cfg["favorite_folders"], [self.orbit, self.ondra])  # still once
        self.assertEqual(len(notes), 1)
        d.favorites_dialog.close()


if __name__ == "__main__":
    unittest.main()
