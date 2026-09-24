"""Overview of running Claude Code sessions: what each one does, whether it waits for Pepa, how full its context is.

Claude Code hooks (installed into ~/.claude/settings.json by set_hooks) run app/cc_hook.py, which leaves one file per
session and event in sessions/. Everything else – state, context usage, the terminal window – is worked out here.
"""
import ctypes
import json
import logging
import re
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .config import ROOT

log = logging.getLogger(__name__)

SESSIONS_DIR = ROOT / "sessions"
SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "Notification", "Stop", "StopFailure", "SessionEnd")
_HOOK = {"type": "command", "command": (ROOT / ".venv" / "Scripts" / "python.exe").as_posix(),
         "args": [(ROOT / "app" / "cc_hook.py").as_posix()], "async": True, "timeout": 10}

DONE_FRESH_S = 600  # "hotovo" for this long after a turn, then "v klidu"
WAITING_TYPES = ("permission_prompt", "elicitation_dialog")
STATE_LABELS = {"working": "pracuje", "waiting": "čeká na tebe", "done": "hotovo", "idle": "v klidu",
                "error": "chyba"}
STALE_S = 12 * 3600  # sessions whose process can't be checked disappear after this long without an event

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_kernel32.OpenProcess.restype = wintypes.HANDLE
_user32.GetForegroundWindow.restype = wintypes.HWND


@dataclass
class Session:
    id: str
    cwd: str = ""
    transcript: str = ""
    pid: int = 0
    hwnd: int = 0
    state: str = "idle"
    since: float = 0.0  # when the current state started
    turn_s: float = 0.0  # how long the last finished turn took
    message: str = ""  # what it waits for / its last answer
    context_tokens: int = 0
    context_size: int = 0

    @property
    def name(self) -> str:
        return Path(self.cwd).name or self.cwd or "?"

    @property
    def context(self) -> float | None:
        return self.context_tokens / self.context_size if self.context_size else None

    def title(self) -> str:
        """The session's topic from its terminal window title ("◐ Katalog z Německa překlad")."""
        if not self.hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(wintypes.HWND(self.hwnd), buf, 256)
        title = re.sub(r"^[^\w]+", "", buf.value).strip()
        return "" if title == "Claude Code" else title

    def tooltip(self) -> str:
        lines = [f"{self.name} – {self.title()}" if self.title() else self.name,
                 STATE_LABELS[self.state] + (f": {summary(self.message, 1)}" if self.message and
                                             self.state in ("waiting", "error") else "")]
        if self.context is not None:
            lines.append(f"Kontext {self.context * 100:.0f} % ({self.context_tokens // 1000} tis. z "
                         f"{_size_text(self.context_size)} tokenů)")
        if self.hwnd:
            lines.append("Klikni a přepneš se do jejího terminálu.")
        return "\n".join(lines)


def _size_text(tokens: int) -> str:
    return f"{tokens // 1_000_000} mil." if tokens >= 1_000_000 else f"{tokens // 1000} tis."


class SessionTracker:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self._context_cache: dict[str, tuple[float, int]] = {}
        self._first = True

    def poll(self) -> list[tuple[Session, str]]:
        """Re-reads the hook files. Returns (session, new state) for changes worth telling Pepa about
        (nothing on the first call, so a restart of Orbit doesn't repeat old news)."""
        records: dict[str, dict[str, dict]] = {}
        try:
            files = list(SESSIONS_DIR.glob("*.json"))
        except OSError:
            files = []
        for f in files:
            sid, _, event = f.stem.partition(".")
            try:
                records.setdefault(sid, {})[event] = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # being written right now

        changes = []
        for sid, events in records.items():
            latest = max(events.values(), key=lambda r: r.get("time", 0))
            if not _alive(latest.get("pid", 0), latest.get("hwnd", 0), latest.get("time", 0)):
                for f in SESSIONS_DIR.glob(f"{sid}.*.json"):
                    f.unlink(missing_ok=True)
                continue
            s = self.sessions.get(sid) or Session(sid)
            before = s.state
            s.cwd, s.transcript = latest.get("cwd", s.cwd), latest.get("transcript_path", s.transcript)
            s.pid = latest.get("pid") or s.pid
            s.hwnd = next((r["hwnd"] for r in sorted(events.values(), key=lambda r: -r.get("time", 0))
                           if r.get("hwnd")), s.hwnd)
            self._update_state(s, events)
            self._update_context(s)
            if not self._first and s.state != before and s.state in ("waiting", "done", "error"):
                changes.append((s, s.state))
            self.sessions[sid] = s
        for sid in set(self.sessions) - set(records):
            del self.sessions[sid]
        self._first = False
        return changes

    def _update_state(self, s: Session, events: dict[str, dict]) -> None:
        relevant = {e: r for e, r in events.items()
                    if e != "Notification" or r.get("notification_type", "permission_prompt") in WAITING_TYPES}
        if not relevant:  # only an "idle for a minute" notification so far
            s.state = "idle"
            return
        event, rec = max(relevant.items(), key=lambda item: item[1].get("time", 0))
        s.since = rec.get("time", 0)
        if event == "UserPromptSubmit":
            s.state, s.message = "working", ""
        elif event == "Notification":
            s.state, s.message = "waiting", rec.get("message", "")
            if self._transcript_mtime(s) > s.since + 1.5:  # Pepa answered the prompt, the tool is running
                s.state = "working"
        elif event in ("Stop", "StopFailure"):
            started = events.get("UserPromptSubmit", {}).get("time", s.since)
            s.turn_s = max(0.0, s.since - started)
            s.message = rec.get("last_assistant_message") or rec.get("message") or ""
            s.state = "error" if event == "StopFailure" else \
                "done" if time.time() - s.since < DONE_FRESH_S else "idle"
        else:
            s.state = "idle"

    @staticmethod
    def _transcript_mtime(s: Session) -> float:
        try:
            return Path(s.transcript).stat().st_mtime
        except (OSError, ValueError):
            return 0.0

    def _update_context(self, s: Session) -> None:
        mtime = self._transcript_mtime(s)
        cached = self._context_cache.get(s.transcript)
        if cached and cached[0] == mtime:
            tokens = cached[1]
        else:
            tokens = _context_tokens(s.transcript)
            self._context_cache[s.transcript] = (mtime, tokens)
        s.context_tokens = tokens
        s.context_size = (1_000_000 if tokens > 200_000 or "[1m]" in _default_model() else 200_000) if tokens else 0


