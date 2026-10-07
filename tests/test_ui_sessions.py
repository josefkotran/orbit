"""sessions._title_lines reads a transcript backwards: the same title as a forward read of the whole file, also with
lines across block borders.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_ui*.py"
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

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import sessions  # noqa: E402


def forward(path) -> str:  # the old way: every line of the file
    with open(path, "rb") as f:
        return sessions._topic([line for line in f if b'"ai-title"' in line])


class TitleTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="orbit-title-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.block = sessions.TITLE_BLOCK
        sessions.TITLE_BLOCK = 1000  # many block borders in a small file
        self.addCleanup(setattr, sessions, "TITLE_BLOCK", self.block)

    def write(self, lines) -> Path:
        path = self.dir / "t.jsonl"
        path.write_bytes(b"".join(json.dumps(x, ensure_ascii=False).encode() + b"\r\n" for x in lines))
        return path

    def test_same_title_as_forward(self):
        filler = [{"type": "user", "text": "x" * (37 * i % 900)} for i in range(200)]
        cases = [
            [{"type": "ai-title", "aiTitle": "Katalog z Německa"}] + filler,
            filler[:50] + [{"type": "ai-title", "aiTitle": "První"}] + filler + [{"type": "ai-title", "aiTitle": "Druhé"}],
            filler + [{"type": "ai-title", "aiTitle": "Na konci"}],
            filler[:120] + [{"type": "ai-title", "aiTitle": "Dlouhé " + "y" * 3000}] + filler[:80],
            filler,
        ]
        for lines in cases:
            path = self.write(lines)
            self.assertEqual(sessions._topic(sessions._title_lines(str(path))), forward(path))
        self.assertEqual(sessions._title_lines(str(self.dir / "missing.jsonl")), [])
        (self.dir / "empty.jsonl").write_bytes(b"")
        self.assertEqual(sessions._title_lines(str(self.dir / "empty.jsonl")), [])

    def test_broken_newest_title_falls_back(self):
        path = self.dir / "t.jsonl"
        path.write_bytes('{"type":"ai-title","aiTitle":"Starý"}\n'.encode() + b'{"type":"user"}\n' * 300 +
                         b'{"type":"ai-title","aiTitle":\n')
        self.assertEqual(sessions._topic(sessions._title_lines(str(path))), "Starý")


if __name__ == "__main__":
    unittest.main()
