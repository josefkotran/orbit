"""The transcript check and what came with it (24 Oct): Claude's fix is taken only when it is a fix (check.accept),
the check's Claude started while the user talks (a stand-in for claude.exe, stream-json), the second recognizer's
process (a stand-in for Canary), the silence after the last word cut off (recorder.trim_tail), the "Děkujeme za
pozornost" filter and a replacement keeping Whisper's capital letter.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import logging
import os
import shutil
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

import numpy as np  # noqa: E402

from app import canary, check, claude_cli, downloads, recorder  # noqa: E402
from app.whisper_server import apply_replacements, clean_text  # noqa: E402

RATE = 16000


def tone(seconds: float, level: float = 2000) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (np.sin(2 * np.pi * 220 * t) * level).astype(np.int16)


def quiet(seconds: float, level: float = 3) -> np.ndarray:
    return (np.random.default_rng(1).standard_normal(int(seconds * RATE)) * level).astype(np.int16)


class Filters(unittest.TestCase):
    def test_a_replacement_keeps_the_capital_letter(self):
        fix = [["proskoumej", "prozkoumej"], ["comgit", "Comgate"]]
        self.assertEqual(apply_replacements("Proskoumej to.", fix), "Prozkoumej to.")
        self.assertEqual(apply_replacements("tak proskoumej to", fix), "tak prozkoumej to")
        self.assertEqual(apply_replacements("platba přes comgit", fix), "platba přes Comgate")

    def test_dekujeme_za_pozornost(self):
        self.assertEqual(clean_text("Děkujeme za pozornost."), "")
        self.assertEqual(clean_text("Děkujeme za sledování!"), "")
        self.assertEqual(clean_text("…aby to byl Sonnet, nebo Haiku. Děkujeme za pozornost."),
                         "…aby to byl Sonnet, nebo Haiku.")
        # said in an e-mail it stays, and so does a sentence that only has the words in it
        self.assertEqual(clean_text("Posílám ceník. Děkuji za pozornost."), "Posílám ceník. Děkuji za pozornost.")
        self.assertEqual(clean_text("Děkujeme za pozornost, kterou nám věnujete."),
                         "Děkujeme za pozornost, kterou nám věnujete.")


class TrimTail(unittest.TestCase):
    def test_the_silence_after_the_last_word_goes(self):
        audio = np.concatenate([quiet(0.2), tone(2.0), quiet(0.9)])
        trimmed = recorder.trim_tail(audio)
        self.assertAlmostEqual(len(trimmed) / RATE, 0.2 + 2.0 + recorder.TRIM_KEEP_S, delta=0.04)
        np.testing.assert_array_equal(trimmed, audio[:len(trimmed)])

    def test_nothing_said_and_nothing_to_cut(self):
        silence = quiet(1.0)
        self.assertIs(recorder.trim_tail(silence), silence)
        speech = tone(1.0)
        self.assertEqual(len(recorder.trim_tail(speech)), len(speech))
        self.assertEqual(len(recorder.trim_tail(np.zeros(100, np.int16))), 100)

    def test_a_quiet_last_word_stays(self):
        audio = np.concatenate([tone(1.0), quiet(0.2), tone(0.3, level=260), quiet(1.0)])  # a soft "…ne?"
        self.assertGreaterEqual(len(recorder.trim_tail(audio)) / RATE, 1.0 + 0.2 + 0.3 + 0.27)

    def test_a_hissing_mic_counts_its_hiss_as_quiet(self):
        audio = np.concatenate([tone(1.0, level=3000), quiet(1.0, level=200)])  # noise above PAUSE_RMS
        self.assertGreater(len(recorder.trim_tail(audio, noise=0)) / RATE, 1.9)  # the hiss looks like speech
        self.assertLess(len(recorder.trim_tail(audio, noise=200)) / RATE, 1.4)


class Accept(unittest.TestCase):
    def test_a_fix_is_taken(self):
        text = "Proskoumej zahřízení a otevři novou sešn."
        fixed = "Prozkoumej zařízení a otevři novou session."
        self.assertEqual(check.accept(text, fixed + "\n"), fixed)
        self.assertEqual(check.accept(text, text), text)
        self.assertEqual(check.changes(text, fixed), [("Proskoumej", "Prozkoumej"), ("zahřízení", "zařízení"),
                                                      ("sešn", "session")])

    def test_anything_else_is_not(self):
        text = "Příliš žluťoučký kůň."
        self.assertIsNone(check.accept(text, "Příliš žluťoučký kůň úpěl ďábelské ódy."))  # it went on (Haiku did)
        self.assertIsNone(check.accept(text, "Tohle je známá pangrama, kterou se testují fonty."))  # it answered
        self.assertIsNone(check.accept("Ahoj\nsvěte", "Ahoj světe"))  # "nový řádek" was said
        self.assertIsNone(check.accept(text, "Příliš žluťoučký\x1b kůň."))
        self.assertIsNone(check.accept(text, None))
        self.assertIsNone(check.accept(text, "   "))
        long = " ".join(f"slovo{i}" for i in range(30))
        self.assertIsNone(check.accept(long, " ".join(f"jiné{i}" if i % 2 else f"slovo{i}" for i in range(30))))
        self.assertIsNotNone(check.accept(long, long.replace("slovo3 ", "slovo tři ")))
        self.assertIsNone(check.accept("Kolik je hodin v Praze?", "V Praze je teď přesně dvanáct hodin."))

    def test_words_run_together_are_split_again(self):
        """24 Oct, Pepa's "Dej to na git, pushni to na git": Whisper wrote two words where he said six, Canary heard
        it right, and the fix was thrown away while words were counted."""
        self.assertEqual(check.accept("Daytona Git, Pushnitona Git,", "Dej to na git, pushni to na git,"),
                         "Dej to na git, pushni to na git,")
        self.assertEqual(check.changes("Daytona Git, Pushnitona Git,", "Dej to na git, pushni to na git,"),
                         [("Daytona", "Dej to na"), ("Git", "git"), ("Pushnitona", "pushni to na"), ("Git", "git")])
        # the bubble: "Git → git" next to them is noise
        self.assertEqual(check.summary(check.changes("Daytona Git, Pushnitona Git,", "Dej to na git, pushni to na git,")),
                         "Daytona → Dej to na, Pushnitona → pushni to na")
        self.assertEqual(check.summary([("git", "Git")]), "git → Git")  # unless that's all there is
        self.assertEqual(check.summary([(str(i), f"x{i}") for i in range(5)]), "0 → x0, 1 → x1, 2 → x2 …")

    def test_what_goes_to_claude(self):
        sent = check.prompt("Otehři to.", "Otevři to.", "Ahoj.", "WindowsTerminal")
        self.assertIn('"other": "Otevři to."', sent)
        self.assertIn('"before": "Ahoj."', sent)
        self.assertNotIn("other", check.prompt("Otehři to."))
        system = check.system_prompt("Pepa", "e-shop s textilem", "Claude, M-tex")
        self.assertIn("The speaker is Pepa.", system)
        self.assertIn("Claude, M-tex", system)
        self.assertIn("(none)", check.system_prompt())
        self.assertFalse(check.worth_checking("OK."))
        self.assertTrue(check.worth_checking("Pusť to."))


class Prepared(unittest.TestCase):
    def setUp(self):
        self.saved = claude_cli._command

    def tearDown(self):
        claude_cli._command = self.saved

    def fake(self, answer: str):
        """A stand-in for claude.exe answering with a stream: whatever `answer` (Python) makes of the prompt p."""
        code = ("import json,sys; sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8'); "
                "m=json.loads(sys.stdin.readline()); p=json.loads(m['message']['content'])['text']; "
                f"print(json.dumps({{'type': 'result', 'structured_output': {{'text': {answer}}}}}))")
        claude_cli._command = lambda *a, **k: [sys.executable, "-I", "-c", code]

    def test_the_checkers_answer(self):
        self.fake("p.replace('Otehři', 'Otevři')")
        checker = check.Checker("Pepa")
        checker.start()
        self.assertEqual(checker.run("Otehři novou session."), "Otevři novou session.")
        self.fake("'Jasně, tady je odpověď na tvou otázku: ' + p")  # it answered instead of fixing
        self.assertIsNone(check.Checker().run("Kolik je hodin v Praze?"))

    def test_a_broken_answer(self):
        claude_cli._command = lambda *a, **k: [sys.executable, "-I", "-c", "print('rozbité')"]
        with self.assertRaises(claude_cli.ClaudeError):
            check.Checker().run("Otehři to.")

    def test_the_stream_is_read_to_its_result(self):
        lines = '{"type":"system"}\n{"type":"assistant"}\n{"type":"result","structured_output":{"text":"x"}}\n'
        self.assertEqual(claude_cli._result(lines, "", 0, stream=True), {"text": "x"})
        with self.assertRaises(claude_cli.ClaudeError):
            claude_cli._result('{"type":"system"}\n', "", 1, stream=True)


# A stand-in for the Canary process: the same protocol, the text says how long the piece was; "die" in a piece of
# exactly 1234 samples ends it
FAKE_WORKER = """
import sys; sys.path.insert(0, sys.argv[1])
import base64, json, os
from app.voice import _stdin_lines
print("loaded 0.1", flush=True)
for line in _stdin_lines():
    r = json.loads(line)
    n = len(base64.b64decode(r["pcm"])) // 2
    if n == 1234:
        os._exit(3)
    print(json.dumps({"id": r["id"], "text": f"{n} vzorků"}), flush=True)
