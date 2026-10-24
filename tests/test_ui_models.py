"""A running session's model (main on a stub, models.py): the right click on it offers the four models with the one it
runs on checked, a click leaves a request for its mod, its row says "→ Sonnet" until the mod answers; then the
default for new sessions goes back, a session without the 0.5 mod and one that asks in its window get a bubble, the
user's own "no" in its window doesn't. The panel names a session's model only when it isn't the default.

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

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from app import claude_settings, main, models, paths, sessions, ui  # noqa: E402

SID = "51ea50a3-e868-49b1-8cae-9116245ae611"
CATALOG = {"fable": {"id": "claude-fable-5-1", "name": "Fable 5.1"}, "opus": {"id": "claude-opus-5-5", "name": "Opus 5.5"},
           "sonnet": {"id": "claude-sonnet-5-5", "name": "Sonnet 5.5"},
           "haiku": {"id": "claude-haiku-5-5", "name": "Haiku 5.5"}}


class Models(unittest.TestCase):
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
        models._catalog = CATALOG  # what Claude Code said its aliases stand for (models.refresh_names)
        self.addCleanup(setattr, models, "_catalog", None)
        self.settings = paths.claude_dir() / "settings.json"
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.write_default("opus[1m]")
        self.addCleanup(self.settings.unlink, True)
        self.addCleanup(lambda: (paths.claude_dir() / claude_settings.BACKUP_NAME).unlink(missing_ok=True))
        shutil.rmtree(models.SWITCH_DIR, ignore_errors=True)
        self.addCleanup(shutil.rmtree, models.SWITCH_DIR, True)
        self.session = sessions.Session(SID, cwd=r"C:\Users\jana\m-tex", topic="Ceník", model="claude-opus-5-5",
                                        state="done", since=time.time() - 60, context_tokens=123_000)
        self.notes = []
        d = self.d = SimpleNamespace(tracker=SimpleNamespace(sessions={SID: self.session}), _model_switches={},
                                     polled=[])
        d._notify = lambda text, **kw: self.notes.append((text, kw.get("kind") or ("error" if kw.get("error") else
                                                                                   "info")))
        d._poll_sessions = lambda: d.polled.append(1)
        d._switch_model = lambda session_id, family: main.Dictation._switch_model(d, session_id, family)
        d._model_switch_over = lambda *a: main.Dictation._model_switch_over(d, *a)

    def write_default(self, model):
        self.settings.write_text(json.dumps({"model": model, "theme": "dark"}), encoding="utf-8")
        time.sleep(0.01)

    def watch(self):
        main.Dictation._watch_model_switches(self.d, [self.session])

    def answer(self, kind: str, record: dict):
        switch = self.d._model_switches[SID]
        (models.SWITCH_DIR / f"{SID}.{switch['id']}.{kind}.json").write_text(json.dumps(record), encoding="utf-8")

    def age(self, seconds: float):
        self.d._model_switches[SID]["at"] = time.time() - seconds

    def test_the_menu_and_a_switch(self):
        if self.elsewhere:
            return
        menu = QMenu()
        main.Dictation._fill_model_menu(self.d, menu, self.session)
        actions = menu.actions()
        self.assertEqual([a.text() for a in actions], ["Model: Opus 5.5", "Fable 5.1", "Opus 5.5",
                                                      "Sonnet 5.5", "Haiku 5.5"])
        self.assertEqual([a.isChecked() for a in actions[1:]], [False, True, False, False])
        self.assertIn("123 tis. tokenů", actions[3].toolTip())  # what switching costs
        self.assertIn("výchozí model pro nové relace zůstane", actions[3].toolTip())
        actions[3].trigger()  # Sonnet
        switch = self.d._model_switches[SID]
        self.assertEqual((switch["model"], switch["label"]), ("sonnet", "Sonnet 5.5"))
        self.assertEqual(models.request(SID, switch["id"])["default"], "opus[1m]")
        self.assertEqual(self.d.polled, [1])  # its row shows it right away
        actions[2].trigger()  # Opus, while it switches: nothing more
        self.assertEqual(len(list(models.SWITCH_DIR.glob("*.json"))), 1)
        menu = QMenu()
        main.Dictation._fill_model_menu(self.d, menu, self.session)
        self.assertEqual(menu.actions()[0].text(), "Model: Opus 5.5 → Sonnet 5.5…")
        self.assertFalse(menu.actions()[3].isEnabled())

    def test_done_puts_the_default_back(self):
        if self.elsewhere:
            return
        self.d._switch_model(SID, "sonnet")
        self.watch()
        self.assertEqual(self.session.model_switch, "Sonnet 5.5")
        self.assertEqual(ui.model_tag(self.session), "→ Sonnet 5.5")
        self.answer("ack", {})
        self.write_default("sonnet")  # what /model did in the session
        self.answer("done", {"ok": True, "text": "Set model to `Sonnet 5.5`", "model": "claude-sonnet-5-5"})
        self.watch()
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8")), {"model": "opus[1m]", "theme": "dark"})
        self.assertEqual((self.session.model, self.session.model_switch), ("claude-sonnet-5-5", ""))
        self.assertEqual(self.d._model_switches, {})
        self.assertEqual(list(models.SWITCH_DIR.iterdir()), [])
        self.assertEqual(self.notes, [])  # its row says it
        self.assertEqual(ui.model_tag(self.session), "Sonnet 5.5")  # its exact name

    def test_no_mod_no_switch(self):
        if self.elsewhere:
            return
        self.d._switch_model(SID, "haiku")
        self.watch()
        self.assertEqual(self.notes, [])
        self.assertEqual(ui.model_tag(self.session), "→ Haiku 5.5")
        self.age(models.ACK_WAIT_S + 1)
        self.watch()
        self.assertEqual(ui.model_tag(self.session), "")  # its row as before
        self.assertEqual(self.d._model_switches, {})
        self.assertEqual(list(models.SWITCH_DIR.iterdir()), [])
        self.assertEqual(len(self.notes), 1)
        self.assertIn("orbit-mozek 0.5", self.notes[0][0])
        self.assertIn("/model haiku", self.notes[0][0])

    def test_asked_in_its_window(self):
        """Taken but not through while the session is idle: without Orbit's hook it asks in its window, once."""
        if self.elsewhere:
            return
        self.d._switch_model(SID, "haiku")
        self.answer("ack", {})
        self.session.state = "working"
        self.age(models.CONFIRM_WAIT_S + 1)
        self.watch()  # it works: /model runs after its turn
        self.assertEqual(self.notes, [])
        self.session.state, self.session.since = "done", time.time() - models.CONFIRM_WAIT_S - 1
        self.watch()
        self.watch()
        self.assertEqual(len(self.notes), 1)
        self.assertIn("potvrď to v jejím okně", self.notes[0][0])
        self.answer("done", {"ok": False, "text": "Kept model as `Opus 5.5`", "model": "claude-opus-5-5"})
        self.watch()  # the user's own "no" there: no bubble
        self.assertEqual(len(self.notes), 1)
        self.assertEqual(self.d._model_switches, {})
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["model"], "opus[1m]")

    def test_refused(self):
        if self.elsewhere:
            return
        self.d._switch_model(SID, "fable")
        self.answer("ack", {})
        self.answer("done", {"ok": False, "text": "Fable 5.1 isn't available for your account yet.", "model": ""})
        self.watch()
        self.assertEqual(self.notes, [("Na Fable 5.1 se nepřepnula: Fable 5.1 isn't available for your account yet.",
                                       "error")])

    def test_the_rows(self):
        if self.elsewhere:
            return
        self.assertEqual(ui.model_tag(self.session), "")  # the default's family: nothing in the row
        before = ui.FloatingButton._sessions_look([self.session])
        self.session.model = "Haiku 5.5"
        self.assertEqual(ui.model_tag(self.session), "Haiku 5.5")
        self.assertNotEqual(ui.FloatingButton._sessions_look([self.session]), before)  # it's painted again
        self.session.model = ""
        self.assertEqual(ui.model_tag(self.session), "")
        button = ui.FloatingButton(lambda: 0.0)
        button.set_usage_visible(True)
        self.session.model = "claude-haiku-5-5"
        button.set_sessions([self.session])
        button.grab()  # paints the row with its mark


if __name__ == "__main__":
    unittest.main()
