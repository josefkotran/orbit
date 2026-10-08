"""Claude Code hook: records a session's state change for Orbit's session overview.

Claude Code runs it (asynchronously, without a shell) for SessionStart, UserPromptSubmit, Notification, Stop,
StopFailure and SessionEnd with the event JSON on stdin. It writes <data>/sessions/<session_id>.<event>.json – one
file per event type, so hooks of one session running at the same time never overwrite each other's data. Orbit reads
them. PostToolUse of the Artifact tool (a published page, which Orbit reads aloud) goes to sessions/artifacts/
instead, one file per publish.

Besides the event it records the session's permission mode (Orbit's voice agent sends messages in the same class,
see agent.py), its claude.exe and the window that shows it: Windows Terminal's or the classic console's, else the
window of the program the terminal runs in (VS Code, Cursor, another IDE).

<data> is Orbit's data folder: `--data <folder>` in the hook's args, else the same rules as Orbit's (paths.py).
Hooks get Claude Code's environment, not Orbit's.

Standard library only and nothing slow: it runs on every prompt of every session.
"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

KEEP = ("session_id", "cwd", "transcript_path", "hook_event_name", "source", "model", "message", "notification_type",
        "last_assistant_message", "reason", "prompt", "permission_mode")
# where the walk up from claude.exe stops looking for a window: the shell and the system aren't a terminal
_NOT_TERMINALS = {"explorer.exe", "svchost.exe", "services.exe", "wininit.exe", "winlogon.exe", "sihost.exe",
                  "runtimebroker.exe", "userinit.exe"}


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def _processes() -> tuple[dict[int, int], dict[int, str]]:
    """Every process's parent and lower-case exe name."""
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    parents, names = {}, {}
    entry = _ProcessEntry(dwSize=ctypes.sizeof(_ProcessEntry))
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        parents[entry.th32ProcessID] = entry.th32ParentProcessID
        names[entry.th32ProcessID] = entry.szExeFile.lower()
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return parents, names


def _claude_pid(parents: dict[int, int], names: dict[int, str]) -> int:
    """The claude.exe this hook belongs to (the nearest ancestor with that name; its auto-update renames a running
    binary to claude.exe.old.<n>)."""
    pid = os.getpid()
    for _ in range(10):
        pid = parents.get(pid, 0)
        if not pid or names.get(pid, "").startswith("claude.exe"):
            return pid
    return 0


def _console_window(claude_pid: int) -> int:
    """The window showing the session's console: Windows Terminal owns the hidden pseudo-console window, the classic
    console is that window itself. 0 when that isn't a visible window (VS Code, Cursor and other IDE terminals keep
    their pseudo console to themselves). Async hooks run without a console (or with a hidden one of their own), so it
    borrows claude.exe's for a moment."""
    k32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GetConsoleWindow.restype = wintypes.HWND
    user32.GetAncestor.restype = wintypes.HWND

    def shown(hwnd) -> int:
        root = user32.GetAncestor(wintypes.HWND(hwnd), 3) or hwnd if hwnd else 0  # GA_ROOTOWNER
        return int(root) if root and user32.IsWindowVisible(wintypes.HWND(root)) else 0

    found = shown(k32.GetConsoleWindow())
    if not found and claude_pid:
        k32.FreeConsole()  # its own console, if it has one: a process can be attached to one console only
        if k32.AttachConsole(claude_pid):
            found = shown(k32.GetConsoleWindow())
            k32.FreeConsole()
    return found


def _ancestor_window(claude_pid: int, parents: dict[int, int], names: dict[int, str], folder: str) -> int:
    """The main window of the nearest program above claude.exe that has one (the IDE whose terminal runs the
    session). With several (VS Code windows), the one whose title has the session's folder."""
    chain, pid = [], claude_pid
    for _ in range(8):
        pid = parents.get(pid, 0)
        if not pid or names.get(pid, "") in _NOT_TERMINALS:
            break
        chain.append(pid)
    if not chain:
        return 0
    user32 = ctypes.windll.user32
    user32.GetWindow.restype = wintypes.HWND
    wanted, found = set(chain), {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def check(hwnd, _):
        handle = wintypes.HWND(hwnd)
        if user32.IsWindowVisible(handle) and not user32.GetWindow(handle, 4):  # GW_OWNER: a main window
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
            if owner.value in wanted:
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(handle, title, 256)
                if title.value:
                    found.setdefault(owner.value, []).append((int(hwnd), title.value.lower()))
        return True

    user32.EnumWindows(check, 0)
    for pid in chain:
        if pid in found:
            named = [h for h, title in found[pid] if folder and folder.lower() in title]
            return (named or [found[pid][0][0]])[0]
    return 0


def _write(target: Path, record: dict) -> None:
    tmp = target.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    try:
        for _ in range(5):
            try:
                os.replace(tmp, target)
                return
            except PermissionError:  # Orbit is reading the file this very moment
                time.sleep(0.02)
    finally:
        tmp.unlink(missing_ok=True)  # never leave a .tmp behind


def _data_dir() -> Path:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--data":
        return Path(args[1])
    # an embedded Python (the installed Orbit) doesn't put the script's folder on sys.path by itself
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import paths
    return paths.data_dir()


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk"):
        return  # a headless run (claude -p, the Agent SDK): not a session to show, nothing to read aloud
    session, event = data.get("session_id"), data.get("hook_event_name")
    if not session or not event:
        return
    sessions_dir = _data_dir() / "sessions"
    if event == "PostToolUse":
        args = data.get("tool_input") or {}
        if data.get("tool_name") == "Artifact" and args.get("file_path") and not args.get("asset") \
                and args.get("action", "publish") == "publish":
            artifacts_dir = sessions_dir / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            record = {k: data.get(k) for k in ("session_id", "cwd", "transcript_path", "tool_input", "tool_response")}
            record["time"] = time.time()
            _write(artifacts_dir / f"{session}.{data.get('tool_use_id') or time.time_ns()}.json", record)
        return
    sessions_dir.mkdir(parents=True, exist_ok=True)
    if event == "SessionEnd":
        for f in sessions_dir.glob(f"{session}.*.json"):
            f.unlink(missing_ok=True)
        return
    record = {k: data[k] for k in KEEP if k in data}
    if "prompt" in record:
        record["prompt"] = str(record["prompt"])[:1000]  # for Orbit's voice agent; pasted text can be huge
    if isinstance(data.get("background_tasks"), list):  # Stop: work the turn left running (not "hotovo" yet)
        record["background"] = [
            {"type": str(t.get("type") or ""),
             "what": str(t.get("description") or t.get("command") or t.get("name") or "")[:160]}
            for t in data["background_tasks"][:12] if isinstance(t, dict)]
    pid = hwnd = 0
    try:  # the event counts even when its process or window can't be found
        parents, names = _processes()
        pid = _claude_pid(parents, names)
        hwnd = _console_window(pid) or _ancestor_window(pid, parents, names, Path(str(data.get("cwd") or "")).name)
    except Exception:
        pass
    record.update(time=time.time(), pid=pid, hwnd=hwnd)
    _write(sessions_dir / f"{session}.{event}.json", record)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never disturb Claude Code
