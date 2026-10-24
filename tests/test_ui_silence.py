"""A dictation the mic didn't hear (13. 10. twice: it beeped at the start and the end, nothing was typed, nothing in
the history): main.Dictation says so on a stub, while the key is still held (DEAF_WARN_S of nothing, not even the
start beep) and after the release, and the Recorder tells a mic sending only its hiss from one that heard something.

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

import numpy as np

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import history, main, recorder  # noqa: E402
from app.whisper_server import SAMPLE_RATE  # noqa: E402

BLOCK = SAMPLE_RATE * 30 // 1000
rng = np.random.default_rng(13)


def hiss(seconds=1.0):
    """What a muted SoloCast sends: its own noise, RMS ~0.5 (the quietest blocks of Pepa's recordings), not zeros."""
    return rng.integers(-1, 2, int(seconds * SAMPLE_RATE)).astype(np.int16)


def beep(seconds=0.06, rms=400):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (rms * np.sqrt(2) * np.sin(2 * np.pi * 880 * t)).astype(np.int16)


def feed(rec, audio):
    for i in range(0, len(audio) // BLOCK * BLOCK, BLOCK):
        rec._callback(audio[i:i + BLOCK].reshape(-1, 1), BLOCK, None, None)


class RecorderHearsTest(unittest.TestCase):
    def recording(self):
        rec = recorder.Recorder()
        rec._recording = True  # as start() leaves it, without a stream
        return rec

    def test_only_hiss(self):
        rec = self.recording()
        feed(rec, hiss(5))
        self.assertTrue(rec.got_signal)  # not zeros: the old "jen nuly" message never came
        self.assertEqual(rec.voiced_s, 0)
        self.assertLess(rec.peak, 5)
        self.assertTrue(recorder.is_silent(hiss(5), rec.noise))

    def test_the_start_beep_counts(self):
        rec = self.recording()
        feed(rec, np.concatenate([hiss(0.12), beep(), hiss(3)]))
        self.assertGreater(rec.voiced_s, 0)
        self.assertGreater(rec.peak, 300)

    def test_a_new_recording_starts_from_nothing(self):
        rec = self.recording()
        feed(rec, beep())
        rec._recording = False
        rec._stream = SimpleNamespace(active=True)  # the meter's stream: start() keeps it
        rec.start()
        self.assertEqual((rec.peak, rec.voiced_s, rec.got_signal), (0.0, 0, False))


class FakeRecorder:
    def __init__(self, audio=None, got_signal=True, voiced_s=0.0, peak=2.0):
        self.audio = audio if audio is not None else hiss(5)
        self.got_signal, self.voiced_s, self.peak, self.noise = got_signal, voiced_s, peak, 0.5
        self.active = self.live = True

    def stop(self):
        self.active = self.live = False
        return self.audio

    def pop_pieces(self):
        return []


class Timer:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def isActive(self):
        return self.running


class Stub:
    _tell_silence = main.Dictation._tell_silence
    _watch_recording = main.Dictation._watch_recording
    _finish_recording = main.Dictation._finish_recording
    _queue_piece = main.Dictation._queue_piece
    _transcribe_piece = _finish_take = None  # only handed to _submit
    _follow_pointer = lambda self: None  # the window under the mouse (test_ui_pointer)

    def __init__(self, rec=None, agent=False):
        self.recorder = rec or FakeRecorder()
        self.take = main.Take("", agent)
        self.cfg = {"sounds": False, "muted": False, "replacements": [], "voice_commands": True,
                    "keep_recordings": False, "learn_vocabulary": False}
        self.notes, self.feed, self.submitted = [], [], []
        self.history = history.History(persist=False)
        self.ducker = SimpleNamespace(restore=lambda: None)
        self.live_timer, self.listen_timer, self.stop_timer, self.watch_timer = Timer(), Timer(), Timer(), Timer()
        self.ptt = self.agent_ptt = None
        self._desktop_ok = False
        self._recording_since = time.monotonic()
        self._hands_free = False
        self._agent_state = "listening"
        self.pending = 0

    def _notify(self, msg, error=False, title="Orbit", **_):
        self.notes.append((msg, error, title))

    def _feed_update(self, **changes):
        self.feed.append(changes)

    def _submit(self, fn, *args):
        self.submitted.append(fn)

    def _agent_rest(self):
        return "idle"

    def refresh(self):
        pass


class TellSilenceTest(unittest.TestCase):
    def test_only_the_mics_hiss(self):
        stub = Stub()
        stub._tell_silence(False)
        [(msg, error, title)] = stub.notes
        self.assertTrue(error)
        self.assertEqual(title, "Diktování")
        self.assertIn("nic nezachytil", msg)
        self.assertIn("ztlumený přímo na mikrofonu", msg)

    def test_zeros(self):
        stub = Stub(FakeRecorder(got_signal=False))
        stub._tell_silence(False)
        self.assertIn("přístup k mikrofonu", stub.notes[0][0])
        self.assertTrue(stub.notes[0][1])

    def test_too_quiet(self):
        stub = Stub(FakeRecorder(voiced_s=0.8, peak=150))
        stub._tell_silence(False)
        [(msg, error, _)] = stub.notes
        self.assertIn("moc potichu", msg)
        self.assertFalse(error)  # something was heard

    def test_a_beep_or_a_click_only(self):
        stub = Stub(FakeRecorder(voiced_s=0.06, peak=400))  # a working mic, nothing said
        stub._tell_silence(False)
        self.assertEqual(stub.notes, [])

    def test_the_agent_hears_it_in_the_panel(self):
        stub = Stub(agent=True)
        stub._tell_silence(True)
        self.assertEqual(stub.notes, [])
        self.assertIn("nic nezachytil", stub.feed[0]["reply"])


class WhileHeldTest(unittest.TestCase):
    def test_said_once_after_two_seconds_of_nothing(self):
        stub = Stub()
        stub._watch_recording()
        self.assertEqual(stub.notes, [])  # just started: the user may not have said a word yet
        stub._recording_since -= main.DEAF_WARN_S
        stub._watch_recording()
        stub._watch_recording()
        [(msg, error, _)] = stub.notes
        self.assertIn("Mikrofon nic neslyší.", msg)
        self.assertTrue(error)

    def test_not_when_something_came(self):
        stub = Stub(FakeRecorder(voiced_s=0.06, peak=400))  # the start beep: the mic hears
        stub._recording_since -= 10
        stub._watch_recording()
        self.assertEqual(stub.notes, [])

    def test_not_before_audio_flows(self):
        stub = Stub()
        stub.recorder.live = False  # the headset's start-up zeros, LIVE_FALLBACK_MS not over yet
        stub._recording_since -= 10
        stub._watch_recording()
        self.assertEqual(stub.notes, [])

    def test_the_agent(self):
        stub = Stub(agent=True)
        stub._recording_since -= main.DEAF_WARN_S
        stub._watch_recording()
        self.assertIn("Mikrofon nic neslyší.", stub.feed[0]["reply"])


class AfterReleaseTest(unittest.TestCase):
    def test_a_dictation_into_a_muted_mic(self):
        """13. 10. 10:08: 9.9 s, signal yes, nothing above the noise: no text, no history, and now a bubble."""
        stub = Stub(FakeRecorder(audio=hiss(9.9)))
        stub._finish_recording()
        self.assertEqual(stub.submitted, [])  # nothing for Whisper
        self.assertIsNone(stub.take)
        self.assertIsNone(stub.history.last())
        [(msg, error, _)] = stub.notes
        self.assertIn("nic nezachytil", msg)
        self.assertTrue(error)

    def test_a_short_press_says_nothing(self):
        stub = Stub(FakeRecorder(audio=hiss(main.SILENT_TELL_S - 0.5)))
        stub._finish_recording()
        self.assertEqual(stub.notes, [])

    def test_speech_goes_to_whisper(self):
        speech = np.concatenate([hiss(0.5), beep(1.0, rms=2000), hiss(0.5)])
        stub = Stub(FakeRecorder(audio=speech, voiced_s=1.0, peak=2000))
        stub._finish_recording()
        self.assertEqual(stub.notes, [])
        self.assertEqual(len(stub.submitted), 2)  # the piece, then the take


if __name__ == "__main__":
    unittest.main()
