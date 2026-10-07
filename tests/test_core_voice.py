"""voice.py: Piper in a process of its own, with a silent stand-in for the sound card (nothing is heard), the voice
model read in place (models\\piper, read-only). Skipped without Piper or the Jirka model.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
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

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402

from app import voice  # noqa: E402

APP = QCoreApplication.instance() or QCoreApplication([])
REAL_PIPER = Path(__file__).resolve().parent.parent / "models" / "piper"
MODEL = voice.FALLBACK
LONG = "Relace ve složce orbit dokončila práci na webu, kontrola prošla bez chyb a stránka je nahraná. " * 4

# The Piper process as PiperSpeaker starts it, only with a sound card that plays nothing (in real time)
SILENT_WORKER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
import app.voice as v
class Out:
    def __init__(self, samplerate, **kw):
        self.rate, self.n = samplerate, 0
    def start(self):
        print("stream-start", file=sys.stderr, flush=True)
    def write(self, audio):
        self.n += len(audio)
        time.sleep(len(audio) / self.rate)
    def stop(self):
        pass
    def abort(self):
        print("stream-abort", file=sys.stderr, flush=True)
    def close(self):
        print("stream-played", self.n, file=sys.stderr, flush=True)
v.sd.OutputStream = Out
v._worker(*sys.argv[2:])
"""


class Records(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


@unittest.skipUnless(voice.piper_installed() and (REAL_PIPER / f"{MODEL}.onnx").is_file(), "bez Piperu nebo hlasu")
class Speaker(unittest.TestCase):
    def setUp(self):
        self.saved = voice.PIPER_DIR, voice._WORKER_CODE
        voice.PIPER_DIR, voice._WORKER_CODE = REAL_PIPER, SILENT_WORKER
        self.records = Records()
        logging.getLogger("app.voice").addHandler(self.records)
        logging.getLogger("app.voice").setLevel(logging.DEBUG)
        self.finished = 0
        self.speakers = []

    def tearDown(self):
        for sp in self.speakers:
            sp.close()
        voice.PIPER_DIR, voice._WORKER_CODE = self.saved
        logging.getLogger("app.voice").removeHandler(self.records)

    def speaker(self):
        sp = voice.PiperSpeaker(MODEL)
        sp.finished.connect(self._finished)
        self.speakers.append(sp)
        return sp

    def _finished(self):
        self.finished += 1

    def wait(self, until, timeout=60.0) -> float:
        """Runs Qt's loop until until() holds; the longest the main thread was kept from running, in seconds."""
        deadline, last, gap = time.monotonic() + timeout, time.monotonic(), 0.0
        while not until():
            if time.monotonic() > deadline:
                self.fail(f"nestihlo se; log: {self.records.lines[-8:]}")
            APP.processEvents()
            time.sleep(0.001)
            now = time.monotonic()
            gap, last = max(gap, now - last), now
        return gap

    def logged(self, text):
        return any(text in line for line in self.records.lines)

    def test_loading_never_blocks_this_process(self):
        self.speaker()
        gap = self.wait(lambda: self.logged("načten"))
        # in Orbit's process the load held the GIL for 1.6–6 s; well under 50 ms now, more only on a PC at 100 %
        self.assertLess(gap, 0.5)
        self.assertNotIn("onnxruntime", sys.modules)

    def test_says_a_text_and_finishes(self):
        sp = self.speaker()
        sp.say("Hotovo, testy prošly.")
        self.assertTrue(sp.speaking)
        self.wait(lambda: self.finished == 1)
        self.assertFalse(sp.speaking)
        played = [line for line in self.records.lines if "stream-played" in line]
        self.assertEqual(len(played), 1)
        self.assertGreater(int(played[0].split()[-1]), 22050)  # more than a second of speech at 22.05 kHz

    def test_stop_is_heard_at_once(self):
        sp = self.speaker()
        sp.say(LONG)
        sp.say(LONG)  # queued behind it: dropped by the same stop
        self.wait(lambda: self.logged("stream-start"))
        time.sleep(0.5)
        t0 = time.monotonic()
        sp.stop()
        self.wait(lambda: self.finished == 2, timeout=5)
        # within 0.1 s while it plays; a sentence being synthesized finishes first (~0.2 s, more on a busy PC)
        self.assertLess(time.monotonic() - t0, 2)
        self.assertTrue(self.logged("stream-abort"))
        sp.say("A ještě tohle.")  # after a stop the next text is said
        self.wait(lambda: self.finished == 3)
        self.assertEqual(sum("stream-played" in line for line in self.records.lines), 2)

    def test_a_crash_ends_the_text_and_the_next_one_starts_it_again(self):
        sp = self.speaker()
        sp.say(LONG)
        self.wait(lambda: self.logged("stream-start"))
        sp._proc.kill()
        self.wait(lambda: self.finished == 1, timeout=10)
        self.assertTrue(self.logged("proces skončil"))
        sp.say("Znovu.")
        self.wait(lambda: self.finished == 2)
        self.assertGreaterEqual(sum("stream-played" in line for line in self.records.lines), 1)

    def test_another_voice_closes_the_first_process(self):
        first = self.speaker()
        first.say(LONG)
        self.wait(lambda: self.logged("stream-start"))
        proc = first._proc
        self.speaker()  # what main does when the voice changes
        self.assertEqual(self.finished, 1)  # the text that was playing counts as finished
        deadline = time.monotonic() + 5
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIsNotNone(proc.poll())


class Paths(unittest.TestCase):
    def test_non_ascii_folder_gets_its_8_3_name(self):
        top = Path(tempfile.mkdtemp(prefix="orbit-test-"))
        self.addCleanup(shutil.rmtree, top, True)
        folder = top / "Jiří Nový" / "espeak-ng-data"
        folder.mkdir(parents=True)
        path = voice._ascii_path(folder)
        if path is None:
            self.skipTest("8.3 jména jsou na tomhle disku vypnutá")
        self.assertTrue(path.isascii())
        self.assertTrue(Path(path).samefile(folder))

    def test_ascii_folder_stays(self):
        self.assertEqual(voice._ascii_path(Path(r"C:\Windows\System32")), r"C:\Windows\System32")

    def test_effective_skips_windows_for_a_downloaded_piper_voice(self):
        saved = voice.PIPER_DIR, voice.windows_czech
        voice.PIPER_DIR = REAL_PIPER
        voice.windows_czech = lambda: self.fail("windows_czech() se neměl ptát")
        try:
            if voice.piper_installed() and voice.downloaded(MODEL):
                self.assertEqual(voice.effective(MODEL), MODEL)
        finally:
            voice.PIPER_DIR, voice.windows_czech = saved


if __name__ == "__main__":
    unittest.main()
