"""Shells a Claude Code session left running in the background (the blue "2 shells" at the bottom of Claude Code) and
whether they still do anything.

Claude Code lists them to the Stop hook (`background_tasks`: id, command, description; cc_hook.py keeps them). Each
one is found among the processes of the session's claude.exe: Git Bash's `bash -c "… eval '<command>' …"` by its
command, PowerShell's `cmd /c "powershell … > …\\tasks\\<id>.output"` by its output file. Then its whole process tree
is watched: processor time, its output file (Claude Code's tasks/<id>.output), the TCP ports it listens on and the
clients connected to them.

A shell that works (processor, output) or waits on purpose (sleep, a polling loop: it ends and wakes the session) is
fine and the session counts as working. A server (php -S, npm run dev, mysqld) never ends by itself: the session
doesn't wait for it, and once nobody has used it for SERVER_IDLE_S it most likely isn't needed. A shell that did
nothing at all for IDLE_S (no processor, no output, no port) hangs or waits for input that never comes. Pepa (11 Oct):
"dole modře třeba dva shell, ale ve skutečnosti nic nedělají" – a PHP preview and a MariaDB, idle for an hour.

Stopping goes through Claude Code itself: Orbit leaves a request in <data>/sessions/stop/ and the mod orbit-mozek in
that session calls TaskStop (Stopper). A shell killed from outside reports to its session as failed ("exit code 1")
and wakes it up; one stopped with TaskStop doesn't (both tried 11 Oct). Killing (Watch.kill) is the last resort.

Standard library only.
"""
import ctypes
import json
import logging
import re
import socket
import tempfile
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .config import SESSIONS_DIR

log = logging.getLogger(__name__)

SAMPLE_S = 5.0  # how often a session's shells are looked at (its processes, ports and output files: ~3 ms)
BUSY_S = 90  # processor time, output or a client within this long = it does something
IDLE_S = 15 * 60  # nothing at all for this long (no processor, output or port): it hangs or waits for nothing
SERVER_IDLE_S = 30 * 60  # a server nobody has used for this long most likely isn't needed any more
CPU_MS = 20  # processor time per look below this counts as nothing (an idle php -S or mysqld: 0 ms in 30 s)
STOP_WAIT_S = 6.0  # how long a session's mod has to answer a stop request (it looks every 2 s)
STOP_DIR = SESSIONS_DIR / "stop"

SHELLS = {"bash.exe", "sh.exe", "zsh.exe", "cmd.exe", "powershell.exe", "pwsh.exe"}  # what Claude Code runs commands in
_HELPERS = SHELLS | {"conhost.exe"}  # not the program a shell runs
_WAITS = re.compile(r"^\s*(sleep|timeout|start-sleep)\b|\b(until|while)\b.*\b(sleep|start-sleep)\b", re.I | re.S)
_CLIPPED = re.compile(r"\s*\.\.\. \[\+\d+ chars\]$")  # Claude Code's mark on a command cut at 1000 characters
# Git Bash: the command inside `eval '…'`, a ' in it written as '"'"' (or '\'')
_EVAL = re.compile(r"""\beval '((?:[^']|'"'"'|'\\'')*)'""")
_SESSION_ID = re.compile(r"^[\w-]{1,128}$")
_TASK_ID = re.compile(r"^[a-z0-9]{4,32}$")

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # own function objects: other modules set other argtypes
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
_k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_k32.LocalFree.argtypes = [ctypes.c_void_p]
_ntdll = ctypes.WinDLL("ntdll")
_ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                                             ctypes.POINTER(wintypes.ULONG)]
_ntdll.NtQueryInformationProcess.restype = ctypes.c_long
_shell32 = ctypes.WinDLL("shell32")
_shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
_shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
_iphlpapi = ctypes.WinDLL("iphlpapi")
_iphlpapi.GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                                          wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
_iphlpapi.GetExtendedTcpTable.restype = wintypes.DWORD

_QUERY, _TERMINATE = 0x1000, 0x0001  # PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_TERMINATE
_LISTEN, _ESTABLISHED = 2, 5  # MIB_TCP_STATE


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


