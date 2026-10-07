"""Small things off Orbit's hot paths: the session panel repaints only when its rows change, and a kept recording
is written after the text is on its way to the window.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
"""
import atexit
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
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

from app import main, ui  # noqa: E402
from app.sessions import Session  # noqa: E402


class SessionRepaintTest(unittest.TestCase):
    def test_repaints_only_when_rows_change(self):
        calls = []
        button = SimpleNamespace(_sessions=[], _session_rows=[], _sessions_look=ui.FloatingButton._sessions_look,
                                 _relayout=lambda: calls.append("relayout"), _auto_align=lambda: None,
                                 update=lambda: calls.append("update"))

        def poll(state="working", context=0.31, message=""):
            return [Session(id="a", cwd="C:/m-tex", topic="Katalog", state=state, context_pct=context * 100,
                            message=message),
                    Session(id="b", cwd="C:/orbit", state="idle")]
        ui.FloatingButton.set_sessions(button, poll())
        self.assertEqual(calls, ["relayout", "update"])
        button._session_rows = [("row a", button._sessions[0]), ("row b", button._sessions[1])]  # as painted
        calls.clear()
        fresh = poll(message="nová odpověď")  # nothing the rows show
        ui.FloatingButton.set_sessions(button, fresh)
        self.assertEqual(calls, [])
        self.assertIs(button._session_rows[0][1], fresh[0])  # a click or tooltip sees the current session
        ui.FloatingButton.set_sessions(button, poll(context=0.314))  # still 31 %
        self.assertEqual(calls, [])
        ui.FloatingButton.set_sessions(button, poll(context=0.32))
        self.assertEqual(calls, ["update"])
        calls.clear()
        ui.FloatingButton.set_sessions(button, poll(state="done", context=0.32))
        self.assertEqual(calls, ["update"])


class SaveAfterTextTest(unittest.TestCase):
    def test_recording_is_saved_after_the_text_goes(self):
        order = []
        bridge = SimpleNamespace(text_ready=SimpleNamespace(emit=lambda *a: order.append("text")),
                                 agent_heard=SimpleNamespace(emit=lambda *a: order.append("agent")),
                                 transcribe_failed=SimpleNamespace(emit=lambda *a: order.append("failed")))
        d = SimpleNamespace(bridge=bridge, _save_recording=lambda audio, text: order.append(("save", text)))
        take = SimpleNamespace(error="", texts=["Ahoj."], raw=["Ahoj."], agent=False, audio=[np.zeros(160, np.int16)],
                               released_at=0.0, target=5, confirm_id=None)
        main.Dictation._finish_take(d, take, [], True, True, False)
        self.assertEqual(order, ["text", ("save", "Ahoj.")])
        order.clear()
        main.Dictation._finish_take(d, take, [], True, False, False)  # not kept
        self.assertEqual(order, ["text"])


if __name__ == "__main__":
    unittest.main()
