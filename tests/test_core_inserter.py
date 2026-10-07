"""inserter.py with a fake clipboard and no keys sent: the clipboard backup keeps a password manager's marks, the
restored content stays out of Windows' clipboard history, and the Enter after "Odešli" only goes to the same window.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import inspect
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
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # and the real clipboard is replaced below anyway

from PySide6.QtCore import QMimeData  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from app import inserter  # noqa: E402

APP = QGuiApplication.instance() or QGuiApplication([])
EXCLUDE = 'application/x-qt-windows-mime;value="ExcludeClipboardContentFromMonitorProcessing"'


class FakeClipboard:
    def __init__(self, data: QMimeData | None):
        self.data, self.set = data, []

    def mimeData(self):
        return self.data

    def setMimeData(self, md):
        self.set.append(md)
        self.data = md

    def text(self):
        return self.data.text() if self.data else ""

    def clear(self):
        self.data = None


class Clipboard(unittest.TestCase):
    def setUp(self):
        self.saved = inserter.QGuiApplication
        password = QMimeData()
        password.setText("heslo123")
        password.setData(EXCLUDE, b"")  # KeePass-style: the mark without data
        self.cb = FakeClipboard(password)
        cb = self.cb

        class FakeApp:
            @staticmethod
            def clipboard():
                return cb

        inserter.QGuiApplication = FakeApp

    def tearDown(self):
        inserter.QGuiApplication = self.saved

    def test_restore_stays_out_of_history(self):
        ins = inserter.Inserter()
        ins._saved = ins._snapshot()
        self.assertIn(EXCLUDE, ins._saved.formats())  # the empty mark survives the backup
        dictated = QMimeData()
        dictated.setText("nadiktovaný text")
        self.cb.data, ins._ours = dictated, "nadiktovaný text"
        ins._restore()
        restored = self.cb.set[-1]
        self.assertEqual(restored.text(), "heslo123")
        for fmt, data in inserter._NO_HISTORY.items():
            self.assertTrue(restored.hasFormat(fmt), fmt)
            self.assertEqual(bytes(restored.data(fmt)), data)

    def test_user_copied_meanwhile_stays(self):
        ins = inserter.Inserter()
        ins._saved, ins._ours = ins._snapshot(), "nadiktovaný text"
        new = QMimeData()
        new.setText("něco nového")
        self.cb.data = new
        ins._restore()
        self.assertEqual(self.cb.set, [])


class Press(unittest.TestCase):
    def setUp(self):
        self.saved = inserter.foreground, inserter._send
        self.sent = []
        inserter._send = lambda events: self.sent.append(len(events)) or True

    def tearDown(self):
        inserter.foreground, inserter._send = self.saved

    def run_press(self, windows, text="Ahoj."):
        it = iter(windows)
        inserter.foreground = lambda: next(it)
        skipped = []
        ins = inserter.Inserter()
        # an older copy (ORBIT_TEST_ROOT) has no callback
        has_callback = "on_skipped" in inspect.signature(ins.press).parameters
        extra = {"on_skipped": lambda: skipped.append(True)} if has_callback else {}
        ins.press("send", after_text=text, **extra)
        deadline = time.monotonic() + 3
        while not (self.sent or skipped) and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.01)
        return skipped

    def test_enter_into_the_same_window(self):
        self.assertEqual(self.run_press([0x111, 0x111]), [])
        self.assertEqual(self.sent, [2])

    def test_no_enter_after_switching_window(self):
        self.assertEqual(self.run_press([0x111, 0x222]), [True])
        self.assertEqual(self.sent, [])

    def test_no_esc_after_switching_window(self):
        self.assertEqual(self.run_press([0x111, 0x222], text=""), [True])
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