class _UnicodeString(ctypes.Structure):
    _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]


class _TcpRow(ctypes.Structure):  # MIB_TCPROW_OWNER_PID
    _fields_ = [("state", wintypes.DWORD), ("local_addr", wintypes.DWORD), ("local_port", wintypes.DWORD),
                ("remote_addr", wintypes.DWORD), ("remote_port", wintypes.DWORD), ("pid", wintypes.DWORD)]


class _Tcp6Row(ctypes.Structure):  # MIB_TCP6ROW_OWNER_PID
    _fields_ = [("local_addr", ctypes.c_ubyte * 16), ("local_scope", wintypes.DWORD), ("local_port", wintypes.DWORD),
                ("remote_addr", ctypes.c_ubyte * 16), ("remote_scope", wintypes.DWORD),
                ("remote_port", wintypes.DWORD), ("state", wintypes.DWORD), ("pid", wintypes.DWORD)]


class Windows:
    """What Watch asks the system (tests hand it a pretend one)."""

    def processes(self) -> dict[int, tuple[int, str]]:
        """Every process: pid -> (parent pid, lower-case exe name)."""
        snap = _k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        found = {}
        if not snap or snap == wintypes.HANDLE(-1).value:
            return found
        entry = _ProcessEntry(dwSize=ctypes.sizeof(_ProcessEntry))
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            found[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile.lower())
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
        _k32.CloseHandle(snap)
        return found

    def times(self, pid: int) -> tuple[float, float] | None:
        """(when it started as Unix time, processor time in ms), None when it can't be opened."""
        handle = _k32.OpenProcess(_QUERY, False, pid)
        if not handle:
            return None
        try:
            created, ended, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
            if not _k32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(ended), ctypes.byref(kernel),
                                        ctypes.byref(user)):
                return None
            return (created.value - 116444736000000000) / 1e7, (kernel.value + user.value) / 1e4
        finally:
            _k32.CloseHandle(handle)

    def command_line(self, pid: int) -> str:
        handle = _k32.OpenProcess(_QUERY, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.ULONG(0)
            _ntdll.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(size))  # ProcessCommandLineInformation
            if not size.value:
                return ""
            buf = ctypes.create_string_buffer(size.value)
            if _ntdll.NtQueryInformationProcess(handle, 60, buf, size, ctypes.byref(size)) != 0:
                return ""
            text = _UnicodeString.from_buffer(buf)
            return ctypes.wstring_at(text.Buffer, text.Length // 2) if text.Buffer else ""
        finally:
            _k32.CloseHandle(handle)

    def tcp(self) -> list[tuple[int, int, int]]:
        """Every TCP socket: (pid, state, local port), IPv4 and IPv6."""
        rows = []
        for family, row in ((2, _TcpRow), (23, _Tcp6Row)):  # AF_INET, AF_INET6
            size, buf, result = wintypes.DWORD(65536), None, 1
            for _ in range(4):
                buf = ctypes.create_string_buffer(size.value)
                result = _iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, family, 5, 0)  # OWNER_PID_ALL
                if result != 122:  # ERROR_INSUFFICIENT_BUFFER: the table grew, size is the new one
                    break
            if result:
                continue
            count = wintypes.DWORD.from_buffer(buf).value
            for item in (row * count).from_buffer(buf, ctypes.sizeof(wintypes.DWORD)):
                rows.append((item.pid, item.state, socket.ntohs(item.local_port & 0xFFFF)))
        return rows

    def output(self, session: str, task: str) -> tuple[int, float] | None:
        """(size, modified) of the task's output file: <temp>/claude/<project>/<session>/tasks/<task>.output."""
        for path in (Path(tempfile.gettempdir()) / "claude").glob(f"*/{session}/tasks/{task}.output"):
            try:
                stat = path.stat()
            except OSError:
                continue
            return stat.st_size, stat.st_mtime
        return None

    def kill(self, pid: int, created: float) -> bool:
        times = self.times(pid)
        if times is None or abs(times[0] - created) > 1:
            return False  # gone, or the number belongs to another process by now
        handle = _k32.OpenProcess(_TERMINATE, False, pid)
        if not handle:
            return False
        try:
            return bool(_k32.TerminateProcess(handle, 1))
        finally:
            _k32.CloseHandle(handle)


