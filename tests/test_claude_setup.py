"""claude_setup: the Claude Code check runs `--version` alongside `auth status` (not one after the other), and a
claude found only in the current folder is never used. No real claude.exe runs (_run is replaced).

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_claude*.py"
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import claude_setup  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DELAY = 0.4


def fake_run(args, timeout):
    time.sleep(DELAY)
    out = "2.1.292 (Claude Code)" if "--version" in args else \
        '{"loggedIn": true, "authMethod": "claude.ai", "subscriptionType": "max", "email": "a@b.cz"}'
    return subprocess.CompletedProcess(args, 0, out, "")


class Status(unittest.TestCase):
    def test_both_at_once(self):
        with mock.patch.object(claude_setup, "find_exe", return_value=r"C:\fake\claude.exe"), \
                mock.patch.object(claude_setup, "_run", side_effect=fake_run):
            start = time.perf_counter()
            s = claude_setup.status()
            took = time.perf_counter() - start
        self.assertLess(took, 1.6 * DELAY)  # one after the other would be 2 × DELAY
        self.assertEqual((s.version, s.logged_in, s.plan, s.error), ("2.1.292", True, "max", ""))
        self.assertTrue(s.connected)

    def test_auth_status_timeout_keeps_the_version(self):
        def run(args, timeout):
            if "auth" in args:
                raise subprocess.TimeoutExpired(args, timeout)
            return fake_run(args, timeout)

        with mock.patch.object(claude_setup, "find_exe", return_value=r"C:\fake\claude.exe"), \
                mock.patch.object(claude_setup, "_run", side_effect=run):
            s = claude_setup.status()
        self.assertEqual((s.installed, s.version, s.error), (True, "2.1.292", "Claude Code neodpovídá."))
        self.assertFalse(s.connected)

    def test_not_installed(self):
        with mock.patch.object(claude_setup, "find_exe", return_value=None), \
                mock.patch.object(claude_setup, "_run") as run:
            self.assertFalse(claude_setup.status().installed)
        run.assert_not_called()


class Candidates(unittest.TestCase):
    def test_never_from_the_current_folder(self):
        """A claude.cmd and node_modules\\…\\claude.exe planted in the folder Orbit runs in, with
        NoDefaultCurrentDirectoryInExePath unset (Claude Code sets it for its own children, Orbit.pyw doesn't)."""
        folder = Path(tempfile.mkdtemp(prefix="orbit-test-cwd-"))
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "claude.cmd").write_text("@echo planted\r\n", encoding="ascii")
        planted = folder / claude_setup._NPM_EXE
        planted.parent.mkdir(parents=True)
        planted.write_bytes(b"MZ")
        env = {k: v for k, v in os.environ.items() if k.lower() != "nodefaultcurrentdirectoryinexepath"}
        code = ("import sys; sys.path.insert(0, sys.argv[1]); from app import claude_setup; "
                "import json; print(json.dumps([str(p) for p in claude_setup._candidates()]))")
        out = subprocess.run([sys.executable, "-c", code, str(ROOT)], cwd=folder, env=env, capture_output=True,
                             text=True, encoding="utf-8", check=True).stdout
        candidates = json.loads(out)
        self.assertTrue(candidates)
        self.assertTrue(all(os.path.isabs(p) for p in candidates), candidates)
        self.assertFalse(any("claude-code" in p and str(folder).lower() in os.path.abspath(p).lower()
                             for p in candidates), candidates)


if __name__ == "__main__":
    unittest.main()
