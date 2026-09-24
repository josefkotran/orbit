"""Claude Code hook: records a session's state change for Orbit's session overview.

Claude Code runs it (asynchronously, without a shell) for SessionStart, UserPromptSubmit, Notification, Stop,
StopFailure and SessionEnd with the event JSON on stdin. It writes sessions/<session_id>.<event>.json – one file per
event type, so hooks of one session running at the same time never overwrite each other's data. Orbit reads them.

Standard library only and nothing slow: it runs on every prompt of every session.
"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"
KEEP = ("session_id", "cwd", "transcript_path", "hook_event_name", "source", "model", "message", "notification_type",
        "last_assistant_message", "reason")


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def _claude_pid() -> int:
    """The claude.exe this hook belongs to (the nearest ancestor with that name)."""
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
    pid = os.getpid()
    for _ in range(10):
        pid = parents.get(pid, 0)
        if not pid or names.get(pid) == "claude.exe":
            return pid
    return 0


def _terminal_window() -> int:
    """The Windows Terminal window showing this console (its hidden pseudo-console window is owned by it)."""
    ctypes.windll.kernel32.GetConsoleWindow.restype = wintypes.HWND
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if not hwnd:
        return 0
    user32 = ctypes.windll.user32
    user32.GetAncestor.restype = wintypes.HWND
    return user32.GetAncestor(wintypes.HWND(hwnd), 3) or hwnd  # GA_ROOTOWNER


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    session, event = data.get("session_id"), data.get("hook_event_name")
    if not session or not event:
        return
    SESSIONS_DIR.mkdir(exist_ok=True)
    if event == "SessionEnd":
        for f in SESSIONS_DIR.glob(f"{session}.*.json"):
            f.unlink(missing_ok=True)
        return
    record = {k: data[k] for k in KEEP if k in data}
    record.update(time=time.time(), pid=_claude_pid(), hwnd=_terminal_window())
    target = SESSIONS_DIR / f"{session}.{event}.json"
    tmp = target.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never disturb Claude Code
