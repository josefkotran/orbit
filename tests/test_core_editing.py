"""Taking back and editing what Orbit typed, without Windows or Claude: the voice commands ("Smaž to", "Vyber to",
"Vlož to znovu", "Nahraď X za Y"), finding a misheard word, how many Backspaces a text is, the trail that says when
it's safe, the hook's report of the user's own keys and clicks, the dictation history, the corrections kept for
vocabulary learning, and Claude's edit prepared while the user talks (a stand-in for claude.exe).

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import json
import logging
import os
import shutil
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

from pynput._util.win32 import SystemHook  # noqa: E402

from app import claude_cli, editing, history, hotkey, learning, rewrite  # noqa: E402


class Commands(unittest.TestCase):
    def test_whole_dictation_commands(self):
        # how Whisper wrote Pepa's "Smaž to" on 8 Oct, and the other ways of saying it
        for said in ("Smaž to!", "Smaš to.", "Smáš to!", "Smažu to.", "Smažuto.", "S máštou!", "smaž to", "Vymaž to!",
                     "Zmaž to.", "Smažte to.", "Odstranit to.", "Odstraň to.", "Vyškrtni to.", "Smaž to poslední.",
                     "Smaž poslední diktát.", "Smaž to, prosím."):
            self.assertEqual(getattr(editing.command(said), "kind", None), editing.DELETE, said)
        for said in ("Vyber to.", "Vyberu to.", "Označ to.", "Vybrat to.", "Vyberto."):
            self.assertEqual(getattr(editing.command(said), "kind", None), editing.SELECT, said)
        for said in ("Vlož to znovu.", "Vložím to znovu.", "Vlož znovu.", "Vlož to ještě jednou.",
                     "Vlož poslední diktát."):
            self.assertEqual(getattr(editing.command(said), "kind", None), editing.PASTE_AGAIN, said)

    def test_text_stays_text(self):
        for said in ("Smaž ten soubor.", "Tak to smaž to.", "Smaž to a napiš znovu.", "Vyber to nejlepší.",
                     "Vlož to do tabulky.", "Nahraď komgit za Comgate.", "Oprav to na modrou.", "Smaž to. Odešli.",
                     "Máš to?", "Mám to.", "Vrať to.", "Zobraz to znovu.", "Zkus to znovu.", "Smažu ten soubor.",
                     "Smát se.", "Vyber si.", "Ulož to.", "Stop."):
            self.assertIsNone(editing.command(said), said)

    def test_replace_only_in_edit_mode(self):
        cmd = editing.command("Nahraď komgit za Comgate.", edit=True)
        self.assertEqual((cmd.kind, cmd.wrong, cmd.right), (editing.REPLACE, "komgit", "Comgate"))
        cmd = editing.command("Místo „komgit“ napiš Comgate.", edit=True)
        self.assertEqual((cmd.wrong, cmd.right), ("komgit", "Comgate"))
        self.assertIsNone(editing.command("Zkrať to.", edit=True))
        self.assertEqual(editing.command("Smaž to.", edit=True).kind, editing.DELETE)

    def test_the_text_decides_where_to_split(self):
        cmd = editing.command("Oprav na trh na na trhu.", edit=True)
        new, wrong, right = editing.replace("Jdu na trh.", cmd)
        self.assertEqual((new, wrong, right), ("Jdu na trhu.", "na trh", "na trhu"))


class Find(unittest.TestCase):
    def test_misheard_the_same_way_everywhere(self):
        cmd = editing.command("Nahraď komgit za Comgate.", edit=True)
        new, wrong, right = editing.replace("Platíme přes comgit a comgit funguje.", cmd)
        self.assertEqual(new, "Platíme přes Comgate a Comgate funguje.")
        self.assertEqual((wrong, right), ("comgit", "Comgate"))

    def test_capital_letter_at_the_start_of_a_sentence(self):
        cmd = editing.command("nahraď komgit za comgate", edit=True)
        self.assertEqual(editing.replace("Komgit funguje. A komgit taky.", cmd)[0], "Comgate funguje. A comgate taky.")

    def test_diacritics_and_whole_words(self):
        self.assertEqual(editing.find("Další krok je dalsi.", "další"), [(0, 5), (14, 19)])
        self.assertEqual(editing.find("Kotel a kotelna", "kotel"), [(0, 5)])  # not inside "kotelna"
        self.assertEqual(editing.find("Úplně jiný text.", "Comgate"), [])

    def test_nothing_close_enough(self):
        cmd = editing.command("Nahraď objednávku za fakturu.", edit=True)
        self.assertIsNone(editing.replace("Pošli mi to zítra.", cmd))


class Keystrokes(unittest.TestCase):
    def test_count(self):
        self.assertEqual(editing.keystrokes("Ahoj světe "), 11)
        self.assertEqual(editing.keystrokes("a\nb"), 3)
        self.assertEqual(editing.keystrokes("é"), 1)  # é written as e + a combining accent
        self.assertEqual(editing.keystrokes("👍"), 1)
        self.assertEqual(editing.keystrokes("👨‍👩‍👧"), 1)  # one family emoji

    def test_terminal_limits(self):
        self.assertTrue(editing.terminal_safe("x" * 800))
        self.assertFalse(editing.terminal_safe("x" * 801))
        self.assertTrue(editing.terminal_safe("a\nb\nc"))
        self.assertFalse(editing.terminal_safe("a\nb\nc\nd"))


class WordChanges(unittest.TestCase):
    def test_small_changes_only(self):
        self.assertEqual(editing.word_changes("Platíme přes comgit.", "Platíme přes Comgate."),
                         [("comgit", "Comgate")])
        self.assertEqual(editing.word_changes("napiš to claudovi", "napiš to Claudovi"), [("claudovi", "Claudovi")])
        self.assertEqual(editing.word_changes("Ahoj, jak se máš?", "Ahoj jak se máš."), [])  # punctuation only
        long_old = "jedna dva tři čtyři pět šest"
        self.assertEqual(editing.word_changes(long_old, "úplně jiná věta o něčem jiném naprosto"), [])

    def test_similar(self):
        self.assertGreater(editing.similar("Pošli to do komgitu", "Pošli to do Comgate"), 0.5)
        self.assertLess(editing.similar("Pošli to do komgitu", "Zítra prší"), 0.5)


class TrailTest(unittest.TestCase):
    same = staticmethod(lambda a, b: a == b)

    def test_safe_until_the_users_input(self):
        trail = editing.Trail()
        self.assertEqual(trail.check(5, self.same), (None, "empty"))
        trail.push(editing.Typed("Ahoj ", 5, at=10.0), self.same)
        trail.push(editing.Typed("světe ", 5, at=11.0), self.same)
        self.assertEqual(trail.check(5, self.same)[0].text, "světe ")
        self.assertEqual(trail.check(7, self.same), (None, "window"))  # another window in front: may come back
        self.assertEqual(trail.check(5, self.same)[0].text, "světe ")
        trail.input_seen(12.0)
        self.assertEqual(trail.check(5, self.same), (None, "input"))
        self.assertEqual(trail.items, [])

    def test_one_after_another_and_pop(self):
        trail = editing.Trail()
        trail.push(editing.Typed("a ", 5, at=1.0), self.same)
        trail.input_seen(1.5)  # a click between them: the first one is no longer reachable
        trail.push(editing.Typed("b ", 5, at=2.0), self.same)
        trail.push(editing.Typed("c ", 5, at=3.0), self.same)
        self.assertEqual([t.text for t in trail.items], ["b ", "c "])
        self.assertEqual(trail.pop().text, "c ")
        self.assertEqual(trail.deleted.text, "c ")
        self.assertEqual(trail.check(5, self.same)[0].text, "b ")

    def test_typing_over_a_selection_replaces_it(self):
        trail = editing.Trail()
        trail.push(editing.Typed("a ", 5, at=1.0), self.same)
        trail.items[-1].selected = True
        trail.push(editing.Typed("b ", 5, at=2.0), self.same)
        self.assertEqual([t.text for t in trail.items], ["b "])


class HookInput(unittest.TestCase):
    """PushToTalk.on_input: the user's own keys and clicks, not the binding, a modifier, Orbit's own window or
    the agent's button."""

    def setUp(self):
        self.seen = []
        self.own = False
        self.ptt = hotkey.PushToTalk({"kind": "mouse", "code": hotkey.MOUSE_X2}, lambda: None, lambda: None,
                                     on_input=lambda: self.seen.append(1), own_point=lambda x, y: self.own)

    def key(self, vk, injected=False):
        data = SimpleNamespace(flags=hotkey.LLKHF_INJECTED if injected else 0, vkCode=vk, scanCode=0)
        self.ptt._kb_filter(hotkey.WM_KEYDOWN, data)

    def click(self, msg, x_button=0):
        data = SimpleNamespace(flags=0, mouseData=x_button << 16, pt=SimpleNamespace(x=10, y=20))
        try:
            self.ptt._ms_filter(msg, data)
        except SystemHook.SuppressException:
            pass

    def test_keys(self):
        self.key(0x41)  # A
        self.key(0xA2)  # Left Ctrl alone moves nothing
        self.key(0x41, injected=True)  # Orbit's own typing
        self.assertEqual(len(self.seen), 1)

    def test_clicks(self):
        self.click(hotkey.WM_LBUTTONDOWN)
        self.click(hotkey.WM_RBUTTONDOWN)
        self.click(hotkey.WM_XBUTTONDOWN, 2)  # X2 is the dictation's own button
        self.assertEqual(len(self.seen), 2)
        self.own = True
        self.click(hotkey.WM_LBUTTONDOWN)  # on Orbit's button or bubble
        self.assertEqual(len(self.seen), 2)

    def test_the_agents_button_is_not_the_users_input(self):
        self.click(hotkey.WM_XBUTTONDOWN, 1)
        self.assertEqual(len(self.seen), 1)
        self.ptt.ignore({"kind": "mouse", "code": hotkey.MOUSE_X1})
        self.click(hotkey.WM_XBUTTONDOWN, 1)
        self.assertEqual(len(self.seen), 1)


