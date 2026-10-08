"""The user's own tasks (app/tasks.py, the notebook window, Dictation's half-hourly offer on a stub): saved and read
back, the first active one that hasn't run is offered, a yes starts its session (tasks.start_session replaced: no
window, no Claude), a no keeps it from being offered again, and what the session gets is the user's text, cleaned.

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

    def test_inbox_from_the_tasks_session(self):
        """The orbit-ukoly mod's messages: notes go to the task, "done" moves it, junk and the unknown are dropped,
        a file still being written waits."""
        box = tasks.inbox()
        box.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, box, True)
        items = [task("Faktury"), task("Web")]
        msgs = {"1-note": {"task": items[0].id, "action": "note", "text": "Září má 48 faktur​.", "at": 100.0},
                "2-user": {"task": items[1].id, "action": "note", "text": "Volat Petrovi", "from": "user"},
                "3-done": {"task": items[0].id, "action": "done", "text": "Odesláno účetní."},
                "4-gone": {"task": "000000000000", "action": "done", "text": ""},
                "5-bad": {"task": items[0].id, "action": "delete"}}
        for name, data in msgs.items():
            (box / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        (box / "6-half.json").write_text('{"task": ', encoding="utf-8")  # the mod is still writing it
        applied = tasks.apply_inbox(items, tasks.read_inbox())
        self.assertEqual([m["action"] for _, m in applied], ["note", "note", "done"])
        self.assertEqual(items[0].status, "done")
        self.assertEqual([n["text"] for n in items[0].notes],
                         ["Claude: Září má 48 faktur.", "Claude: hotovo – Odesláno účetní."])
        self.assertEqual(items[0].notes[0]["at"], 100.0)
        self.assertEqual(items[1].notes[0]["text"], "Volat Petrovi")
        self.assertEqual([f.name for f in box.iterdir()], ["6-half.json"])
        old = time.time() - tasks.INBOX_UNREADABLE_S - 1
        os.utime(box / "6-half.json", (old, old))
        self.assertEqual(tasks.read_inbox(), [])
        self.assertEqual(list(box.iterdir()), [])

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
        self.spoken, self.notes, self.heard, self.started, self.timer = [], [], [], [], []
        self.items = [task("Plán", "planned"), task("Ceník Profod")]
        bridge = SimpleNamespace(task_done=SimpleNamespace(emit=lambda *a: self.started.append(a)))
        self.d = SimpleNamespace(
            tasks=self.items, claude=SimpleNamespace(connected=True), _confirm=None, cfg={"agent": True, "name": "Pepa"},
            confirm_timer=SimpleNamespace(start=lambda: None, stop=lambda: None), _feed={}, bridge=bridge,
            tasks_timer=SimpleNamespace(start=lambda ms: self.timer.append(ms)),
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
        self.assertEqual(start.call_args.kwargs["task_id"], self.items[1].id)  # the session's mod shows the task
        main.Dictation._task_done(self.d, *self.started[0])
        self.assertTrue(self.items[1].started)
        self.assertEqual(self.items[1].status, "done")  # its session runs: off the active ones
        self.assertEqual((tasks.load()[1].started, tasks.load()[1].status), (self.items[1].started, "done"))
        self.assertEqual(self.timer[-1], tasks.NEXT_SOON_MS)  # the next active task comes a minute later
        self.assertIsNone(self.ask())  # it ran: not offered again

    def test_no_is_not_offered_again(self):
        request = self.ask()
        self.assertEqual(self.timer, [tasks.CHECK_EVERY_MS])  # the regular half hour from here
        self.d._confirm = None
        main.Dictation._answer_task(self.d, request, False, "ne")
        self.assertTrue(self.items[1].declined)
        self.assertEqual(self.timer[-1], tasks.NEXT_SOON_MS)
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
        self.assertEqual(self.timer[-1], tasks.NEXT_SOON_MS)  # tried again a minute later

    def test_unanswered_comes_back_sooner(self):
        self.ask()
        main.Dictation._drop_confirm(self.d, "Do dvou minut nepřišlo potvrzení.")  # (what the expiry does)
        self.assertIsNone(self.d._confirm)
        self.assertEqual(self.timer[-1], tasks.RETRY_MS)
        self.assertFalse(self.items[1].declined)  # nobody said no: offered again
        self.assertEqual(self.ask()["task"], self.items[1].id)

    def test_started_before_goes_to_done(self):
        items = [task("Běží", started=5.0), task("Čeká"), task("Hotový", "done", started=3.0)]
        self.assertTrue(tasks.settle_started(items))
        self.assertEqual([t.status for t in items], ["done", "active", "done"])
        self.assertFalse(tasks.settle_started(items))


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
        items[2].started = 7.0
        nb._move_to("active")  # C to the end of Aktivní, may be offered (and started) again
        self.assertEqual([t.title for t in items if t.status == "active"], ["B", "A", "C"])
        self.assertEqual((items[2].declined, items[2].started), (0.0, 0.0))
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
