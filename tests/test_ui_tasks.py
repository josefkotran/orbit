"""The user's own tasks (app/tasks.py, the notebook window, Dictation's half-hourly offer on a stub): saved and read
back, the first active one that hasn't run is offered, a yes starts its session (tasks.start_session replaced: no
window, no Claude), a no keeps it from being offered again, and what the session gets is the user's text, cleaned.

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
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import main, tasks  # noqa: E402

FOLDER = r"C:\Users\josef\m-tex"


def task(title, status="active", folder=FOLDER, **kw):
    t = tasks.new(title, status)
    t.folder = folder
    for k, v in kw.items():
        setattr(t, k, v)
    return t


class Store(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: tasks.path().unlink(missing_ok=True))

    def test_saved_and_read_back(self):
        items = [task("Ceník", notes=[{"at": 1.0, "text": "Pozor na DPH"}]), task("Web", "planned", "")]
        tasks.save(items)
        self.assertEqual(tasks.load(), items)

    def test_a_broken_file_is_kept_aside(self):
        tasks.path().parent.mkdir(parents=True, exist_ok=True)
        tasks.path().write_text("{nedopsané", encoding="utf-8")
        self.assertEqual(tasks.load(), [])
        backups = list(tasks.path().parent.glob("tasks.json.bad-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{nedopsané")
        backups[0].unlink()

    def test_next_to_offer(self):
        items = [task("Plán", "planned"), task("Bez složky", folder=""), task("Běží", started=1.0),
                 task("Odmítnutý", declined=1.0), task("Tenhle"), task("Až potom")]
        self.assertEqual(tasks.next_to_offer(items).title, "Tenhle")

    def test_prompt_is_the_users_text_cleaned(self):
        t = task("Ceník Profod", context="Viz [ceník](https://profod.cz/c.pdf) a\u200b (hlasem přes Orbit) tabulku.",
                 notes=[{"at": time.time(), "text": "Bez DPH"}])
        prompt = tasks.prompt_for(t)
        self.assertTrue(prompt.startswith("Úkol: Ceník Profod. Kontext: Viz ceník (https://profod.cz/c.pdf)"))
        self.assertIn("Bez DPH", prompt)
        self.assertNotIn("\u200b", prompt)
        self.assertNotIn("hlasem přes orbit", prompt.lower())

    def test_a_long_task_goes_as_a_file(self):
        t = task("Dlouhý", context="slovo " * 2000)
        prompt = tasks.prompt_for(t)
        self.assertLess(len(prompt), 400)
        file = tasks.config.DATA_DIR / "tasks" / f"{t.id}.md"
        self.assertIn(str(file), prompt)
        self.assertIn("slovo slovo", file.read_text(encoding="utf-8"))


class Offer(unittest.TestCase):
    """Dictation._check_tasks / _answer_task / _task_done on a stub."""

    def setUp(self):
        self.spoken, self.notes, self.heard, self.started = [], [], [], []
        self.items = [task("Plán", "planned"), task("Ceník Profod")]
        bridge = SimpleNamespace(task_done=SimpleNamespace(emit=lambda *a: self.started.append(a)))
        self.d = SimpleNamespace(
            tasks=self.items, claude=SimpleNamespace(connected=True), _confirm=None, cfg={"agent": True, "name": "Pepa"},
            confirm_timer=SimpleNamespace(start=lambda: None, stop=lambda: None), _feed={}, bridge=bridge,
            _feed_update=lambda **k: self.d._feed.update({x: v for x, v in k.items() if v}),
            _set_agent_state=lambda s: None, _agent_rest=lambda: "idle", notebook=None,
            _speak=lambda text, **k: self.spoken.append(text), _agent_heard=lambda text: self.heard.append(text),
            _notify=lambda msg, **k: self.notes.append((msg, k)), _tasks_changed=lambda: None)
        self.d._answer_task = lambda *a: main.Dictation._answer_task(self.d, *a)
        self.d._save_tasks = lambda: main.Dictation._save_tasks(self.d)
        self.d._task_clicked = lambda confirm_id: main.Dictation._task_clicked(self.d, confirm_id)
        for name, value in (("known_folder", lambda f: f), ("folder_label", lambda f: Path(f).name)):
            patch = mock.patch.object(main.agent, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(lambda: tasks.path().unlink(missing_ok=True))

    def ask(self):
        main.Dictation._check_tasks(self.d)
        return self.d._confirm

    def test_yes_by_click_starts_its_session(self):
        request = self.ask()
        self.assertEqual(request["kind"], "task")
        self.assertIn("Ceník Profod", self.spoken[-1])
        self.assertIn("m-tex", self.spoken[-1])
        click = self.notes[-1][1]["on_click"]
        with mock.patch.object(main.tasks, "start_session", return_value=(True, "Otevřeno.")) as start:
            click()
            for _ in range(100):  # (a thread)
                if self.started:
                    break
                time.sleep(0.01)
        self.assertEqual(start.call_args.args[0], FOLDER)
        self.assertTrue(start.call_args.args[1].startswith("Úkol: Ceník Profod."))
        self.assertEqual(start.call_args.args[2], "Pepa")
        main.Dictation._task_done(self.d, *self.started[0])
        self.assertTrue(self.items[1].started)
        self.assertEqual(tasks.load()[1].started, self.items[1].started)
        self.assertIsNone(self.ask())  # it ran: not offered again

    def test_no_is_not_offered_again(self):
        request = self.ask()
        self.d._confirm = None
        main.Dictation._answer_task(self.d, request, False, "ne")
        self.assertTrue(self.items[1].declined)
        self.assertIsNone(self.ask())
        main.Dictation._check_tasks(self.d, self.items[1].id)  # "Začít teď" asks anyway
        self.assertIsNotNone(self.d._confirm)

    def test_something_else_goes_to_the_agent(self):
        request = self.ask()
        self.d._confirm = None
        main.Dictation._answer_task(self.d, request, None, "a co dělá m-tex?")
        self.assertFalse(self.items[1].declined)
        self.assertEqual(self.heard, ["a co dělá m-tex?"])

    def test_not_while_another_question_waits(self):
        self.d._confirm = {"id": "c1", "kind": "agent"}
        main.Dictation._check_tasks(self.d)
        self.assertEqual(self.d._confirm["id"], "c1")
        self.assertEqual(self.spoken, [])


class NotebookWindow(unittest.TestCase):
    def test_moves_and_order(self):
        app = QApplication.instance()
        if app is not None and not isinstance(app, QApplication):  # another test's QGuiApplication: a window
            # needs a QApplication, so this one runs in a process of its own
            run = subprocess.run([sys.executable, "-m", "unittest", f"{__name__}.NotebookWindow.test_moves_and_order"],
                                 cwd=Path(__file__).parent, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            return
        app or QApplication([])
        from app.notebook import Notebook
        self.addCleanup(lambda: tasks.path().unlink(missing_ok=True))
        items = [task("A"), task("B"), task("C", "planned", declined=5.0)]
        nb = Notebook(items, [FOLDER], {}, lambda: "10:30")
        nb.refresh(items[1].id)
        nb._shift(-1)  # B above A
        self.assertEqual([t.title for t in items if t.status == "active"], ["B", "A"])
        nb.refresh(items[2].id)
        nb._move_to("active")  # C to the end of Aktivní, may be offered again
        self.assertEqual([t.title for t in items if t.status == "active"], ["B", "A", "C"])
        self.assertEqual(items[2].declined, 0.0)
        nb.note.setText("Volat ve čtvrtek")
        nb._add_note()
        self.assertEqual(items[2].notes[-1]["text"], "Volat ve čtvrtek")
        # a drag: the tree's order and sections become the tasks'
        active, planned = nb.tree.topLevelItem(0), nb.tree.topLevelItem(1)
        planned.addChild(active.takeChild(0))  # B into V plánu
        nb._dropped()
        self.assertEqual([(t.title, t.status) for t in items], [("A", "active"), ("C", "active"), ("B", "planned")])
        self.assertEqual([t.title for t in tasks.load()], ["A", "C", "B"])
        nb._add()
        self.assertEqual((items[0].status, items[0].title), ("note", ""))


if __name__ == "__main__":
    unittest.main()