def command_of(command_line: str) -> str:
    """The command a Claude Code shell runs, from its process's command line ("" when it isn't one: an MCP server)."""
    count = ctypes.c_int()
    argv = _shell32.CommandLineToArgvW(command_line, ctypes.byref(count))
    if not argv:
        return ""
    try:
        args = [argv[i] for i in range(count.value)]
    finally:
        _k32.LocalFree(argv)
    script = args[args.index("-c") + 1] if "-c" in args[:-1] else ""
    found = _EVAL.search(script)
    return found.group(1).replace("'\"'\"'", "'").replace("'\\''", "'") if found else ""


def _plain(text: str) -> str:
    return " ".join(_CLIPPED.sub("", text).split())


def _span(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{max(1, minutes)} min"


@dataclass
class Shell:
    """One background shell of a session as Orbit sees it."""
    task: str  # Claude Code's id for it ("bh3di8ppc")
    what: str  # what it's for, as Claude described it ("Start local PHP preview")
    kind: str = "new"  # new, works, waits, quiet, idle, server, gone (see text)
    idle_s: float = 0.0  # since it last did something (at least: a program that writes nothing, since Orbit watches)
    used: bool = False  # it did something within BUSY_S (a server: somebody used it)
    ports: tuple = ()  # TCP ports it listens on
    program: str = ""  # what runs in the shell ("php"), when it isn't the shell itself
    known: bool = False  # looked at twice at least: its processor time is known, not only its output file

    @property
    def needless(self) -> bool:
        """Most likely not needed any more: worth stopping."""
        return self.kind == "idle" or (self.kind == "server" and self.known and self.idle_s >= SERVER_IDLE_S)

    @property
    def keeps_working(self) -> bool:
        """Does the session wait for it? A server never ends by itself, a hung shell won't either; anything else
        reports back to the session when it ends (and so does a shell Orbit couldn't find)."""
        return self.kind not in ("server", "idle")

    @property
    def text(self) -> str:
        """"server (php) na :8770, nikdo ho nepoužil 48 min"."""
        if self.kind == "server":
            text = f"server{f' ({self.program})' if self.program else ''} na " + ", ".join(f":{p}" for p in self.ports)
            if self.used:
                text += ", používá se"
            elif self.known:
                text += f", nikdo ho nepoužil {_span(self.idle_s)}" if self.idle_s >= BUSY_S else \
                    ", teď ho nikdo nepoužívá"
            return text
        return {"new": "zjišťuju, co dělá", "works": "pracuje", "waits": "čeká (sleep nebo smyčka)",
                "quiet": f"teď nic nedělá ({_span(self.idle_s)})",
                "idle": f"nic nedělá {_span(self.idle_s)}, nejspíš visí",
                "gone": "jeho proces jsem nenašel"}[self.kind]


@dataclass
class _Seen:
    pid: int
    created: float
    cpu_ms: float
    out_size: int
    active_at: float  # since when it's quiet, as well as it's known
    did_at: float  # when it was last seen doing something (0 = not yet)
    looks: int = 1
    tree: tuple = ()  # (pid, started) of its processes at the last look, the shell first


class Watch:
    """The shells of the sessions, looked at every SAMPLE_S: look() is cheap in between."""

    def __init__(self, probe=None):
        self._probe = probe or Windows()
        self._system: tuple[float, dict, list] = (-1.0, {}, [])  # (when, processes, TCP sockets), one per second
        self._seen: dict[tuple[str, str], _Seen] = {}
        self._shown: dict[str, tuple[float, tuple, list[Shell]]] = {}  # session -> (when, task ids, shells)
        self._commands: dict[tuple[int, float], str] = {}  # (pid, started) -> the command it runs
        self.stopped: set[tuple[str, str]] = set()  # (session, task) stopped by Orbit: not shown, not waited for

    def look(self, session: str, claude_pid: int, tasks: list[dict], now: float | None = None) -> list[Shell]:
        """The session's background shells (Stop's background_tasks of type shell: id, command, what)."""
        now = time.time() if now is None else now
        ids = tuple(t["id"] for t in tasks)
        when, shown_ids, shells = self._shown.get(session, (0.0, (), []))
        if ids == shown_ids and now - when < SAMPLE_S:
            return shells
        try:
            shells = self._sample(session, claude_pid, tasks, now)
        except OSError:
            log.exception("Kontrola příkazů na pozadí selhala")
            shells = [Shell(t["id"], t.get("what", ""), kind="gone") for t in tasks]
        self._shown[session] = (now, ids, shells)
        for key in [k for k in self._seen if k[0] == session and k[1] not in ids]:
            del self._seen[key]
        return shells

    def forget(self, live: set[str]) -> None:
        """Sessions that ended."""
        for session in set(self._shown) - live:
            del self._shown[session]
        self._seen = {k: v for k, v in self._seen.items() if k[0] in live}
        self.stopped = {k for k in self.stopped if k[0] in live}

    def _sample(self, session: str, claude_pid: int, tasks: list[dict], now: float) -> list[Shell]:
        probe = self._probe
        if abs(now - self._system[0]) >= 1:  # the process list takes ~5 ms: once for all sessions looked at now
            self._system = (now, probe.processes(), probe.tcp())
        _, processes, sockets = self._system
        claude = probe.times(claude_pid) if claude_pid in processes else None
        roots = []  # (pid, started, command line, command) of the claude.exe's shells
        for pid, (parent, name) in processes.items():
            if parent != claude_pid or name not in SHELLS or claude is None:
                continue
            times = probe.times(pid)
            if times is None or times[0] < claude[0] - 1:
                continue  # its parent number belongs to an earlier process
            key = (pid, times[0])
            if key not in self._commands:
                line = probe.command_line(pid)
                self._commands[key] = line
            line = self._commands[key]
            roots.append((pid, times[0], line, _plain(command_of(line)) if "eval '" in line else ""))
        live = {(pid, started) for pid, started, _, _ in roots}
        self._commands = {k: v for k, v in self._commands.items() if k in live}
        roots.sort(key=lambda r: r[1])

        children: dict[int, list[int]] = {}
        for pid, (parent, _) in processes.items():
            children.setdefault(parent, []).append(pid)
        taken: set[int] = set()
        shells = []
        for task in tasks:
            tid, wanted = task["id"], _plain(task.get("command", ""))
            root = next((r for r in roots if r[0] not in taken and (
                f"\\tasks\\{tid}.output" in r[2] or f"/tasks/{tid}.output" in r[2])), None) or \
                next((r for r in roots if r[0] not in taken and wanted and r[3] and r[3].startswith(wanted)), None)
            shell = Shell(tid, task.get("what") or task.get("command", "")[:80])
            if root is None:
                shell.kind = "gone"
                self._seen.pop((session, tid), None)
                shells.append(shell)
                continue
            taken.add(root[0])
            tree, names, cpu = [], [], 0.0  # its processes as (pid, started), the shell first
            queue, visited = [(root[0], root[1])], set()
            while queue:
                pid, parent_started = queue.pop()
                times = probe.times(pid) if pid not in visited else None
                if times is None or times[0] < parent_started - 1:
                    continue  # ended, or a number another process had before
                visited.add(pid)
                cpu += times[1]
                tree.append((pid, times[0]))
                if pid != root[0]:
                    names.append(processes[pid][1])
                queue += [(child, times[0]) for child in children.get(pid, ())]
            pids = {pid for pid, _ in tree}
            ports = tuple(sorted({port for pid, state, port in sockets if pid in pids and state == _LISTEN}))
            clients = sum(1 for pid, state, port in sockets if pid in pids and state == _ESTABLISHED and port in ports)
            out = probe.output(session, tid)
            size, written = out if out else (0, 0.0)

            seen = self._seen.get((session, tid))
            if seen is None or (seen.pid, seen.created) != (root[0], root[1]):
                # its past is known only from its output file: one that writes nothing (mysqld) counts as quiet
                # since Orbit first sees it, unless it started just now
                active = max(root[1], written) if size or now - root[1] < 2 * SAMPLE_S else now
                seen = self._seen[(session, tid)] = _Seen(root[0], root[1], cpu, size, active, written if size else 0)
            else:
                seen.looks += 1
                if cpu - seen.cpu_ms >= CPU_MS or size != seen.out_size:
                    seen.active_at = seen.did_at = now
                seen.cpu_ms, seen.out_size = cpu, size
            if clients:
                seen.active_at = seen.did_at = now
            seen.tree = tuple(tree)

            shell.idle_s = max(0.0, now - seen.active_at)
            shell.used = bool(seen.did_at) and now - seen.did_at < BUSY_S
            shell.known = seen.looks >= 2
            shell.ports = ports
            shell.program = next((Path(n).stem for n in names if n not in _HELPERS), "")
            waits = bool(_WAITS.search(wanted)) or any(n in ("sleep.exe", "timeout.exe") for n in names)
            if ports:
                shell.kind = "server"
            elif not shell.known:
                shell.kind = "new"
            elif shell.used:
                shell.kind = "works"
            elif waits:
                shell.kind = "waits"
            else:
                shell.kind = "idle" if shell.idle_s >= IDLE_S else "quiet"
            shells.append(shell)
        return shells

    def kill(self, session: str, task: str) -> bool:
        """Ends the shell's processes from outside, the last resort: Claude Code tells the session it failed."""
        seen = self._seen.get((session, task))
        if seen is None:
            return False
        killed = [self._probe.kill(pid, started) for pid, started in reversed(seen.tree)]
        if any(killed):
            self.stopped.add((session, task))
        return any(killed)


class Stopper:
    """Stop requests for the mod orbit-mozek in the session: <data>/sessions/stop/<session>.<task>.json; it calls
    TaskStop and answers with <session>.<task>.done.json ({"ok", "text"}). Orbit removes both."""

    def __init__(self, folder: Path = STOP_DIR):
        self.folder = folder
        self._asked: dict[tuple[str, str], float] = {}
        try:  # an earlier run's (the mod leaves requests older than a minute alone anyway)
            for f in folder.glob("*.json"):
                f.unlink(missing_ok=True)
        except OSError:
            pass

    def ask(self, session: str, task: str) -> bool:
        if not _SESSION_ID.match(session) or not _TASK_ID.match(task):
            return False
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp = self.folder / f"{session}.{task}.tmp"
            tmp.write_text(json.dumps({"session_id": session, "task_id": task, "time": time.time()}),
                           encoding="utf-8")
            tmp.replace(self.folder / f"{session}.{task}.json")
        except OSError:
            log.exception("Žádost o zastavení příkazu nejde zapsat")
            return False
        self._asked[(session, task)] = time.time()
        return True

    def asked(self, session: str, task: str) -> bool:
        return (session, task) in self._asked

    def answers(self, now: float | None = None) -> list[tuple[str, str, bool | None, str]]:
        """(session, task, ok, Claude Code's words) for each request answered; ok None = no answer in time (the
        session runs without the mod, or an older one)."""
        now = time.time() if now is None else now
        done = []
        for (session, task), at in list(self._asked.items()):
            request, answer = self.folder / f"{session}.{task}.json", self.folder / f"{session}.{task}.done.json"
            try:
                reply = json.loads(answer.read_text(encoding="utf-8"))
            except FileNotFoundError:
                if now - at < STOP_WAIT_S:
                    continue
                reply = None
            except (OSError, ValueError):
                continue  # being written
            for f in (request, answer):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
            del self._asked[(session, task)]
            if reply is None:
                done.append((session, task, None, ""))
            else:
                reply = reply if isinstance(reply, dict) else {}
                done.append((session, task, reply.get("ok") is True, str(reply.get("text") or "")[:300]))
        return done
