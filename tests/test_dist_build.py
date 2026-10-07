"""build_installer.py and installer/orbit.iss: the bundle's Python packages come only from the hash-pinned lock, a PFX
password never goes into a command line, and an update doesn't delete the interpreter Claude Code runs for Orbit's
hooks and status line. No network, no installer run (ISCC only compiles a tiny fake bundle into a temp folder).

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_dist*.py"
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))

import build_installer as b  # noqa: E402

ISS = ROOT / "installer" / "orbit.iss"
ISCC = ROOT / "build" / "tools" / "InnoSetup" / "ISCC.exe"


class Lock(unittest.TestCase):
    def test_lock_parses(self):
        pins = b.read_lock()
        self.assertGreaterEqual(len(pins), 15)
        self.assertEqual(len({b.canon(name) for name, _, _, _ in pins}), len(pins))  # each package once
        for name, version, sha, _ in pins:
            self.assertRegex(sha, r"^[0-9a-f]{64}$", name)

    def test_lock_matches_requirements(self):
        # fails when requirements.txt changes without --update-lock
        pinned = {b.canon(n): v for n, v, _, _ in b.read_lock()}
        for line in b.requirements(False):
            name, _, version = line.partition("==")
            self.assertEqual(pinned.get(b.canon(name)), version.strip(), line)
        lines = b.locked_requirements(False)
        self.assertEqual(len(lines), len(pinned))
        self.assertTrue(all(re.fullmatch(r"\S+==\S+ --hash=sha256:[0-9a-f]{64}", line) for line in lines))

    def test_without_piper_drops_what_only_piper_needs(self):
        names = {b.canon(line.split("==")[0]) for line in b.locked_requirements(True)}
        piper_only = {b.canon(n) for n, _, _, piper in b.read_lock() if piper}
        self.assertTrue({"piper-tts", "onnxruntime"} <= piper_only)
        self.assertFalse(names & piper_only)
        self.assertTrue({"numpy", "pyside6", "requests", "urllib3", "certifi"} <= names)

    def test_requirement_not_in_lock_stops(self):
        for reqs in (["numpy==9.9.9"], ["something-new==1.0"]):
            with mock.patch.object(b, "requirements", return_value=reqs), self.assertRaises(SystemExit) as e:
                b.locked_requirements(False)
            self.assertIn("--update-lock", str(e.exception))

    def test_bad_lock_line_stops(self):
        with self.assertRaises(SystemExit):
            b.read_lock("numpy==2.5.3 sha256:abc\n")

    def test_pip_installs_only_the_lock(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(b, "CACHE", Path(tmp)), \
                mock.patch.object(b.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            b.install_packages(Path(tmp, "site"), without_piper=True)
            cmd = run.call_args.args[0]
            req_file = Path(cmd[cmd.index("-r") + 1]).read_text(encoding="utf-8")
        for flag in ("--require-hashes", "--no-deps", "--only-binary=:all:", "--target"):
            self.assertIn(flag, cmd)
        self.assertNotIn("onnxruntime", req_file)
        self.assertEqual(req_file.count("--hash=sha256:"), len(b.locked_requirements(True)))

    def test_update_lock_rewrites_only_the_block(self):
        full = {"numpy": ("2.5.3", "a" * 64), "piper-tts": ("1.8.0", "b" * 64), "PySide6_Addons": ("6.11.2", "c" * 64)}
        core = {"numpy": ("2.5.3", "a" * 64), "PySide6_Addons": ("6.11.2", "c" * 64)}
        resolve = mock.Mock(side_effect=lambda reqs: full if any("piper" in r for r in reqs) else core)
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp, "build_installer.py")
            shutil.copy2(b.__file__, script)
            before = script.read_text(encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(b, "resolve", resolve), contextlib.redirect_stdout(out):
                b.update_lock(script)
                b.update_lock(script)
            after = script.read_text(encoding="utf-8")
        block = re.search(r'(?ms)^BUNDLE_LOCK = """(.*?)^"""', after)
        self.assertEqual(b.read_lock(block[1]), [("numpy", "2.5.3", "a" * 64, False),
                                                 ("piper-tts", "1.8.0", "b" * 64, True),
                                                 ("PySide6_Addons", "6.11.2", "c" * 64, False)])
        old = re.search(r'(?ms)^BUNDLE_LOCK = """(.*?)^"""', before)
        self.assertEqual(before[:old.start()], after[:block.start()])
        self.assertEqual(before[old.end():], after[block.end():])
        self.assertTrue(out.getvalue().strip().splitlines()[-1].endswith("beze změny"))


class Signing(unittest.TestCase):
    PASSWORD = "tajne-heslo-123"

    def command(self, **env):
        clean = {k: v for k, v in os.environ.items() if not k.startswith("ORBIT_SIGN")}
        with mock.patch.dict(os.environ, {**clean, "ORBIT_SIGNTOOL": r"C:\sdk\signtool.exe", **env}, clear=True):
            return b.sign_command()

    def test_pfx_password_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            self.command(ORBIT_SIGN_PFX=r"C:\cert.pfx", ORBIT_SIGN_PASSWORD=self.PASSWORD)
        self.assertIn("ORBIT_SIGN_THUMBPRINT", str(e.exception))
        self.assertNotIn(self.PASSWORD, str(e.exception))

    def test_commands_never_carry_a_password(self):
        pfx = self.command(ORBIT_SIGN_PFX=r"C:\cert.pfx")
        self.assertIn('/f $qC:\\cert.pfx$q', pfx)
        self.assertNotIn("/p ", pfx)
        thumb = self.command(ORBIT_SIGN_THUMBPRINT="ab" * 20, ORBIT_SIGN_PASSWORD=self.PASSWORD)
        self.assertIn("/sha1 " + "ab" * 20, thumb)
        self.assertNotIn(self.PASSWORD, thumb)
        self.assertIsNone(self.command())
        self.assertEqual(self.command(ORBIT_SIGN_COMMAND="sign $f"), "sign $f")


def section(text: str, name: str) -> str:
    m = re.search(rf"(?ms)^\[{name}\]\n(.*?)(?=^\[\w+\]\n|\Z)", text)
    return m[1] if m else ""


class Installer(unittest.TestCase):
    def setUp(self):
        self.iss = ISS.read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_update_keeps_the_interpreter_of_the_hooks(self):
        deleted = re.findall(r'^Type: \w+; Name: "([^"]+)"', section(self.iss, "InstallDelete"), re.M)
        self.assertNotIn(r"{app}\runtime", deleted)  # python.exe and the stdlib stay for Claude Code's hooks
        self.assertIn(r"{app}\runtime\Lib", deleted)  # packages are still replaced whole
        self.assertEqual(deleted[-1], r"{app}\app")
        self.assertIn("BeforeInstall: MoveAsideIfInUse", section(self.iss, "Files"))
        self.assertRegex(section(self.iss, "Code"), r"procedure MoveAsideIfInUse;")
        uninstall = section(self.iss, "UninstallDelete")
        self.assertIn(r'Name: "{app}\runtime"', uninstall)  # *.orbit-old leftovers go with the uninstall

    @unittest.skipUnless(ISCC.exists(), "Inno Setup is not in build/tools")
    def test_script_compiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp, "src"), Path(tmp, "out")
            for f in ("runtime/python.exe", "runtime/Lib/site-packages/a.py", "app/cc_hook.py", "Orbit.pyw"):
                Path(src, f).parent.mkdir(parents=True, exist_ok=True)
                Path(src, f).write_text("x", encoding="utf-8")
            Path(src, "assets").mkdir()
            shutil.copy2(ROOT / "assets" / "orbit.ico", src / "assets")
            r = subprocess.run([str(ISCC), "/Qp", "/DAppVersion=0.0.0", f"/DSourceDir={src}", f"/DOutputDir={out}",
                                str(ISS)], capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(any(out.glob("*.exe")))  # never run: the temp folder goes away with it


if __name__ == "__main__":
    unittest.main()
