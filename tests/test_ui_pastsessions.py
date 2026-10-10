"""The session history (the clock above the panel, app/pastsessionsview.py, Dictation on a stub): the clock is there
only with Claude connected and opens the history; the window lists past sessions newest first, finds them by words
without diacritics and by folder, and "Pokračovat" resumes the chosen one in its folder (favorites.start_session
replaced: no window, no Claude), while one that runs right now gets its window to the front instead. Transcripts are
written to a temporary Claude Code folder.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import favorites, main, pastsessions, sessions, ui  # noqa: E402
from app.pastsessionsview import SessionHistory  # noqa: E402

IDS = [f"{n:08x}-0000-4000-8000-000000000000" for n in range(1, 10)]


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
        self.dir = Path(tempfile.mkdtemp(prefix="orbit-test-past-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        patch = mock.patch.object(pastsessions.paths, "claude_dir", return_value=self.dir)
        patch.start()
        self.addCleanup(patch.stop)
        self.mtex, self.orbit = str(self.dir / "m-tex"), str(self.dir / "orbit")
        for folder in (self.mtex, self.orbit):
            os.mkdir(folder)

    def write(self, session_id: str, cwd: str, prompt: str, title: str = "", age: float = 0.0) -> None:
        project = self.dir / "projects" / Path(cwd).name
        project.mkdir(parents=True, exist_ok=True)
        entries = [{"type": "user", "message": {"role": "user", "content": prompt}, "cwd": cwd,
                    "entrypoint": "cli", "timestamp": "2026-10-08T12:00:00.000Z", "gitBranch": "main"},
                   {"type": "assistant", "message": {"role": "assistant", "content": []}, "cwd": cwd}]
        if title:
            entries.append({"type": "ai-title", "aiTitle": title})
        path = project / f"{session_id}.jsonl"
        path.write_text("".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in entries),
                        encoding="utf-8")
        when = time.time() - age
        os.utime(path, (when, when))

    def window(self, running=()) -> SessionHistory:
        self.write(IDS[0], self.mtex, "Uprav ceník Profodu", "Ceník Profodu", age=60)
        self.write(IDS[1], self.orbit, "Historie relací místo diktátů", age=10)
        self.write(IDS[2], self.mtex, "Objednávka 82", "Objednávka Worlíčka", age=3600)
        index = pastsessions.Index()
        window = SessionHistory(index, lambda: {"m-tex": "orange"}, lambda: set(running))
        self.addCleanup(window.close)
        window._got(index.scan())  # (what reload's thread brings)
        return window

    def rows(self, window) -> list[str]:
        return [window.shown[window.list.item(i).data(Qt.UserRole)].name for i in range(window.list.count())]

    def test_the_clock_only_with_claude_and_it_opens_the_history(self):
        if self.elsewhere:
            return
        button = ui.FloatingButton(lambda: 0.0)
        button.set_usage_visible(True)
        button.set_claude(False)
        self.assertIsNone(button._history_center())
        button.set_claude(True)
        clock = button._history_center()
        got = []
        button.sessions_history_clicked.connect(lambda: got.append(True))
        button._press_global = button.mapToGlobal(clock.toPoint())
        button._dragging = button._press_on_button = button._press_on_speaker = False
        button.mouseReleaseEvent(SimpleNamespace(button=lambda: Qt.LeftButton, position=lambda: QPointF(clock)))
        self.assertEqual(got, [True])

    def test_the_dictation_history_next_to_the_notebook(self):
        if self.elsewhere:
            return
        button = ui.FloatingButton(lambda: 0.0)
        button.set_usage_visible(True)
        button.set_claude(False)  # it needs no Claude
        notes, bubble = button._notes_center(), button._dictations_center()
        self.assertEqual(bubble.y(), notes.y())
        self.assertGreater(bubble.x() - notes.x(), button.AGENT_D)  # beside it, not over it
        button.set_claude(True)
        button.set_agent(True)  # the right side at its fullest: dots, agent, clock, +
        self.assertLess(bubble.x() + button.AGENT_D, button._new_center().x())  # well left of the +
        got = []
        button.dictation_history_clicked.connect(lambda: got.append("diktáty"))
        button.notes_clicked.connect(lambda: got.append("poznámky"))
        for at in (bubble, notes):
            button._press_global = button.mapToGlobal(at.toPoint())
            button._dragging = button._press_on_button = button._press_on_speaker = False
            button.mouseReleaseEvent(SimpleNamespace(button=lambda: Qt.LeftButton, position=lambda at=at: QPointF(at)))
        self.assertEqual(got, ["diktáty", "poznámky"])

    def test_lists_finds_and_filters(self):
        if self.elsewhere:
            return
        window = self.window()
        self.assertEqual(self.rows(window), ["Historie relací místo diktátů", "Ceník Profodu", "Objednávka Worlíčka"])
        self.assertEqual(window._current.id, IDS[1])  # the newest is chosen
        self.assertTrue(window.count.text().startswith("3 relace."))
        window.search.setText("cenik profod")
        self.assertEqual(self.rows(window), ["Ceník Profodu"])
        self.assertEqual(window.title.text(), "Ceník Profodu")
        self.assertEqual(window.first.toPlainText(), "Uprav ceník Profodu")
        self.assertIn("Nalezeno: 1 z 3", window.count.text())
        window.search.setText("")
        window.folder.setCurrentIndex(window.folder.findData(os.path.normcase(self.mtex)))
        self.assertEqual(window.folder.currentText(), "m-tex (2)")
        self.assertEqual(self.rows(window), ["Ceník Profodu", "Objednávka Worlíčka"])
        window.search.setText("neexistuje")
        self.assertFalse(window.detail.isVisible() and window.list.count())
        self.assertEqual(window.empty.text(), "Nic takového tu není.")

    def test_resume_or_its_window(self):
        if self.elsewhere:
            return
        window = self.window(running={IDS[1]})
        self.assertEqual(window.resume.text(), "Přepnout do relace")  # the newest one runs
        asked = []
        window.resume_requested.connect(asked.append)
        window.list.setCurrentRow(1)
        self.assertEqual(window.resume.text(), "Pokračovat v relaci")
        window.resume.click()
        window.list.itemActivated.emit(window.list.currentItem())  # a double click or Enter
        self.assertEqual(asked, [IDS[0], IDS[0]])

        resumed, done = [], threading.Event()
        said = []
        d = SimpleNamespace(past_sessions=window.index, past_window=SimpleNamespace(say=lambda t, warn=False:
                                                                                      said.append((t, warn))),
                            tracker=SimpleNamespace(sessions={}),
                            bridge=SimpleNamespace(past_resumed=SimpleNamespace(
                                emit=lambda *a: (resumed.append(a), done.set()))))
        with mock.patch.object(sessions, "running_ids", return_value={IDS[1]}), \
                mock.patch.object(favorites, "start_session", return_value=(True, "Relace pokračuje.")) as start:
            main.Dictation._resume_past(d, IDS[0])
            self.assertTrue(done.wait(5))
            start.assert_called_once_with(self.mtex, resume=IDS[0])
            self.assertEqual(resumed, [(IDS[0], True, "Relace pokračuje.")])
            focused = mock.patch.object(sessions, "focus", return_value=True)
            with focused as focus:
                d.tracker.sessions[IDS[1]] = SimpleNamespace(hwnd=42, folder="orbit")
                main.Dictation._resume_past(d, IDS[1])  # runs: its window, not a second copy
                focus.assert_called_once()
            start.assert_called_once()
            d.tracker.sessions.clear()
            main.Dictation._resume_past(d, IDS[1])  # runs, its window isn't known
            start.assert_called_once()
        self.assertEqual(said[-1][1], True)
        self.assertIn("už běží", said[-1][0])


if __name__ == "__main__":
    unittest.main()