"""


class SecondOpinion(unittest.TestCase):
    def test_pieces_come_back_and_a_dead_process_is_no_answer(self):
        second = canary.SecondOpinion(worker_code=FAKE_WORKER)
        try:
            second.start()
            self.assertEqual(second.transcribe(np.zeros(16000, np.int16), timeout=20), "16000 vzorků")
            self.assertEqual(second.transcribe(np.zeros(800, np.int16), timeout=20), "800 vzorků")
            self.assertIsNone(second.transcribe(np.zeros(41 * RATE, np.int16)))  # too long for it: not sent
            self.assertIsNone(second.transcribe(np.zeros(1234, np.int16), timeout=20))  # it died on this one
            self.assertEqual(second.transcribe(np.zeros(500, np.int16), timeout=20), "500 vzorků")  # a new one
        finally:
            second.close()

    def test_the_download(self):
        item = downloads.ITEMS[canary.KEY]
        self.assertEqual(item.folder, canary.MODEL_DIR)
        self.assertEqual({f.name for f in item.files}, {"config.json", "vocab.txt", "encoder-model.onnx",
                                                         "encoder-model.onnx.data", "decoder-model.onnx"})
        self.assertTrue(all("/resolve/" in f.url and len(f.sha256) == 64 for f in item.files))
        self.assertEqual(downloads.size_text(item.size), "4,0 GB")


if __name__ == "__main__":
    unittest.main()