class HistoryTest(unittest.TestCase):
    def setUp(self):
        history.path().unlink(missing_ok=True)

    def test_kept_and_loaded(self):
        h = history.History()
        first = h.add("Ahoj.", app="chrome", seconds=1.2)
        h.add("Druhý.", outcome=history.CLIPBOARD)
        h.update(first, corrected="Ahoj!")
        again = history.History()
        self.assertEqual([e.best for e in again.items], ["Ahoj!", "Druhý."])
        self.assertEqual(again.last().text, "Druhý.")
        self.assertEqual(again.get(first.id).app, "chrome")

    def test_limit_and_switched_off(self):
        h = history.History()
        for i in range(history.MAX_ITEMS + 5):
            h.items.append(history.Entry(id=str(i), at=0, text=str(i)))
        h.add("poslední")
        self.assertEqual(len(h.items), history.MAX_ITEMS)
        h.set_persist(False)
        self.assertFalse(history.path().exists())  # nothing of it stays on disk
        self.assertEqual([e.text for e in h.items], ["poslední"])  # "Vlož to znovu" still works
        h.add("další")
        self.assertFalse(history.path().exists())
        self.assertEqual(len(h.items), 1)

    def test_a_broken_file_is_an_empty_history(self):
        history.path().parent.mkdir(parents=True, exist_ok=True)
        history.path().write_text("{nesmysl", encoding="utf-8")
        self.assertEqual(history.History().items, [])
        history.path().write_text(json.dumps({"items": [{"id": "a", "text": "ok", "at": 1}, {"id": 5}, "x"]}),
                                  encoding="utf-8")
        self.assertEqual([e.text for e in history.History().items], ["ok"])