def _context_tokens(transcript: str) -> int:
    """Tokens the session's last main-thread request sent (= how full its context is), from the transcript's end."""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 512 * 1024))
            lines = f.read().splitlines()
    except (OSError, ValueError):
        return 0
    for line in reversed(lines):
        if b'"usage"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        usage = (entry.get("message") or {}).get("usage")
        if entry.get("type") == "assistant" and not entry.get("isSidechain") and usage:
            return sum(usage.get(k) or 0 for k in
                       ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return 0


_model_cache: tuple[float, str] = (0.0, "")


def _default_model() -> str:
    global _model_cache
    try:
        mtime = SETTINGS.stat().st_mtime
        if mtime != _model_cache[0]:
            _model_cache = (mtime, str(json.loads(SETTINGS.read_text(encoding="utf-8")).get("model", "")))
    except (OSError, ValueError):
        pass
    return _model_cache[1]


def _alive(pid: int, hwnd: int, last_event: float) -> bool:
    if pid:
        handle = _kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code, name = wintypes.DWORD(), ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(512)
            _kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            _kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))
            return code.value == 259 and name.value.lower().endswith("claude.exe")  # STILL_ACTIVE, not a reused PID
        finally:
            _kernel32.CloseHandle(handle)
    if hwnd:
        return bool(_user32.IsWindow(wintypes.HWND(hwnd)))
    return time.time() - last_event < STALE_S


def is_foreground(s: Session) -> bool:
    return bool(s.hwnd) and _user32.GetForegroundWindow() == s.hwnd


def focus(s: Session) -> bool:
    """Brings the session's terminal window to the front."""
    hwnd = wintypes.HWND(s.hwnd)
    if not s.hwnd or not _user32.IsWindow(hwnd):
        return False
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if _user32.SetForegroundWindow(hwnd):
        return True
    # Windows lets only the app with the last input change the foreground; sharing input state with the current
    # foreground thread for a moment gets around that without sending any keys.
    fg_thread = _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), None)
    our_thread = _kernel32.GetCurrentThreadId()
    _user32.AttachThreadInput(our_thread, fg_thread, True)
    try:
        _user32.BringWindowToTop(hwnd)
        return bool(_user32.SetForegroundWindow(hwnd))
    finally:
        _user32.AttachThreadInput(our_thread, fg_thread, False)


def summary(text: str, sentences: int = 2, limit: int = 300) -> str:
    """The start of a Markdown answer as plain sentences (for a notification or reading aloud)."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "odkaz", text)
    text = re.sub(r"[`*_#>|]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)
    text = " ".join(text.split())
    parts = re.split(r"(?<=[.!?:])\s+", text)
    out = " ".join(parts[:sentences])
    return out if len(out) <= limit else out[:limit].rsplit(" ", 1)[0] + "…"


# --- hooks in ~/.claude/settings.json ------------------------------------------------------

def _is_ours(group: dict) -> bool:
    return any("cc_hook.py" in " ".join(h.get("args") or [h.get("command", "")]) for h in group.get("hooks", []))


def set_hooks(enabled: bool) -> bool:
    """Adds (or removes) Orbit's hooks, leaving everything else in the file as it is. Returns True if it changed
    anything. Already running sessions pick the change up only after a restart."""
    try:
        text = SETTINGS.read_text(encoding="utf-8")
        settings = json.loads(text)
    except FileNotFoundError:
        text, settings = "", {}
    hooks = settings.get("hooks", {})
    new_hooks = {}
    for event, groups in hooks.items():
        kept = [g for g in groups if not _is_ours(g)]
        if kept:
            new_hooks[event] = kept
    if enabled:
        for event in HOOK_EVENTS:
            new_hooks.setdefault(event, []).append({"hooks": [dict(_HOOK)]})
    if new_hooks == hooks:
        return False
    if new_hooks:
        settings["hooks"] = new_hooks
    else:
        settings.pop("hooks", None)
    backup = SETTINGS.with_name("settings.json.orbit-backup")
    if text and not backup.exists():
        backup.write_text(text, encoding="utf-8")
    SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("Hooky Orbitu v %s %s", SETTINGS, "přidány" if enabled else "odebrány")
    return True
