"""shells.py on pretend processes: a background shell of a Claude Code session is found by its command (Git Bash) or
its output file (PowerShell), and told apart: works, waits, a server somebody uses, a server nobody used for half an
hour, a shell that hangs. Servers and hung shells don't keep the session "pracuje"; stop requests go to the mod and
come back. (The real processes were tried on a live session, see CLAUDE.md.)

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
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

from app import shells  # noqa: E402

CLAUDE, SESSION, T0 = 10, "sess-1", 1_000_000.0
PHP = 'cd /c/web && "/c/xampp/php/php.exe" -S 127.0.0.1:8770 -t \'www\''


def bash_line(command: str) -> str:
    """The command line Claude Code starts a Git Bash command with (seen 11 Oct)."""
    script = ("source /c/Users/x/.claude/shell-snapshots/snapshot-bash-1.sh 2>/dev/null || true && eval '"
              + command.replace("'", "'\"'\"'") + "' < /dev/null && pwd -P >| /c/Temp/claude-1-cwd")
    return '"C:\\Program Files\\Git\\bin\\bash.exe" -c "' + script.replace('"', '\\"') + '"'


class Probe:
    """The processes, sockets and output files Watch sees."""

    def __init__(self):
        self.procs, self.started, self.cpu, self.lines = {}, {}, {}, {}
        self.sockets, self.outputs, self.killed = [], {}, []
        self.add(CLAUDE, 1, "claude.exe", T0 - 7200)

    def add(self, pid, parent, name, started, line="", cpu=0.0):
        self.procs[pid], self.started[pid], self.cpu[pid], self.lines[pid] = (parent, name), started, cpu, line

    def shell(self, pid, command, started, program=None, cpu=0.0):
        """A background Bash command: bash -c → MSYS bash → its program."""
        self.add(pid, CLAUDE, "bash.exe", started, bash_line(command))
        self.add(pid + 1, pid, "bash.exe", started)
        if program:
            self.add(pid + 2, pid + 1, program, started, cpu=cpu)

    def processes(self):
        return dict(self.procs)

    def times(self, pid):
        return (self.started[pid], self.cpu[pid]) if pid in self.procs else None

    def command_line(self, pid):
        return self.lines.get(pid, "")

    def tcp(self):
        return list(self.sockets)

    def output(self, session, task):
        return self.outputs.get(task)

    def kill(self, pid, created):
        self.killed.append(pid)
        self.procs.pop(pid, None)
        return True


def task(tid, command, what=""):
    return {"type": "shell", "id": tid, "command": command, "what": what or command[:40]}


class Watching(unittest.TestCase):
    def setUp(self):
        self.probe = Probe()
        self.watch = shells.Watch(self.probe)

    def look(self, tasks, at):
        return {s.task: s for s in self.watch.look(SESSION, CLAUDE, tasks, now=T0 + at)}

    def test_found_by_its_command_with_quotes_and_by_its_output_file(self):
        self.probe.shell(20, PHP, T0 - 3000, "php.exe")
        self.probe.add(30, CLAUDE, "cmd.exe", T0 - 100, 'C:\\WINDOWS\\System32\\cmd.exe /d /s /c ""powershell.exe" '
                       '-Command "…" > "C:\\Temp\\claude\\C--web\\sess-1\\tasks\\pwsh0001.output" 2>&1"')
        self.probe.shell(40, "npm test", T0 - 50)  # a command no task asked for: a foreground one
        found = self.watch._sample(SESSION, CLAUDE, [task("php00001", PHP), task("pwsh0001", "Start-Sleep 600")],
                                   T0)
        self.assertEqual([s.kind for s in found], ["new", "new"])
        self.assertEqual(self.watch._seen[(SESSION, "php00001")].pid, 20)
        self.assertEqual(self.watch._seen[(SESSION, "pwsh0001")].pid, 30)
        self.assertEqual(found[0].program, "php")

    def test_a_server_nobody_uses_is_needless_after_half_an_hour(self):
        self.probe.shell(20, PHP, T0 - 7000, "php.exe", cpu=900)
        self.probe.sockets = [(22, 2, 8770)]  # php listens
        self.probe.outputs["php00001"] = (5000, T0 - 2880)  # its last request 48 min ago
        first = self.look([task("php00001", PHP, "Start local PHP preview")], 0)["php00001"]
        self.assertEqual((first.kind, first.text), ("server", "server (php) na :8770"))
        self.assertFalse(first.keeps_working)  # it never ends by itself: the session doesn't wait for it
        self.assertFalse(first.needless)  # not until its processor time is known too
        later = self.look([task("php00001", PHP)], shells.SAMPLE_S)["php00001"]
        self.assertTrue(later.needless)
        self.assertEqual(later.text, "server (php) na :8770, nikdo ho nepoužil 48 min")

    def test_a_server_somebody_uses(self):
        self.probe.shell(20, PHP, T0 - 7000, "php.exe")
        self.probe.sockets = [(22, 2, 8770), (22, 5, 8770), (99, 5, 51000)]  # a browser is connected
        self.look([task("php00001", PHP)], 0)
        shell = self.look([task("php00001", PHP)], 2 * shells.SAMPLE_S)["php00001"]
        self.assertEqual((shell.text, shell.needless), ("server (php) na :8770, používá se", False))

    def test_a_server_that_writes_nothing_is_quiet_only_since_orbit_watches(self):
        # mysqld logs nowhere Orbit sees: started 2 h ago doesn't mean unused for 2 h
        self.probe.shell(20, "mysqld --port=3306", T0 - 7200, "mysqld.exe")
        self.probe.sockets = [(22, 2, 3306)]
        self.look([task("db000001", "mysqld --port=3306")], 0)
        shell = self.look([task("db000001", "mysqld --port=3306")], 10 * 60)["db000001"]
        self.assertEqual((shell.text, shell.needless), ("server (mysqld) na :3306, nikdo ho nepoužil 10 min", False))
        shell = self.look([task("db000001", "mysqld --port=3306")], 31 * 60)["db000001"]
        self.assertTrue(shell.needless)

    def test_working_waiting_and_hung(self):
        self.probe.shell(20, "npm run build", T0 - 30, "node.exe", cpu=500)
        self.probe.shell(30, "sleep 600 && echo hotovo", T0 - 1000, "sleep.exe")
        self.probe.shell(40, "git push", T0 - 4000, "git.exe")  # waits for a password nobody types
        tasks = [task("build001", "npm run build"), task("wait0001", "sleep 600 && echo hotovo"),
                 task("push0001", "git push")]
        self.look(tasks, 0)
        self.probe.cpu[22] += 4000  # the build keeps going
        shells_ = self.look(tasks, 60)
        self.assertEqual([shells_[t].kind for t in ("build001", "wait0001", "push0001")], ["works", "waits", "quiet"])
        self.assertEqual(shells_["push0001"].text, "teď nic nedělá (1 min)")
        self.probe.cpu[22] += 4000
        shells_ = self.look(tasks, shells.IDLE_S + 60)
        self.assertEqual([shells_[t].kind for t in ("build001", "wait0001", "push0001")], ["works", "waits", "idle"])
        self.assertEqual([shells_[t].keeps_working for t in ("build001", "wait0001", "push0001")], [True, True, False])
        self.assertEqual(shells_["push0001"].text, "nic nedělá 16 min, nejspíš visí")  # since Orbit first saw it
        self.assertTrue(shells_["push0001"].needless)

    def test_output_counts_as_work(self):
        self.probe.shell(20, "python crawl.py", T0 - 4000, "python.exe")
        self.probe.outputs["crawl001"] = (100, T0 - 3000)
        self.look([task("crawl001", "python crawl.py")], 0)
        self.probe.outputs["crawl001"] = (180, T0 + 60)
        self.assertEqual(self.look([task("crawl001", "python crawl.py")], 60)["crawl001"].kind, "works")

    def test_a_shell_that_isnt_there(self):
        shell = self.look([task("gone0001", "php -S :8000")], 0)["gone0001"]
        self.assertEqual(shell.kind, "gone")
        self.assertTrue(shell.keeps_working)  # it ended: Claude Code tells the session, which then reports again

    def test_a_number_an_older_process_had(self):
        self.probe.shell(20, PHP, T0 - 9000, "php.exe")  # older than this claude.exe: its parent was another
        self.assertEqual(self.look([task("php00001", PHP)], 0)["php00001"].kind, "gone")

    def test_looks_at_most_every_few_seconds(self):
        self.probe.shell(20, PHP, T0 - 7000, "php.exe")
        self.look([task("php00001", PHP)], 0)
        self.probe.sockets = [(22, 2, 8770)]
        self.assertEqual(self.look([task("php00001", PHP)], 1)["php00001"].kind, "new")  # the same answer
        self.assertEqual(self.look([task("php00001", PHP)], shells.SAMPLE_S)["php00001"].kind, "server")

    def test_kill_ends_the_whole_tree(self):
        self.probe.shell(20, PHP, T0 - 7000, "php.exe")
        self.look([task("php00001", PHP)], 0)
        self.assertTrue(self.watch.kill(SESSION, "php00001"))
        self.assertEqual(self.probe.killed, [22, 21, 20])  # the program first, the shell last
        self.assertIn((SESSION, "php00001"), self.watch.stopped)

    def test_command_of_a_real_command_line(self):
        line = ('"C:\\Program Files\\Git\\bin\\bash.exe" -c "source /c/x.sh 2>/dev/null || true && eval \'cd '
                '/c/Users/josef/m-tex && \\"/c/xampp1/php/php.exe\\" -S 127.0.0.1:8770 -t www\' < /dev/null && pwd '
                '-P >| /c/Temp/claude-a1e4-cwd"')  # as Windows showed it, from a session on 11 Oct
        self.assertEqual(shells.command_of(line), 'cd /c/Users/josef/m-tex && "/c/xampp1/php/php.exe" -S '
                                                  '127.0.0.1:8770 -t www')
        self.assertEqual(shells.command_of(bash_line("echo 'a b' \"c\"")), "echo 'a b' \"c\"")
        self.assertEqual(shells.command_of('"node.exe" server.js'), "")


class Stopping(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="orbit-stop-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.stopper = shells.Stopper(self.folder)

    def test_the_mods_answer_comes_back_and_both_files_go(self):
        self.assertTrue(self.stopper.ask(SESSION, "php00001"))
        request = json.loads((self.folder / f"{SESSION}.php00001.json").read_text(encoding="utf-8"))
        self.assertEqual((request["session_id"], request["task_id"]), (SESSION, "php00001"))
        self.assertTrue(self.stopper.asked(SESSION, "php00001"))
        self.assertEqual(self.stopper.answers(), [])  # not yet
        (self.folder / f"{SESSION}.php00001.done.json").write_text(
            json.dumps({"ok": True, "text": "Successfully stopped task"}), encoding="utf-8")
        self.assertEqual(self.stopper.answers(), [(SESSION, "php00001", True, "Successfully stopped task")])
        self.assertEqual(list(self.folder.iterdir()), [])
        self.assertFalse(self.stopper.asked(SESSION, "php00001"))

    def test_no_answer_in_time(self):
        self.stopper.ask(SESSION, "php00001")
        self.assertEqual(self.stopper.answers(now=10**10), [(SESSION, "php00001", None, "")])
        self.assertEqual(list(self.folder.iterdir()), [])  # a mod loaded later won't act on it

    def test_odd_ids_are_not_written(self):
        self.assertFalse(self.stopper.ask(SESSION, "../x"))
        self.assertFalse(self.stopper.ask("a/b", "php00001"))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_leftovers_of_an_earlier_run_go(self):
        (self.folder / f"{SESSION}.old00001.json").write_text("{}", encoding="utf-8")
        shells.Stopper(self.folder)
        self.assertEqual(list(self.folder.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
