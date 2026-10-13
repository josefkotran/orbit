"""ducking.py on pretend audio sessions: what gets muted or turned down while the microphone is open (not Orbit, not
Windows' system sounds, not what the user muted), that only what Orbit set is put back, and that a run that died
mid-dictation gets put back by the next start. (Core Audio itself was tried on a real session, see CLAUDE.md.)

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

from app import config, ducking  # noqa: E402

ORBIT = 100


class Session:
    def __init__(self, pid, volume=1.0, muted=False, system=False, run=1):
        self.pid, self.volume, self.muted, self.system = pid, volume, muted, system
        self.group, self.id = f"app{pid}", f"app{pid}#{run}"

    def set_volume(self, value):
        self.volume = value

    def set_mute(self, on):
        self.muted = on


class Audio:
    def __init__(self, sessions):
        self.list = sessions

    def sessions(self, use):
        use(self.list)


class Ducking(unittest.TestCase):
    def setUp(self):
        self.state = config.DATA_DIR / "ducked.json"
        self.state.unlink(missing_ok=True)
        self.music, self.video = Session(1), Session(2, volume=0.5)
        self.audio = Audio([self.music, self.video, Session(ORBIT), Session(0, system=True),
                            Session(3, muted=True), Session(4, volume=0.0)])

    def ducker(self, audio=None):
        d = ducking.Ducker(self.state, audio or self.audio)
        self.addCleanup(d._pool.shutdown)
        self.addCleanup(lambda: d._timer and d._timer.cancel())
        return d

    def wait(self, d):
        d._pool.submit(lambda: None).result()

    def retry(self, d):
        """What the timer does after RETRY_S, at once."""
        d._pool.submit(d._retry).result()

    def test_only_other_programs_and_back(self):
        d = self.ducker()
        d.duck(ducking.MUTE, {ORBIT})
        self.wait(d)
        self.assertEqual([s.muted for s in self.audio.list], [True, True, False, False, True, False])
        self.assertTrue(self.state.exists())  # the way back is on disk while it's muted
        d.restore()
        self.wait(d)
        self.assertEqual([s.muted for s in self.audio.list], [False, False, False, False, True, False])
        self.assertFalse(self.state.exists())

    def test_lower_to_a_fifth_of_its_own_volume(self):
        d = self.ducker()
        d.duck(ducking.LOWER, {ORBIT})
        self.wait(d)
        self.assertEqual((self.music.volume, self.video.volume), (0.2, 0.1))
        d.restore()
        self.wait(d)
        self.assertEqual((self.music.volume, self.video.volume), (1.0, 0.5))

    def test_keep_touches_nothing(self):
        d = self.ducker()
        d.duck(ducking.KEEP, {ORBIT})
        self.wait(d)
        self.assertEqual([s.volume for s in self.audio.list[:2]], [1.0, 0.5])
        self.assertFalse(self.state.exists())

    def test_what_the_user_changed_meanwhile_stays(self):
        d = self.ducker()
        d.duck(ducking.LOWER, {ORBIT})
        self.wait(d)
        self.music.volume = 0.7  # turned up by hand in the mixer during the dictation
        d.restore()
        self.wait(d)
        self.assertEqual((self.music.volume, self.video.volume), (0.7, 0.5))

    def test_a_second_recording_right_after_keeps_the_first_values(self):
        d = self.ducker()
        d.duck(ducking.LOWER, {ORBIT})
        d.duck(ducking.LOWER, {ORBIT})  # not a fifth of a fifth
        d.restore()
        self.wait(d)
        self.assertEqual(self.music.volume, 1.0)

    def test_the_next_start_puts_back_what_a_crash_left(self):
        d = self.ducker()
        d.duck(ducking.MUTE, {ORBIT})
        self.wait(d)  # ... and Orbit dies here; the music program runs on (or was started again)
        again = Audio([Session(1, muted=True, run=2), Session(2, muted=True)])
        d2 = self.ducker(again)
        d2.restore_leftover()
        self.wait(d2)
        self.assertEqual([s.muted for s in again.list], [False, False])
        self.assertFalse(self.state.exists())

    def test_shutdown_puts_it_back(self):
        d = ducking.Ducker(self.state, self.audio)
        d.duck(ducking.MUTE, {ORBIT})
        d.shutdown()
        self.assertFalse(self.music.muted)

    def test_a_program_that_stopped_playing_gets_its_sound_back_when_it_plays_again(self):
        # Windows remembers the mute per program and gives it to the program's next session: on 10 Oct Chrome's
        # audio process ended during a dictation and Chrome stayed muted from then on
        d = self.ducker()
        d.duck(ducking.MUTE, {ORBIT})
        self.wait(d)
        self.audio.list.remove(self.video)  # its session ended while it was muted
        d.restore()
        self.wait(d)
        self.assertFalse(self.music.muted)
        self.assertTrue(self.state.exists())  # still owed, over a restart too
        self.assertIsNotNone(d._timer)
        self.retry(d)  # not playing yet: nothing to put back, still owed
        self.assertTrue(self.state.exists())
        again = Session(2, muted=True, run=2)  # plays again, muted by Windows' memory
        self.audio.list.append(again)
        self.retry(d)
        self.assertFalse(again.muted)
        self.assertFalse(self.state.exists())
        self.assertIsNone(d._timer)  # nothing owed, no more looking

    def test_a_session_that_started_during_the_dictation_is_put_back_too(self):
        users = Session(1, muted=True, run=0)  # the same program, muted by the user before: stays muted
        self.audio.list.append(users)
        d = self.ducker()
        d.duck(ducking.MUTE, {ORBIT})
        self.wait(d)
        born = Session(1, muted=True, run=2)  # its sound restarted mid-dictation and came up muted
        self.audio.list.append(born)
        d.restore()
        self.wait(d)
        self.assertEqual((self.music.muted, born.muted, users.muted), (False, False, True))
        self.assertFalse(self.state.exists())

    def test_what_is_owed_waits_over_a_restart(self):
        d = ducking.Ducker(self.state, self.audio)
        d.duck(ducking.LOWER, {ORBIT})
        d._pool.submit(lambda: None).result()
        self.audio.list.remove(self.video)
        d.shutdown()
        self.assertEqual(self.music.volume, 1.0)
        again = Audio([Session(2, volume=0.1, run=2), Session(5, volume=0.1)])  # 5: never ducked, the user's
        d2 = self.ducker(again)
        d2.restore_leftover()
        self.wait(d2)
        self.assertEqual([s.volume for s in again.list], [0.5, 0.1])
        self.assertFalse(self.state.exists())

    def test_gives_up_after_a_week(self):
        d = self.ducker()
        d.duck(ducking.MUTE, {ORBIT})
        self.wait(d)
        self.audio.list.remove(self.video)
        d.restore()
        self.wait(d)
        d._owed[0].at -= ducking.GIVE_UP_S + 1
        self.retry(d)
        self.assertEqual(d._owed, [])
        self.assertFalse(self.state.exists())
        self.assertIsNone(d._timer)

    def test_program_name_for_the_log(self):
        group = ("{0.0.0.00000000}.{c60770bf}|\\Device\\HarddiskVolume3\\Program Files\\Google\\Chrome\\Application"
                 "\\chrome.exe%b{00000000-0000-0000-0000-000000000000}")
        self.assertEqual(ducking.program(group), "chrome.exe")


if __name__ == "__main__":
    unittest.main()
