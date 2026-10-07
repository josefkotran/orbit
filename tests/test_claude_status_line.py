"""cc_status.py and agent_tools.py look up git, pwsh and claude by bare name: never in the current folder (the
session's project, maybe a cloned repo), also when whoever started them didn't set NoDefaultCurrentDirectoryInExePath.
Each runs in its own Python with that variable removed, in a folder holding planted git.cmd, pwsh.cmd and claude.cmd.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_claude*.py"
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHECK = """
import json, os, shutil, sys
sys.path.insert(0, sys.argv[1])
if sys.argv[2] == "cc_status":
    sys.path.insert(0, os.path.join(sys.argv[1], "app"))
    import cc_status
    found = {"pwsh": cc_status._powershell(), "bash": cc_status._git_bash()}
else:
    from app import agent_tools  # noqa
    found = {}
found.update({name: shutil.which(name) for name in ("git", "pwsh", "claude")})
print(json.dumps(found))
"""


class NotFromTheCurrentFolder(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="orbit-test-cwd-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        data = Path(tempfile.mkdtemp(prefix="orbit-test-data-"))
        self.addCleanup(shutil.rmtree, data, True)
        for name in ("git", "pwsh", "claude"):
            (self.folder / f"{name}.cmd").write_text("@echo planted\r\n", encoding="ascii")
        self.env = {k: v for k, v in os.environ.items() if k.lower() != "nodefaultcurrentdirectoryinexepath"}
        self.env.update(ORBIT_DATA_DIR=str(data / "data"), ORBIT_CLAUDE_DIR=str(data / "claude"))

    def lookups(self, module: str) -> dict:
        out = subprocess.run([sys.executable, "-c", CHECK, str(ROOT), module], cwd=self.folder, env=self.env,
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        return json.loads(out)

    def check(self, module: str) -> None:
        for name, path in self.lookups(module).items():
            if path:
                self.assertTrue(os.path.isabs(path), f"{module}: {name} -> {path}")
                self.assertNotEqual(os.path.normcase(os.path.dirname(os.path.abspath(path))),
                                    os.path.normcase(str(self.folder)), f"{module}: {name} -> {path}")

    def test_cc_status(self):
        self.check("cc_status")

    def test_agent_tools(self):
        self.check("agent_tools")

    def test_planted_files_would_be_found_otherwise(self):
        """The test itself: without the modules, plain which() does take the planted files."""
        code = "import json, shutil; print(json.dumps(shutil.which('pwsh')))"
        out = subprocess.run([sys.executable, "-c", code], cwd=self.folder, env=self.env, capture_output=True,
                             text=True, encoding="utf-8", check=True).stdout
        self.assertEqual(Path(json.loads(out)).name.lower(), "pwsh.cmd")


if __name__ == "__main__":
    unittest.main()
