"""Claude Code's version and its update (13 Oct, Pepa: "něco, co by ukazovalo aktuální verzi Claude Code a jestli
není potřeba update, a tlačítko na automatický update"): versions compared as Claude Code compares them, the newest
one asked where Claude Code itself asks (npm's dist-tag for an npm install, Anthropic's release file otherwise, the
channel from settings.json), `claude update` told apart by `claude --version` before and after, the connection's
check and update in worker threads, the settings' Claude box, the menu item and the pill between the panel and
the circles (Pepa, 13 Oct: "ať je pořád napsána verze", with the update right there). No claude.exe and no network:
_run, urlopen, release and update are replaced.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
import io
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

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import claude_setup, main, onboarding, paths, theme, ui  # noqa: E402

NPM_EXE = r"C:\Users\x\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
NATIVE_EXE = r"C:\Users\x\.local\bin\claude.exe"
OK = claude_setup.Status(installed=True, exe=NPM_EXE, version="2.1.290", logged_in=True, method="claude.ai")


class InQt(unittest.TestCase):
    """Widgets need a QApplication: after another test's QGuiApplication the test runs in a process of its own."""

    def setUp(self):
        self.elsewhere = False
        existing = QApplication.instance()
        if existing is not None and not isinstance(existing, QApplication):
            run = subprocess.run([sys.executable, "-m", "unittest", self.id().removeprefix("tests.")],
                                 cwd=Path(__file__).parent, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            self.elsewhere = True
            return
        self.app = existing or QApplication([])


def response(body: str):
    return mock.MagicMock(__enter__=lambda self: io.BytesIO(body.encode()), __exit__=lambda *a: False)


class Versions(unittest.TestCase):
    def test_older(self):
        self.assertTrue(claude_setup.older("2.1.290", "2.1.296"))
        self.assertTrue(claude_setup.older("2.1.9", "2.1.10"))  # numbers, not text
        self.assertTrue(claude_setup.older("2.1.296-beta.1", "2.1.296"))
        self.assertFalse(claude_setup.older("2.1.296", "2.1.296"))
        self.assertFalse(claude_setup.older("2.1.296+fdb6c17", "2.1.296"))  # a build suffix doesn't count
        self.assertFalse(claude_setup.older("2.1.1000", "2.1.999"))
        self.assertFalse(claude_setup.older("", "2.1.296"))
        self.assertFalse(claude_setup.older("2.1.290", "<script>"))

    def test_install_kind(self):
        self.assertEqual(claude_setup.install_kind(NPM_EXE), "npm")
        self.assertEqual(claude_setup.install_kind(NATIVE_EXE), "native")
        self.assertEqual(claude_setup.install_kind(r"C:\Users\x\AppData\Local\Microsoft\WinGet\Links\claude.exe"),
                         "winget")

    def test_stale_sessions_in_czech(self):
        self.assertEqual(claude_setup.stale_sessions_text([]), "")
        self.assertTrue(claude_setup.stale_sessions_text(["2.1.290"]).startswith(
            "Jedna běžící relace jede ještě na 2.1.290. Nová verze se v ní projeví, až ji zavřeš"))
        self.assertTrue(claude_setup.stale_sessions_text(["2.1.290", "2.1.288", "2.1.290"]).startswith(
            "3 běžící relace jedou ještě na 2.1.288 až 2.1.290. Nová verze se v nich projeví, až je zavřeš"))
        self.assertTrue(claude_setup.stale_sessions_text(["2.1.290"] * 5).startswith("5 běžících relací jede"))


class Latest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="orbit-test-claude-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        patches = [mock.patch.object(paths, "claude_dir", return_value=self.folder),
                   mock.patch.object(paths, "claude_json", return_value=self.folder / ".claude.json"),
                   mock.patch.dict(os.environ, {}, clear=False)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        for name in ("DISABLE_AUTOUPDATER", "DISABLE_UPDATES", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"):
            os.environ.pop(name, None)
        self.urls = []

    def settings(self, **values):
        (self.folder / "settings.json").write_text(json.dumps(values), encoding="utf-8")

    def urlopen(self, body):
        def fake(request, timeout):
            self.urls.append(request.full_url)
            return response(body)
        return mock.patch("urllib.request.urlopen", side_effect=fake)

    def release(self, exe=NPM_EXE, body='{"name": "@anthropic-ai/claude-code", "version": "2.1.296"}'):
        with self.urlopen(body), mock.patch.object(claude_setup, "version", return_value="2.1.290"):
            return claude_setup.release(exe)

    def test_npm_asks_npms_tag_of_the_channel(self):
        self.settings(autoUpdatesChannel="stable")
        r = self.release()
        self.assertEqual(self.urls, ["https://registry.npmjs.org/@anthropic-ai/claude-code/stable"])
        self.assertEqual((r.installed, r.latest, r.channel, r.kind, r.behind), ("2.1.290", "2.1.296", "stable",
                                                                               "npm", True))

    def test_native_asks_anthropics_release_file(self):
        r = self.release(NATIVE_EXE, "2.1.296\n")
        self.assertEqual(self.urls, ["https://downloads.claude.ai/claude-code-releases/latest"])
        self.assertEqual((r.latest, r.behind), ("2.1.296", True))

    def test_an_unknown_channel_never_goes_into_the_url(self):
        self.settings(autoUpdatesChannel="../../evil")
        self.release()
        self.assertEqual(self.urls, ["https://registry.npmjs.org/@anthropic-ai/claude-code/latest"])

    def test_anything_but_a_version_is_refused(self):
        r = self.release(NATIVE_EXE, "<html>Something went wrong</html>")
        self.assertEqual((r.latest, r.behind), ("", False))
        self.assertEqual(r.error, "Novou verzi teď nejde zjistit.")

    def test_offline(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("no network")), \
                mock.patch.object(claude_setup, "version", return_value="2.1.290"):
            r = claude_setup.release(NPM_EXE)
        self.assertEqual((r.installed, r.latest, r.error), ("2.1.290", "", "Novou verzi teď nejde zjistit."))

    def test_nonessential_traffic_off_asks_nothing(self):
        self.settings(env={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
        r = self.release()
        self.assertEqual(self.urls, [])
        self.assertEqual(r.latest, "")
        self.assertIn("nezjišťuju", r.error)

    def test_auto_updates(self):
        self.assertTrue(self.release().auto_updates)
        (self.folder / ".claude.json").write_text('{"autoUpdates": false}', encoding="utf-8")
        self.assertFalse(self.release().auto_updates)
        (self.folder / ".claude.json").write_text('{"autoUpdates": false, "autoUpdatesProtectedForNative": true}',
                                                  encoding="utf-8")
        self.assertTrue(self.release(NATIVE_EXE, "2.1.296").auto_updates)
        (self.folder / ".claude.json").write_text("{}", encoding="utf-8")
        self.settings(env={"DISABLE_AUTOUPDATER": "1"})
        self.assertFalse(self.release().auto_updates)


class Update(unittest.TestCase):
    def run_update(self, out="", err="", code=0, after="2.1.296", raises=None):
        versions = iter(["2.1.290", after])
        calls = []

        def run(args, timeout):
            calls.append(args)
            if raises:
                raise raises
            return subprocess.CompletedProcess(args, code, out, err)

        with mock.patch.object(claude_setup, "version", side_effect=lambda exe: next(versions)), \
                mock.patch.object(claude_setup, "_run", side_effect=run):
            result = claude_setup.update(NPM_EXE)
        self.assertEqual(calls, [[NPM_EXE, "update"]])
        return result

    def test_updated(self):
        r = self.run_update("Current version: 2.1.290\nChecking for updates...\n"
                            "\x1b[32mSuccessfully updated from 2.1.290 to version 2.1.296\x1b[39m\n")
        self.assertEqual((r.ok, r.before, r.after), (True, "2.1.290", "2.1.296"))
        self.assertEqual(r.text, "Claude Code je aktualizovaný: 2.1.290 → 2.1.296.")

    def test_already_up_to_date(self):
        r = self.run_update("Claude Code is up to date (2.1.290)\n", after="2.1.290")
        self.assertTrue(r.ok)
        self.assertIn("nebylo co aktualizovat", r.text)

    def test_exe_in_use(self):
        r = self.run_update(err="Error: Update failed because claude.exe is in use. Close other Claude Code sessions "
                                "(including VS Code), then run claude update again, or run claude doctor.\n",
                            code=1, after="2.1.290")
        self.assertFalse(r.ok)
        self.assertTrue(r.text.startswith("Soubor claude.exe drží jiný program."))

    def test_another_update_running_says_so_even_with_code_0(self):
        r = self.run_update("Another Claude process (PID 1234) is currently running. Please try again in a moment.\n",
                            after="2.1.290")
        self.assertFalse(r.ok)
        self.assertIn("aktualizuje jinde", r.text)

    def test_something_else_shows_its_last_line(self):
        r = self.run_update(err="npm ERR! code EBUSY\nnpm ERR! resource busy or locked\n", code=1, after="2.1.290")
        self.assertEqual((r.ok, r.text), (False, "Aktualizace se nepovedla: npm ERR! resource busy or locked"))

    def test_too_long(self):
        r = self.run_update(raises=subprocess.TimeoutExpired("claude", 600), after="2.1.290")
        self.assertEqual((r.ok, r.text), (False, "Aktualizace neskončila ani za 10 minut."))

    def test_the_new_version_counts_even_with_an_error_code(self):  # (npm warnings after a good install)
        r = self.run_update(err="npm WARN cleanup Failed to remove some directories\n", code=1)
        self.assertTrue(r.ok)

    def test_winget_runs_what_claude_code_runs(self):
        self.assertEqual(claude_setup.update_command(r"C:\x\WinGet\Links\claude.exe", "winget")[1:],
                         ["upgrade", "--id", "Anthropic.ClaudeCode", "--exact", "--silent", "--disable-interactivity"])


class Connection(InQt):
    def setUp(self):
        super().setUp()
        if self.elsewhere:
            return
        self.releases, self.updates = [], []
        patches = [
            mock.patch.object(claude_setup, "status", side_effect=lambda timeout=30: OK),
            mock.patch.object(claude_setup, "release", side_effect=self.fake_release),
            mock.patch.object(claude_setup, "update", side_effect=self.fake_update),
            mock.patch.object(onboarding.sessions, "running_versions",
                              side_effect=lambda: ["2.1.290", "2.1.296", "2.1.288"])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.installed = "2.1.290"
        self.conn = onboarding.ClaudeConnection()
        self.conn.status = OK

    def fake_release(self, exe):
        self.releases.append(exe)
        return claude_setup.Release(installed=self.installed, latest="2.1.296", kind="npm")

    def fake_update(self, exe):
        self.updates.append(exe)
        time.sleep(0.05)
        self.installed = "2.1.296"
        return claude_setup.Updated(True, "2.1.290", "2.1.296", "Claude Code je aktualizovaný: 2.1.290 → 2.1.296.")

    def wait(self, done):
        t0 = time.monotonic()
        while not done() and time.monotonic() - t0 < 5:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(done())

    def test_the_newest_is_asked_at_most_once_an_hour(self):
        if self.elsewhere:
            return
        self.conn.check_release()
        self.assertTrue(self.conn.checking_release)
        self.wait(lambda: self.conn.release is not None)
        self.assertTrue(self.conn.release.behind)
        self.conn.check_release()
        self.conn.check_release(max_age=600)
        self.assertEqual(self.releases, [NPM_EXE])
        self.conn.check_release(max_age=0)
        self.wait(lambda: len(self.releases) == 2 and not self.conn.checking_release)

    def test_update_then_the_sessions_left_on_the_old_one(self):
        if self.elsewhere:
            return
        self.conn.check_release()
        self.wait(lambda: self.conn.release is not None)
        got = []
        self.conn.updated.connect(got.append)
        self.conn.update_claude()
        self.assertEqual(self.conn.updating, "2.1.296")
        self.conn.update_claude()  # a second click while it runs does nothing
        self.wait(lambda: got)
        self.assertEqual(self.updates, [NPM_EXE])
        self.assertEqual((self.conn.updating, self.conn.update_note), ("", (got[0].text, True)))
        self.assertEqual(sorted(self.conn.old_sessions), ["2.1.288", "2.1.290"])
        self.wait(lambda: not self.conn.checking_release and self.conn.release.installed == "2.1.296")
        self.assertFalse(self.conn.release.behind)

    def test_nothing_without_claude_code(self):
        if self.elsewhere:
            return
        self.conn.status = claude_setup.Status()
        self.conn.check_release()
        self.conn.update_claude()
        self.assertEqual((self.releases, self.updates, self.conn.updating), ([], [], ""))


class Box(InQt):
    def setUp(self):
        super().setUp()
        if self.elsewhere:
            return
        self.conn = onboarding.ClaudeConnection()
        self.conn.status = OK
        self.box = ui.ClaudeBox(self.conn)

    def show(self, release=None, **state):
        self.conn.release = release
        for name, value in state.items():
            setattr(self.conn, name, value)
        self.conn.release_changed.emit()
        return self.box._version.text(), self.box._version_note.text(), not self.box._update_btn.isHidden()

    def test_states(self):
        if self.elsewhere:
            return
        R = claude_setup.Release
        self.assertEqual(self.show(None, _release_inflight=True),
                         ("Claude Code 2.1.290 · zjišťuju, jestli je novější…", "", False))
        self.assertEqual(self.show(R(installed="2.1.296", latest="2.1.296"), _release_inflight=False),
                         ("Claude Code 2.1.296 · nejnovější verze ✓", "", False))
        text, note, button = self.show(R(installed="2.1.290", latest="2.1.296"))
        self.assertEqual((text, note, button), ("Claude Code 2.1.290 · je nová verze 2.1.296", "", True))
        self.assertEqual(self.box._update_btn.text(), "Aktualizovat Claude Code")
        text, note, button = self.show(R(installed="2.1.290", latest="2.1.296", auto_updates=False))
        self.assertIn("Automatické aktualizace má Claude Code vypnuté", note)
        text, note, button = self.show(R(installed="2.1.290", latest="2.1.296"), updating="2.1.296")
        self.assertEqual((text, button), ("Aktualizuju Claude Code na 2.1.296…", False))
        text, note, button = self.show(R(installed="2.1.296", latest="2.1.296"), updating="",
                                       update_note=("Claude Code je aktualizovaný: 2.1.290 → 2.1.296.", True),
                                       old_sessions=["2.1.290"])
        self.assertEqual(text, "Claude Code 2.1.296 · nejnovější verze ✓")
        self.assertTrue(note.startswith("Claude Code je aktualizovaný: 2.1.290 → 2.1.296. Jedna běžící relace"))
        self.assertFalse(button)
        text, note, button = self.show(R(installed="2.1.296", error="Novou verzi teď nejde zjistit."),
                                       update_note=("", True), old_sessions=[])
        self.assertEqual((text, button), ("Claude Code 2.1.296 · novou verzi teď nejde zjistit.", True))
        self.assertEqual(self.box._update_btn.text(), "Zkusit aktualizovat")

    def test_hidden_without_claude_code_or_while_installing(self):
        if self.elsewhere:
            return
        self.conn.status = claude_setup.Status()
        self.conn.changed.emit(self.conn.status)
        self.assertTrue(self.box._version.isHidden())
        self.conn.status, self.conn.busy = OK, "login"
        self.conn.busy_changed.emit("login")
        self.assertTrue(self.box._version.isHidden())
        self.assertTrue(self.box._update_btn.isHidden())


class Menu(InQt):
    """Dictation's menu item and bubble on a stub."""

    def setUp(self):
        super().setUp()
        if self.elsewhere:
            return
        self.notes = []
        self.action = SimpleNamespace(visible=None, text=None, enabled=None)
        action = SimpleNamespace(setVisible=lambda v: setattr(self.action, "visible", v),
                                 isVisible=lambda: self.action.visible,
                                 setText=lambda t: setattr(self.action, "text", t),
                                 setEnabled=lambda e: setattr(self.action, "enabled", e))
        self.claude = SimpleNamespace(status=OK, release=None, updating="", checking_release=False, old_sessions=[],
                                      update_note=("", True),
                                      update_claude=lambda: setattr(self.claude, "updating", "2.1.296"))
        self.pills = []
        self.d = SimpleNamespace(claude=self.claude, claude_version_action=action, dialog=None,
                                 open_settings=lambda: None, button=SimpleNamespace(set_claude_version=self.pills.append),
                                 _notify=lambda msg, **kw: self.notes.append((kw.get("title"), msg, kw.get("kind"),
                                                                              kw.get("error"))))
        self.d._claude_version_line = lambda: main.Dictation._claude_version_line(self.d)

    def item(self):
        main.Dictation._show_claude_version(self.d)
        return self.action.visible, self.action.text, self.action.enabled

    def pill(self):
        main.Dictation._show_claude_version(self.d)
        return self.pills[-1] and {k: v for k, v in self.pills[-1].items() if k != "tip"}

    def test_the_panels_pill(self):
        if self.elsewhere:
            return
        R = claude_setup.Release
        self.assertEqual(self.pill(), {"installed": "2.1.290", "latest": "", "state": "unknown", "target": ""})
        self.claude.release = R(installed="2.1.296", latest="2.1.296")
        self.assertEqual(self.pill()["state"], "current")
        self.assertEqual(self.pills[-1]["tip"], "Claude Code 2.1.296 je nejnovější verze.")
        self.claude.release, self.claude.old_sessions = R(installed="2.1.290", latest="2.1.296"), ["2.1.288"]
        self.assertEqual(self.pill(), {"installed": "2.1.290", "latest": "2.1.296", "state": "new", "target": ""})
        self.assertIn("Klikni na Aktualizovat", self.pills[-1]["tip"])
        self.assertIn("Jedna běžící relace jede ještě na 2.1.288.", self.pills[-1]["tip"])
        self.claude.updating = "2.1.296"
        self.assertEqual(self.pill()["state"], "updating")
        self.claude.updating, self.claude.update_note = "", ("Soubor claude.exe drží jiný program.", False)
        self.assertEqual(self.pill()["state"], "failed")
        self.assertTrue(self.pills[-1]["tip"].startswith("Soubor claude.exe drží jiný program.\nKlikni na Zkusit"))
        self.claude.release = R(installed="2.1.296", latest="2.1.296")  # it updated itself in the meantime
        self.assertEqual(self.pill()["state"], "current")
        self.claude.status = claude_setup.Status()
        self.assertIsNone(self.pill())

    def test_item(self):
        if self.elsewhere:
            return
        self.assertEqual(self.item(), (True, "Claude Code 2.1.290", False))
        self.claude.release = claude_setup.Release(installed="2.1.296", latest="2.1.296")
        self.assertEqual(self.item(), (True, "Claude Code 2.1.296: nejnovější verze", False))
        self.claude.release = claude_setup.Release(installed="2.1.290", latest="2.1.296")
        self.assertEqual(self.item(), (True, "Aktualizovat Claude Code na 2.1.296 (teď 2.1.290)", True))
        main.Dictation._update_claude_from_menu(self.d)
        self.assertEqual(self.notes[-1][0], "Aktualizuju Claude Code na 2.1.296")
        self.assertEqual(self.item(), (True, "Aktualizuju Claude Code…", False))
        self.claude.status = claude_setup.Status()
        self.assertFalse(self.item()[0])

    def test_bubble(self):
        if self.elsewhere:
            return
        self.claude.old_sessions = ["2.1.290", "2.1.290"]
        main.Dictation._claude_updated(self.d, claude_setup.Updated(True, "2.1.290", "2.1.296", "…"))
        self.assertEqual(self.notes[-1], ("Claude Code je aktualizovaný", "Hotovo: 2.1.290 → 2.1.296. Běžící relace "
                                          "(2) jedou na staré verzi, dokud je neotevřeš znovu.", "done", None))
        main.Dictation._claude_updated(self.d, claude_setup.Updated(False, "2.1.290", "2.1.290", "Nejde to."))
        self.assertEqual(self.notes[-1], ("Claude Code se neaktualizoval", "Nejde to.", None, True))
        self.d.dialog = object()  # the settings show it in their Claude box
        main.Dictation._claude_updated(self.d, claude_setup.Updated(True, "2.1.290", "2.1.296", "…"))
        self.assertEqual(len(self.notes), 2)


class Pill(InQt):
    """The version pill between the panel and the circles (FloatingButton)."""

    VERSION = {"installed": "2.1.290", "latest": "2.1.296", "state": "new", "target": "", "tip": "Je nová verze"}

    def setUp(self):
        super().setUp()
        if self.elsewhere:
            return
        self.b = ui.FloatingButton(lambda: 0.0)
        self.b._auto_align = lambda: None  # (it goes by where the button is on the screen) the panel above, right
        self.b.set_claude(True)
        self.b.set_usage_visible(True)
        self.b._align, self.b._below = "right", False
        self.b._relayout()
        self.clicks = []
        self.b.claude_update_clicked.connect(lambda: self.clicks.append(1))

    def circles_top(self) -> float:
        return self.b._button_center().y() - self.b.DIAMETER / 2

    def test_between_the_panel_and_the_circles_with_the_button_in_place(self):
        if self.elsewhere:
            return
        before, height = self.b.button_pos(), self.b.height()
        self.b.set_claude_version(self.VERSION)
        pill, button = self.b._version_layout()
        self.assertEqual(self.b.button_pos(), before)  # the panel moved up, the circles stayed
        self.assertEqual(self.b.height(), height + self.b.VER_PILL_H + self.b.VER_GAP)
        self.assertGreaterEqual(pill.top(), self.b._panel.bottom())
        self.assertLessEqual(pill.bottom(), self.circles_top())
        self.assertEqual(pill.right(), self.b._panel.right())  # above the circles (the panel lines up with them)
        self.assertTrue(pill.contains(button))
        self.b.set_claude_version(None)
        self.assertEqual((self.b.height(), self.b.button_pos()), (height, before))
        self.assertTrue(self.b._version_layout()[0].isEmpty())

    def test_below_the_button_too(self):
        if self.elsewhere:
            return
        self.b.set_claude_version(self.VERSION)
        self.b._below = True
        self.b._relayout()
        pill = self.b._version_layout()[0]
        self.assertGreaterEqual(pill.top(), self.b._button_center().y() + self.b.DIAMETER / 2)
        self.assertLessEqual(pill.bottom(), self.b._panel.top())

    def test_the_button_updates_the_rest_does_not(self):
        if self.elsewhere:
            return
        self.b.set_claude_version(self.VERSION)
        pill, button = self.b._version_layout()
        for at in (pill.topLeft() + QPointF(20, 11), button.center()):
            event = SimpleNamespace(button=lambda: Qt.LeftButton, position=lambda at=at: QPointF(at),
                                    globalPosition=lambda at=at: QPointF(at))
            self.b.mousePressEvent(event)
            self.b.mouseReleaseEvent(event)
        self.assertEqual(self.clicks, [1])
        self.assertEqual(self.b._version_parts()[1], "Aktualizovat")
        for state, label in (("current", ""), ("updating", ""), ("failed", "Zkusit znovu"), ("unknown", "")):
            self.b.set_claude_version({**self.VERSION, "state": state})
            self.assertEqual(self.b._version_parts()[1], label, state)
            self.assertEqual(self.b._version_layout()[1].isEmpty(), not label)

    def test_painted(self):
        if self.elsewhere:
            return
        self.b.set_claude_version(self.VERSION)
        image = self.b.grab().toImage()
        pill, button = self.b._version_layout()
        inside = QPointF(button.left() + 5, button.center().y()).toPoint()  # its round end, left of the text
        self.assertEqual(image.pixelColor(inside).name(), QColor(theme.ACCENT).name())
        self.assertGreater(image.pixelColor(QPointF(pill.left() + 4, pill.center().y()).toPoint()).alpha(), 200)


if __name__ == "__main__":
    unittest.main()
