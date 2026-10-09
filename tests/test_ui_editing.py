"""main.Dictation's commands and edits on a stub, against a pretend text field (no keys reach Windows): "Smaž to"
takes back exactly what Orbit typed and nothing after a key or click of the user's, "Vyber to", "Vlož to znovu",
"Nahraď X za Y" done by Orbit itself, an edit by (a stand-in for) Claude and taking it back, the selection replaced,
a dictation said again after "Smaž to" and a correction in the history kept for vocabulary learning.

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

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import editing, history, learning, main, rewrite  # noqa: E402

WINDOW, OTHER = 5, 9


class Field:
    """A text field with the cursor at its end: what Orbit types, deletes and selects there."""

    def __init__(self):
        self.text, self.selected, self.window, self.terminal, self.clipboard = "", 0, WINDOW, False, None

    def type(self, text):
        if self.selected:
            self.text, self.selected = self.text[:-self.selected], 0
        self.text += text
        return True

    def delete_back(self, count):
        count = 1 if self.selected and count else count  # a selection goes with one Backspace
        cut = self.selected or count
        self.text, self.selected = self.text[:len(self.text) - cut], 0
        return True

    def select_back(self, count):
        self.selected = count
        return True


class FakeInserter:
    def __init__(self, field):
        self.field, self.modes = field, []

    def insert(self, text, mode):
        self.modes.append(mode)
        return self.field.type(text)

    def to_clipboard(self, text):
        self.field.clipboard = text

    def when_keys_up(self, done, exclude=0, timeout=3):
        done(True)

    def press(self, key, after_text="", on_skipped=None):
        pass

    def copy_selection(self, done):
        done(self.field.text[-self.field.selected:] if self.field.selected else None)


class Stub:
    UNDO_WHY = main.Dictation.UNDO_WHY

    def __init__(self, field):
        self.cfg = {"trailing_space": True, "insert_mode": "type", "ptt": {"kind": "mouse", "code": 6},
                    "voice_commands": True, "voice_edit": True, "learn_vocabulary": False, "name": "", "about": "",
                    "vocabulary": "", "replacements": []}
        self.trail, self.history, self.inserter = editing.Trail(), history.History(persist=False), FakeInserter(field)
        self.ptt = SimpleNamespace(watch_clicks=lambda on: None)
        self.claude = SimpleNamespace(connected=True)
        self.notes, self.clicks = [], []
        self.dialog = self.history_window = None
        self.pending = self._edit_pending = self._rewriting = 0
        self._watching = False

    def _notify(self, msg, on_click=None, **_):
        self.notes.append(msg)
        self.clicks.append(on_click)

    def refresh(self):
        pass

    def _maybe_learn(self, force=False):
        pass


for _name in ("_put_text", "_typed", "_remember", "_run_command", "_take_back", "_paste_last", "_edit_ready",
              "_apply_edit", "_revert_edit", "_corrected", "_always_fix", "_redictated", "_history_changed",
              "_ptt_key", "_dictated", "_insert_text", "_rewritten", "_entry_corrected"):
    setattr(Stub, _name, getattr(main.Dictation, _name))


class FakeRewriter:
    def __init__(self, answer, problem=""):
        self.answer, self.problem, self.asked = answer, problem, None

    def run(self, instruction, text, scope, app=""):
        self.asked = (instruction, text, scope)
        return rewrite.Result(self.answer, self.problem)

    def cancel(self):
        pass


class Now:
    """threading.Thread that runs its target right away (the edit's worker)."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class Editing(unittest.TestCase):
    def setUp(self):
        self.field = Field()
        self.d = Stub(self.field)
        self.d.bridge = SimpleNamespace(rewritten=SimpleNamespace(emit=self.d._rewritten),
                                        rewrite_failed=SimpleNamespace(emit=lambda take, msg: self.fail(msg)))
        ins = main.inserter
        self.saved = {name: getattr(ins, name) for name in (
            "foreground", "same_window", "runs_as_admin", "is_terminal", "app_name", "delete_back", "select_back")}
        ins.foreground = lambda: self.field.window
        ins.same_window = lambda a, b: a == b
        ins.runs_as_admin = lambda w: False
        ins.is_terminal = lambda w: self.field.terminal
        ins.app_name = lambda w: "notepad"
        ins.delete_back, ins.select_back = self.field.delete_back, self.field.select_back
        self.saved_thread = main.threading.Thread
        main.threading.Thread = Now
        learning.corrections_path().unlink(missing_ok=True)

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(main.inserter, name, value)
        main.threading.Thread = self.saved_thread

    def take(self, said, edit=False):
        take = main.Take("")
        take.edit, take.target, take.raw_text = edit, self.field.window, said
        take.text = said
        if edit:
            take.command = editing.command(said, edit=True)
            take.heard = take.selection_done = True
        else:
            take.command = editing.command(said)
        return take

    def dictate(self, said):
        self.d.pending += 1
        self.d._dictated(self.take(said))

    def test_smaz_to_takes_back_one_dictation_at_a_time(self):
        self.dictate("Ahoj.")
        self.dictate("Jak se máš?")
        self.assertEqual(self.field.text, "Ahoj. Jak se máš? ")
        self.dictate("Smaž to.")
        self.assertEqual(self.field.text, "Ahoj. ")
        self.dictate("Smaž to.")
        self.assertEqual(self.field.text, "")
        self.dictate("Smaž to.")
        self.assertEqual(self.field.text, "")
        self.assertIn("Není s čím pracovat", self.d.notes[-1])

    def test_nothing_after_the_users_key_or_click(self):
        self.field.text = "Můj vlastní text. "
        self.dictate("Diktát.")
        self.d.trail.input_seen()  # the user clicked somewhere
        self.dictate("Smaž to.")
        self.assertEqual(self.field.text, "Můj vlastní text. Diktát. ")
        self.assertIn("klávesa nebo klik", self.d.notes[-1])

    def test_not_after_odesli(self):
        self.d.pending += 1
        take = self.take("Ahoj.")
        take.key = "send"
        self.d._dictated(take)
        self.dictate("Smaž to.")
        self.assertEqual(self.field.text, "Ahoj.")

    def test_long_text_in_a_terminal_is_left_alone(self):
        self.field.terminal = True
        self.dictate("Krátký.")
        self.dictate("Smaž to.")
        self.assertEqual(self.field.text, "")
        self.dictate("x" * 900)
        self.dictate("Smaž to.")
        self.assertEqual(len(self.field.text), 901)
        self.assertIn("Claude Code ho mohl sbalit", self.d.notes[-1])
        self.dictate("Vyber to.")
        self.assertIn("V terminálu text označovat neumím", self.d.notes[-1])

    def test_vyber_to_then_typing_replaces_it(self):
        self.dictate("Špatně.")
        self.dictate("Vyber to.")
        self.assertEqual(self.field.selected, len("Špatně. "))
        self.dictate("Dobře.")
        self.assertEqual(self.field.text, "Dobře. ")
        self.dictate("Smaž to.")
        self.assertEqual(self.field.text, "")

    def test_vloz_to_znovu(self):
        self.dictate("Ahoj.")
        self.field.window = OTHER
        self.dictate("Vlož to znovu.")
        self.assertEqual(self.field.text, "Ahoj. Ahoj. ")
        self.assertEqual(len(self.d.history.items), 1)  # still one dictation (the history keeps only the last here)

    def test_replace_done_by_orbit_and_remembered(self):
        self.dictate("Platíme přes komgit, komgit funguje.")
        self.d._dictated(self.take("Nahraď komgit za Comgate.", edit=True))
        self.assertEqual(self.field.text, "Platíme přes Comgate, Comgate funguje. ")
        self.assertIn("Opraveno: komgit → Comgate", self.d.notes[-1])
        stored = learning.corrections_since(None)
        self.assertEqual([(c["wrong"], c["right"], c["source"]) for c in stored],
                         [("komgit", "Comgate", learning.BY_VOICE)])
        self.d.clicks[-1]()  # "budu to tak opravovat vždycky"
        self.assertEqual(self.d.cfg["replacements"], [["komgit", "Comgate"]])
        self.dictate("Smaž to.")  # the edited dictation is still the one to take back
        self.assertEqual(self.field.text, "")

    def test_claude_edits_the_last_dictation_and_it_goes_back(self):
        self.dictate("No takže, ehm, pošli mi to zítra ráno.")
        take = self.take("Zkrať to.", edit=True)
        take.rewriter = claude = FakeRewriter("Pošli mi to zítra ráno.")
        self.d._dictated(take)
        self.assertEqual(claude.asked, ("Zkrať to.", "No takže, ehm, pošli mi to zítra ráno.", rewrite.LAST))
        self.assertEqual(self.field.text, "Pošli mi to zítra ráno. ")
        self.assertIn("vrátím původní text", self.d.notes[-1])
        self.d.clicks[-1]()
        self.assertEqual(self.field.text, "No takže, ehm, pošli mi to zítra ráno. ")
        self.assertEqual(learning.corrections_since(None), [])  # rewording isn't a recognition error

    def test_claude_edits_the_selection(self):
        self.field.text, self.field.selected = "Text: ahoj světe", len("ahoj světe")
        take = self.take("Velkými písmeny.", edit=True)
        take.selection = "ahoj světe"
        take.rewriter = FakeRewriter("AHOJ SVĚTE")
        self.d._dictated(take)
        self.assertEqual(self.field.text, "Text: AHOJ SVĚTE")
        self.assertEqual(self.d.inserter.modes[-1], "paste")  # over a selection always pasted

    def test_a_key_after_reading_the_selection_sends_it_to_the_clipboard(self):
        self.field.text, self.field.selected = "ahoj", 4
        take = self.take("Velkými písmeny.", edit=True)
        take.selection, take.probed_at = "ahoj", 1.0
        take.rewriter = FakeRewriter("AHOJ")
        self.d.trail.input_seen(2.0)
        self.d._dictated(take)
        self.assertEqual(self.field.text, "ahoj")
        self.assertEqual(self.field.clipboard, "AHOJ")

    def test_claude_writes_when_there_is_nothing_to_edit(self):
        take = self.take("Napiš krátký pozdrav.", edit=True)
        take.rewriter = FakeRewriter("Dobrý den, zdravím.")
        self.d._dictated(take)
        self.assertEqual(self.field.text, "Dobrý den, zdravím. ")
        problem = self.take("Zkrať to.", edit=True)
        problem.rewriter = FakeRewriter("", "Není co zkrátit, označ text.")
        self.d.trail.input_seen()
        self.d._dictated(problem)
        self.assertEqual(self.d.notes[-1], "Není co zkrátit, označ text.")

    def test_without_claude_only_what_orbit_does_itself(self):
        self.d.claude.connected = False
        self.dictate("Ahoj.")
        self.d._dictated(self.take("Zkrať to.", edit=True))
        self.assertIn("umí jen Claude", self.d.notes[-1])
        self.assertEqual(self.field.text, "Ahoj. ")

    def test_said_again_after_smaz_to_is_a_hint_for_learning(self):
        self.dictate("Pošli to přes komgit.")
        self.dictate("Smaž to.")
        self.dictate("Pošli to přes Comgate.")
        stored = learning.corrections_since(None)
        self.assertEqual([(c["wrong"], c["right"], c["source"]) for c in stored],
                         [("komgit", "Comgate", learning.REDICTATED)])
        self.assertFalse(any("Opraveno" in n for n in self.d.notes))  # no bubble for a guess

    def test_a_correction_in_the_history(self):
        self.dictate("Napiš to klodovi.")
        entry = self.d.history.last()
        self.d._entry_corrected(entry.id, "Napiš to Claudovi.")
        self.assertEqual(self.d.history.last().best, "Napiš to Claudovi.")
        self.assertEqual([(c["wrong"], c["right"]) for c in learning.corrections_since(None)],
                         [("klodovi", "Claudovi")])


class HistoryWindowTest(unittest.TestCase):
    """The history window: one click copies a row (it gets a tick), the search finds without diacritics."""

    def test_copy_and_search(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None and not isinstance(app, QApplication):  # another test's QGuiApplication: a window
            # needs a QApplication, so this one runs in a process of its own
            test = f"{__name__}.HistoryWindowTest.test_copy_and_search"
            run = subprocess.run([sys.executable, "-m", "unittest", test],
                                 cwd=Path(__file__).parent, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            return
        self.app = app or QApplication([])  # kept for the window's lifetime
        from app.historyview import HistoryWindow
        h = history.History(persist=False)
        h.persist = True  # several entries in memory (nothing is saved: the file is in the test's data folder)
        first = h.add("Faktura za září pořád chybí.", app="chrome")
        h.add("Pošli mi to zítra.", app="WindowsTerminal")
        window = HistoryWindow(h, Path(tempfile.gettempdir()))
        copied = []
        window.copy_requested.connect(copied.append)
        self.assertEqual(window.list.count(), 2)
        window.list.copy.emit(first.id)  # the icon at the row's end
        self.assertEqual(copied, [first.id])
        self.assertEqual(window._rows.copied, first.id)
        self.assertIn("Zkopírováno", window.status.text())
        window.search.setText("zari")
        self.assertEqual(window.list.count(), 1)
        self.assertIn("Nalezeno: 1 z 2", window.count.text())
        window.search.setText("nic takového")
        self.assertEqual(window.list.count(), 0)
        history.path().unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
