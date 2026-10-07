"""config.py with config.json locked by another program (a share-nothing handle, like an antivirus or a backup tool).

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import ctypes
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from ctypes import wintypes
from pathlib import Path

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import config  # noqa: E402

assert "orbit-test-" in str(config.CONFIG_PATH), config.CONFIG_PATH

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                             wintypes.DWORD, wintypes.HANDLE]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def lock(path: Path, seconds: float) -> threading.Thread:
    """Opens the file with no sharing at all for a while."""
    handle = _k32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)  # GENERIC_READ, no share, OPEN_EXISTING
    assert handle and handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    t = threading.Thread(target=lambda: (time.sleep(seconds), _k32.CloseHandle(handle)))
    t.start()
    return t


class Locked(unittest.TestCase):
    def setUp(self):
        self.saved = getattr(config, "READ_TRIES", None), getattr(config, "READ_PAUSE_S", None)  # None: older copy
        config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg = dict(config.DEFAULTS, vocabulary="Comgate, HHW Hommel Hercules", replacements=[["comgit", "Comgate"]])
        config.CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.original = config.CONFIG_PATH.read_bytes()

    def tearDown(self):
        if self.saved[0] is not None:
            config.READ_TRIES, config.READ_PAUSE_S = self.saved
        config.readonly = False
        for bad in config.CONFIG_PATH.parent.glob("config.json.bad-*"):
            bad.unlink()

    def test_locked_for_a_second_is_waited_for(self):
        t = lock(config.CONFIG_PATH, 1.0)
        cfg = config.load()
        t.join()
        self.assertEqual(cfg["vocabulary"], "Comgate, HHW Hommel Hercules")
        self.assertEqual(config.problem, "")

    def test_locked_for_long_is_never_overwritten(self):
        config.READ_TRIES, config.READ_PAUSE_S = 3, 0.05  # gives up long before the lock ends
        t = lock(config.CONFIG_PATH, 1.0)
        cfg = config.load()
        self.assertEqual(cfg["vocabulary"], "")  # the defaults for this run
        self.assertTrue(config.problem)
        t.join()
        config.save(cfg)  # what main does right after the start
        self.assertEqual(config.CONFIG_PATH.read_bytes(), self.original)

    def test_corrupt_file_is_kept_aside_and_then_replaced(self):
        config.CONFIG_PATH.write_text("{nope", encoding="utf-8")
        cfg = config.load()
        self.assertIn("config.json.bad-", config.problem)
        config.save(cfg)  # a copy exists, so saving is fine (as before)
        self.assertEqual(json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))["vocabulary"], "")


if __name__ == "__main__":
    unittest.main()
