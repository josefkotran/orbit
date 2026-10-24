"""main.Dictation's transcript check (check.py) on a stub, against a pretend text field (no keys reach Windows): the
fix goes into the window in place of the misheard words and a click on the bubble takes it back; after a key or click
of the user's it stays out of the window (in the history, and on the clipboard on a click); a dictation typed after
the checked one is typed again behind the fix; "Odešli" waits for the fix; a long text in a terminal isn't retyped;
the last piece goes to Whisper and Canary without the silence after the last word.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
import logging
import os
import shutil
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

from concurrent.futures import Future  # noqa: E402

import numpy as np  # noqa: E402

from app import editing, history, main  # noqa: E402

WINDOW = 5


class Field:
    """A text field with the cursor at its end."""

    def __init__(self):
        self.text, self.window, self.terminal, self.clipboard, self.presses = "", WINDOW, False, None, []

    def type(self, text):
        self.text += text
        return True

    def delete_back(self, count):
        self.text = self.text[:len(self.text) - count]
        return True


class FakeInserter:
    def __init__(self, field):
        self.field = field

    def insert(self, text, mode):
        return self.field.type(text)

    def to_clipboard(self, text):
        self.field.clipboard = text

    def when_keys_up(self, done, exclude=0, timeout=3):
        done(True)

    def press(self, key, after_text="", on_skipped=None):
        self.field.presses.append(key)


class FakeChecker:
    def __init__(self, answer=None, field=None):
        self.answer, self.asked, self.cancelled, self.field, self.window_then = answer, None, False, field, None

    def run(self, text, other="", before="", app=""):
        self.asked = (text, other, before, app)
        self.window_then = self.field.text if self.field else None  # what the window held when Claude was asked
        return text if self.answer is None else self.answer

    def cancel(self):
        self.cancelled = True


class Threads:
    """threading.Thread that waits until the test lets it run (the check's worker). A thread started by one that
    runs (the check before insertion asks Claude in one) runs at once, unless nested_now is off."""
    waiting: list = []
    running = False
    nested_now = True

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        if Threads.running and Threads.nested_now:
            self.target()
        else:
            Threads.waiting.append(self.target)

    @classmethod
    def run_all(cls):
        while cls.waiting:
            cls.running = True
            try:
                cls.waiting.pop(0)()
            finally:
                cls.running = False


class Stub:
    def __init__(self, field):
        self.cfg = {"trailing_space": True, "insert_mode": "type", "ptt": {"kind": "mouse", "code": 6},
                    "voice_commands": True, "learn_vocabulary": False, "replacements": [], "check_first": False}
        self.trail, self.history, self.inserter = editing.Trail(), history.History(persist=False), FakeInserter(field)
        self.ptt = SimpleNamespace(watch_clicks=lambda on: None)
        self.notes, self.clicks, self.quiet = [], [], []
        self.history_window = None
        self.pending = 0
        self._watching = False
        self.bridge = SimpleNamespace(checked=SimpleNamespace(emit=self._checked),
                                      prechecked=SimpleNamespace(emit=self._prechecked),
                                      asking=SimpleNamespace(emit=self._asking))
        self._held_takes = []

    def _notify(self, msg, on_click=None, quiet=False, **_):
        self.notes.append(msg)
        self.clicks.append(on_click)
        self.quiet.append(quiet)

    def refresh(self):
        pass

    def _maybe_learn(self, force=False):
        pass


for _name in ("_put_text", "_typed", "_remember", "_press", "_release_key", "_run_check", "_checked", "_retype",
              "_revert_check", "_history_changed", "_ptt_key", "_dictated", "_insert_text", "_redictated",
              "_run_command", "_take_back", "_queue_piece", "_deliver", "_wants_precheck", "_precheck",
              "_prechecked", "_release_held", "_tell_fixed", "_second_text_of", "_asking"):
    setattr(Stub, _name, getattr(main.Dictation, _name))


class Base(unittest.TestCase):
    def setUp(self):
        self.field = Field()
        self.d = Stub(self.field)
        ins = main.inserter
        self.saved = {name: getattr(ins, name) for name in (
            "foreground", "same_window", "runs_as_admin", "is_terminal", "app_name", "delete_back")}
        ins.foreground = lambda: self.field.window
        ins.same_window = lambda a, b: a == b
        ins.runs_as_admin = lambda w: False
        ins.is_terminal = lambda w: self.field.terminal
        ins.app_name = lambda w: "WindowsTerminal"
        ins.delete_back = self.field.delete_back
        self.saved_thread, self.saved_timer = main.threading.Thread, main.QTimer.singleShot
        main.threading.Thread = Threads
        self.timers = []
        main.QTimer.singleShot = lambda ms, fn: self.timers.append(fn)
        Threads.waiting, Threads.nested_now = [], True

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(main.inserter, name, value)
        main.threading.Thread = self.saved_thread
        main.QTimer.singleShot = self.saved_timer

    def dictate(self, said, answer=None, key="", second=None):
        take = main.Take("")
        take.target, take.raw_text, take.text, take.key = self.field.window, said, said, key
        take.command = editing.command(said)
        take.checker = FakeChecker(answer, self.field)
        if second is not None:  # what the second recognizer heard
            future = Future()
            future.set_result(second)
            take.second = [future]
        take.released_at = time.perf_counter()
        self.d.pending += 1
        self.d._dictated(take)
        return take


class Check(Base):
    """check_first off: the text goes in at once, the fix after it."""

    def test_the_fix_goes_into_the_window_and_a_click_takes_it_back(self):
        take = self.dictate("Otehři novou sešn.", "Otevři novou session.")
        self.assertEqual(self.field.text, "Otehři novou sešn. ")  # typed at once, the check comes later
        Threads.run_all()
        self.assertEqual(self.field.text, "Otevři novou session. ")
        entry = self.d.history.get(take.entry_id)
        self.assertEqual((entry.text, entry.unchecked), ("Otevři novou session.", "Otehři novou sešn."))
        self.assertIn("Opraveno: Otehři → Otevři, sešn → session", self.d.notes[-1])
        self.assertTrue(self.d.quiet[-1])
        self.assertEqual(take.checker, None)
        self.assertEqual(Threads.waiting, [])
        self.d.clicks[-1]()  # "Klikni sem a vrátím původní"
        self.assertEqual(self.field.text, "Otehři novou sešn. ")
        self.assertEqual((entry.text, entry.unchecked, entry.checked),
                         ("Otehři novou sešn.", "", "Otevři novou session."))

    def test_not_after_the_users_key_or_click(self):
        take = self.dictate("Otehři to.", "Otevři to.")
        self.d.trail.input_seen()  # the user clicked somewhere
        Threads.run_all()
        self.assertEqual(self.field.text, "Otehři to. ")
        entry = self.d.history.get(take.entry_id)
        self.assertEqual((entry.text, entry.checked, entry.best), ("Otehři to.", "Otevři to.", "Otevři to."))
        self.assertIn("Opravil bych: Otehři → Otevři. Mezitím přišla klávesa nebo klik", self.d.notes[-1])
        self.d.clicks[-1]()
        self.assertEqual(self.field.clipboard, "Otevři to.")

    def test_a_dictation_after_it_is_typed_again_behind_the_fix(self):
        self.dictate("Proskoumej zahřízení.", "Prozkoumej zařízení.")
        self.dictate("A pak hotovo.")
        Threads.run_all()
        self.assertEqual(self.field.text, "Prozkoumej zařízení. A pak hotovo. ")
        self.dictate("Smaž to.")  # the trail still knows both: the later one goes first
        self.assertEqual(self.field.text, "Prozkoumej zařízení. ")

    def test_a_space_typed_between_dictations_keeps_the_fixes(self):
        """24 Oct: Pepa has the trailing space off and typed it after each dictation; as any other key it ended the
        trail and no fix ever went into the window ("Pouští → Pushni" only in the bubble)."""
        self.d.cfg["trailing_space"] = False
        self.dictate("Pouští to na git.", "Pushni to na git.")
        self.field.type(" ")
        self.d.trail.space_seen()
        self.dictate("Půjšně to na git.", "Pushni to na git.")
        Threads.run_all()
        self.assertEqual(self.field.text, "Pushni to na git. Pushni to na git.")
        self.dictate("Smaž to.")
        self.assertEqual(self.field.text, "Pushni to na git. ")

    def test_odesli_waits_for_the_fix(self):
        self.dictate("Otehři to.", "Otevři to.", key="send")
        self.assertEqual(self.field.presses, [])
        Threads.run_all()
        self.assertEqual(self.field.text, "Otevři to.")
        self.assertEqual(self.field.presses, ["send"])
        self.assertEqual(self.d.trail.items, [])  # sent: nothing to take back
        for fn in self.timers:  # the time limit comes later and does nothing
            fn()
        self.assertEqual(self.field.presses, ["send"])

    def test_odesli_goes_when_the_check_takes_too_long(self):
        self.dictate("Otehři to.", "Otevři to.", key="send")
        for fn in self.timers:
            fn()
        self.assertEqual(self.field.presses, ["send"])
        Threads.run_all()  # the fix came after the Enter: the text was sent already
        self.assertEqual(self.field.text, "Otehři to.")
        self.assertIn("Text už odešel", self.d.notes[-1])

    def test_nothing_to_fix_and_nothing_to_check(self):
        self.dictate("Všechno je správně.")
        Threads.run_all()
        self.assertEqual((self.field.text, self.d.notes), ("Všechno je správně. ", []))
        take = self.dictate("OK.", "Okej.")
        self.assertEqual(Threads.waiting, [])  # one word isn't worth a check
        self.assertIsNone(take.checker)
        take = self.dictate("Smaž to.", "Smažte to.")  # a command
        self.assertTrue(take.checker is None and Threads.waiting == [])

    def test_long_text_in_a_terminal_is_left_alone(self):
        self.field.terminal = True
        long = "slovo " * 150 + "sešn."
        self.dictate(long, long.replace("sešn", "session"))
        Threads.run_all()
        self.assertTrue(self.field.text.endswith("sešn. "))
        self.assertIn("Delší text v terminálu nepřepíšu", self.d.notes[-1])

    def test_the_last_piece_without_the_silence_after_it(self):
        submitted, second = [], []
        d = SimpleNamespace(recorder=SimpleNamespace(noise=0.0), _transcribe_piece=None,
                            _submit=lambda fn, take, audio: submitted.append(audio),
                            second_opinion=SimpleNamespace(transcribe=None),
                            second_executor=SimpleNamespace(submit=lambda fn, audio: second.append(audio) or audio))
        take = main.Take("")
        take.checker = FakeChecker()
        rate = main.SAMPLE_RATE
        speech = (np.sin(np.arange(rate) / rate * 2 * np.pi * 200) * 3000).astype(np.int16)
        audio = np.concatenate([speech, np.zeros(rate, np.int16)])
        main.Dictation._queue_piece(d, take, audio, last=True)
        self.assertAlmostEqual(len(submitted[0]) / rate, 1.3, delta=0.04)
        self.assertEqual(len(second[0]), len(submitted[0]))  # Canary hears the same
        self.assertEqual(len(take.audio[0]), 2 * rate)  # the recording keeps all of it
        main.Dictation._queue_piece(d, take, audio)  # a piece cut at a pause: as it is
        self.assertEqual(len(submitted[1]), 2 * rate)


if __name__ == "__main__":
    unittest.main()


class CheckFirst(Base):
    """check_first: the fixed text goes in, not the wrong one first and the fix after it (Pepa 24 Oct)."""

    def setUp(self):
        super().setUp()
        self.d.cfg["check_first"] = True

    def test_the_fixed_text_goes_in_at_once(self):
        take = self.dictate("Pouští to na git.", "Pushni to na git.")
        self.assertEqual(self.field.text, "")  # Claude first
        Threads.run_all()
        self.assertEqual(self.field.text, "Pushni to na git. ")
        self.assertEqual(take.checker, None)
        entry = self.d.history.get(take.entry_id)
        self.assertEqual((entry.text, entry.unchecked), ("Pushni to na git.", "Pouští to na git."))
        self.assertIn("Opraveno: Pouští → Pushni", self.d.notes[-1])
        self.d.clicks[-1]()  # "Klikni sem a vrátím, co napsal Whisper"
        self.assertEqual(self.field.text, "Pouští to na git. ")

    def test_where_both_recognizers_agree_it_goes_in_at_once(self):
        take = self.dictate("Sparta Praha šampion.", second="Sparta Praha šampion!")
        checker = take.checker
        Threads.run_all()
        self.assertEqual(self.field.text, "Sparta Praha šampion. ")
        self.assertEqual(checker.window_then, "Sparta Praha šampion. ")  # checked after it went in
        self.assertEqual(self.d.notes, [])
        take = self.dictate("Daytona Git.", "Dej to na git.", second="Dej to na git.")
        checker = take.checker
        Threads.run_all()
        self.assertEqual(checker.window_then, "Sparta Praha šampion. ")  # they differ: asked before it went in
        self.assertTrue(self.field.text.endswith("Dej to na git. "))

    def test_what_comes_after_it_waits_and_the_order_stays(self):
        self.dictate("Pouští to na git.", "Pushni to na git.")
        self.dictate("A hotovo.")
        self.assertEqual(self.field.text, "")
        Threads.run_all()
        self.assertEqual(self.field.text, "Pushni to na git. A hotovo. ")
        self.dictate("Otehři to.", "Otevři to.")
        self.dictate("Smaž to.")  # a command waits for it too, and then takes it back
        Threads.run_all()
        self.assertEqual(self.field.text, "Pushni to na git. A hotovo. ")

    def test_the_button_says_claude_checks_while_it_is_asked(self):
        seen = []
        take = self.dictate("Pouští to na git.", "Pushni to na git.", second="Pushni to na git.")
        run = take.checker.run
        take.checker.run = lambda *a: (seen.append([t.asking for t in self.d._held_takes]), run(*a))[1]
        self.assertFalse(take.asking)  # the recognizers first: "Přepisuji…"
        Threads.run_all()
        self.assertEqual(seen, [[True]])
        self.assertFalse(take.asking)
        self.assertEqual(self.d._held_takes, [])
        take = self.dictate("Sparta Praha šampion.", second="Sparta Praha šampion!")
        take.checker.run = lambda *a: (seen.append([t.asking for t in self.d._held_takes]), "")[1]
        Threads.run_all()
        self.assertFalse(take.asking)  # they agree: Claude isn't waited for (checked after it went in)

    def test_too_slow_goes_in_as_it_was_and_the_fix_follows(self):
        saved = main.PRECHECK_WAIT_S
        main.PRECHECK_WAIT_S = 0.01
        Threads.nested_now = False  # Claude answers only after the wait is over
        try:
            take = self.dictate("Pouští to na git.", "Pushni to na git.")
            Threads.run_all()
        finally:
            main.PRECHECK_WAIT_S = saved
        self.assertTrue(take.late)
        self.assertEqual(self.field.text, "Pushni to na git. ")
        self.assertIn("Opraveno: Pouští → Pushni. Klikni sem a vrátím původní.", self.d.notes[-1])


class ButtonWords(unittest.TestCase):
    """Dictation.refresh: what the button says next to the circles (FloatingButton.set_status)."""

    def words(self, pending=1, rewriting=0, edits=0, asking=False, live=False):
        shown = []
        held = [SimpleNamespace(asking=asking)]
        d = SimpleNamespace(
            cfg={"ptt": {"kind": "mouse", "code": 6}, "show_usage": False, "model": "m"}, take=None,
            recorder=SimpleNamespace(live=live), pending=pending, _rewriting=rewriting, _edit_pending=edits,
            _held_takes=held, server_state="ready", _agent_state="idle", usage=None,
            downloads=SimpleNamespace(running=lambda m: False),
            button=SimpleNamespace(set_state=lambda *a: None, set_button_tip=lambda t: shown.append(t),
                                   set_status=lambda t: shown.append(t), set_agent_state=lambda s: None),
            tray=SimpleNamespace(setIcon=lambda i: None, setToolTip=lambda t: None),
            icons={k: None for k in ("idle", "loading", "recording", "busy", "error")},
            hint_action=SimpleNamespace(setText=lambda t: None))
        d.edit_icons = d.icons
        main.Dictation.refresh(d)
        return shown[-1]

    def test_each_phase_in_words(self):
        self.assertEqual(self.words(), "Přepisuji…")
        self.assertEqual(self.words(asking=True), "Claude kontroluje přepis…")
        self.assertEqual(self.words(edits=1), "Přepisuji pokyn…")
        self.assertEqual(self.words(pending=0, rewriting=1), "Claude upravuje text…")
        self.assertEqual(self.words(pending=0), "")  # nothing going on
        self.assertEqual(self.words(live=True), "")  # recording: the red mic says it