class Corrections(unittest.TestCase):
    def setUp(self):
        learning.corrections_path().unlink(missing_ok=True)

    def test_kept_and_sent_with_the_transcripts(self):
        self.assertIsNone(learning.add_correction("stejné", "stejné"))
        learning.add_correction("komgit", "Comgate", "Platíme přes Comgate.", learning.BY_VOICE)
        learning.add_correction("klod", "Claude", "", learning.REDICTATED)
        items = learning.corrections_since(None)
        self.assertEqual([(c["wrong"], c["right"]) for c in items], [("komgit", "Comgate"), ("klod", "Claude")])
        self.assertEqual(learning.corrections_since(items[-1]["at"]), [])
        self.assertLess(learning.stamp(0), learning.stamp(1))
        sent = {}
        saved = claude_cli.ask
        claude_cli.ask = lambda prompt, system, schema: sent.update(prompt=prompt, system=system) or {}
        try:
            learning.suggest(["Platíme přes Comgate."], [], [], corrections=items)
        finally:
            claude_cli.ask = saved
        self.assertIn('- corrected: "komgit" -> "Comgate" (in: "Platíme přes Comgate.")', sent["prompt"])
        self.assertIn('- said again: "klod" -> "Claude"', sent["prompt"])
        self.assertIn("most reliable evidence", sent["system"])


class Rewrite(unittest.TestCase):
    def test_clean_and_prompt(self):
        self.assertEqual(rewrite.clean("Ahoj\r\n\x1b[2Jsvěte​\tkonec\n\n\n\nx"), "Ahoj\n[2Jsvěte\tkonec\n\nx")
        prompt = rewrite.prompt("zkrať to", "Dlouhý text.", rewrite.LAST, "chrome")
        self.assertIn("Spoken instruction: zkrať to", prompt)
        self.assertIn("<<<TEXT\nDlouhý text.\nTEXT>>>", prompt)
        self.assertIn("(no text)", rewrite.prompt("napiš pozdrav", "", rewrite.NOTHING))
        self.assertIn("The user's name is Pepa.", rewrite.system_prompt("Pepa"))

    def test_prepared_while_the_user_talks(self):
        """A stand-in for claude.exe: it gets the prompt on stdin only after it started, answers in Claude's JSON."""
        fake = ("import json,sys; sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8'); "
                "p=sys.stdin.read(); "
                "print(json.dumps({'structured_output': {'text': 'OK: ' + p.split(chr(10))[0], 'problem': ''}}))")
        saved = claude_cli._command
        claude_cli._command = lambda *a: [sys.executable, "-I", "-c", fake]
        try:
            rw = rewrite.Rewriter()
            rw.start()
            result = rw.run("zkrať to", "Text.", rewrite.LAST)
            self.assertEqual(result.text, "OK: Spoken instruction: zkrať to")
            rw.start()
            rw.cancel()  # not needed after all: ended, nothing waits for it
            claude_cli._command = lambda *a: [sys.executable, "-I", "-c", "print('rozbité')"]
            with self.assertRaises(claude_cli.ClaudeError):
                rewrite.Rewriter().run("zkrať to", "Text.", rewrite.LAST)
        finally:
            claude_cli._command = saved


if __name__ == "__main__":
    unittest.main()
