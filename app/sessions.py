"""Overview of running Claude Code sessions: what each one does, whether it waits for the user, how full its context
is, which permission mode it runs in.

Which sessions run comes from Claude Code's own list (~/.claude/sessions/<pid>.json). Claude Code hooks (put into its
settings.json by claude_settings.set_hooks) run app/cc_hook.py, which leaves one file per session and event in
<data>/sessions/ – that's where "waits for you", "done", the answers and the permission mode come from. Orbit's status
line (app/cc_status.py) leaves <data>/sessions/status/<session>.json with the exact context use. Everything else – the
session's name, the terminal window – is worked out here. Claude Code's folder: paths.claude_dir().
"""
import ctypes
import json
import logging
import re
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .config import SESSIONS_DIR

log = logging.getLogger(__name__)

STATUS_DIR = SESSIONS_DIR / "status"  # cc_status.py's files
DONE_FRESH_S = 600  # "hotovo" for this long after a turn, then "v klidu"
WAITING_TYPES = ("permission_prompt", "elicitation_dialog")
STATE_LABELS = {"working": "pracuje", "waiting": "čeká na tebe", "done": "hotovo", "idle": "v klidu",
                "error": "chyba"}
STALE_S = 12 * 3600  # sessions whose process can't be checked disappear after this long without an event
STATUS_FRESH_S = 600  # the status line's context counts while it isn't this much older than the transcript

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_kernel32.OpenProcess.restype = wintypes.HANDLE
_user32.GetForegroundWindow.restype = wintypes.HWND


def _settings() -> Path:
    return paths.claude_dir() / "settings.json"


def _registry_dir() -> Path:
    """Claude Code's list of running sessions, <pid>.json each."""
    return paths.claude_dir() / "sessions"


@dataclass
class Session:
    id: str
    cwd: str = ""
    transcript: str = ""
    pid: int = 0
    hwnd: int = 0
    shared: bool = False  # another session shows in the same window (tabs of one Windows Terminal)
    state: str = "idle"
    since: float = 0.0  # when the current state started
    announced: float = 0.0  # since of the last state change told to the user (never the same news twice)
    turn_s: float = 0.0  # how long the last finished turn took
    message: str = ""  # what it waits for / its last answer
    context_tokens: int = 0
    context_size: int = 0
    context_pct: float | None = None  # exact, from the status line (else tokens / size, estimated)
    topic: str = ""  # what Claude Code named the session ("Analýza ceníků a katalogů Profodu")
    started: float = 0.0  # when Orbit first saw it (keeps the overview's order stable)
    peer: str = ""  # its address for messages between sessions ("m-tex-41"), from Claude Code's list
    prompt: str = ""  # what the user asked it last
    mode: str = ""  # permission mode: default, acceptEdits, plan, auto, dontAsk, bypassPermissions ("" = not known)
    bypass_seen: bool = False  # it has run in bypassPermissions (so it was started with bypass allowed)

    @property
    def folder(self) -> str:
        return Path(self.cwd).name or self.cwd or "?"

    @property
    def name(self) -> str:
        return self.topic or self.folder

    @property
    def context(self) -> float | None:
        if self.context_pct is not None:
            return self.context_pct / 100
        return self.context_tokens / self.context_size if self.context_size else None

    @property
    def mode_class(self) -> str:
        """Claude Code's class for messages between sessions (a message from the other class waits for approval):
        "bypass" = runs tools without asking, "prompting" otherwise, "" = not known yet."""
        if self.mode == "bypassPermissions" or (self.mode == "plan" and self.bypass_seen):
            return "bypass"
        return "prompting" if self.mode else ""

    def tooltip(self) -> str:
        lines = [f"{self.topic} ({self.folder})" if self.topic else self.folder,
                 STATE_LABELS[self.state] + (f": {summary(self.message, 1)}" if self.message and
                                             self.state in ("waiting", "error") else "")]
        if self.context is not None:
            used = f"{self.context_tokens // 1000} tis. z {_size_text(self.context_size)} tokenů" \
                if self.context_size else ""
            lines.append(f"Kontext {self.context * 100:.0f} %" + (f" ({used})" if used else ""))
        if self.mode_class == "bypass":
            lines.append("Běží bez ptaní na oprávnění.")
        if self.hwnd:
            lines.append("Klikni a přepneš se do jejího okna (kartu si vyber)." if self.shared else
                         "Klikni a přepneš se do jejího terminálu.")
        return "\n".join(lines)


def _size_text(tokens: int) -> str:
    return f"{tokens // 1_000_000} mil." if tokens >= 1_000_000 else f"{tokens // 1000} tis."


class SessionTracker:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        # transcript path -> (mtime, context tokens, topic, permission mode, bypass seen)
        self._transcript_cache: dict[str, tuple[float, int, str, str, bool]] = {}
        self._status_cache: dict[str, tuple[float, dict]] = {}  # session id -> (mtime, status line record)
        self._first = True

    def poll(self) -> list[tuple[Session, str]]:
        """Re-reads the hook files. Returns (session, new state) for changes worth telling the user about
        (nothing on the first call, so a restart of Orbit doesn't repeat old news)."""
        records: dict[str, dict[str, dict]] = {}
        try:
            files = list(SESSIONS_DIR.glob("*.json"))
        except OSError:
            files = []
        for f in files:
            sid, _, event = f.stem.partition(".")
            try:
                record = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # being written right now
            if isinstance(record, dict):
                records.setdefault(sid, {})[event] = record

        running, headless = _running()
        changes = []
        for sid in set(records) | set(running):
            events, reg = records.get(sid, {}), running.get(sid, {})
            latest = max(events.values(), key=lambda r: r.get("time", 0)) if events else {}
            if not reg and (latest.get("pid", 0) in headless or
                            not _alive(latest.get("pid", 0), latest.get("hwnd", 0), latest.get("time", 0))):
                for f in SESSIONS_DIR.glob(f"{sid}.*.json"):
                    f.unlink(missing_ok=True)
                continue
            s = self.sessions.get(sid) or Session(sid)
            before = s.state
            # the folder the session started in: hooks report the current one, which follows a `cd` (m-tex → www)
            s.cwd = reg.get("cwd") or events.get("SessionStart", {}).get("cwd") or s.cwd or latest.get("cwd", "")
            s.transcript = latest.get("transcript_path") or s.transcript or _find_transcript(sid)
            s.pid = reg.get("pid") or latest.get("pid") or s.pid
            s.peer = reg.get("name") or s.peer
            s.prompt = events.get("UserPromptSubmit", {}).get("prompt") or s.prompt
            s.hwnd = next((r["hwnd"] for r in sorted(events.values(), key=lambda r: -r.get("time", 0))
                           if r.get("hwnd")), s.hwnd)
            s.started = s.started or reg.get("startedAt", 0) / 1000 or \
                min((r.get("time", 0) for r in events.values()), default=time.time())
            if events:
                self._update_state(s, events)
                if reg.get("status") == "busy" and s.state in ("idle", "done") \
                        and reg.get("statusUpdatedAt", 0) / 1000 > s.since:
                    s.state = "working"  # a session whose hooks don't run (started before they were installed)
                elif reg.get("status") == "idle" and s.state == "working" \
                        and reg.get("statusUpdatedAt", 0) / 1000 > s.since + 2:
                    s.state = "idle"  # interrupted (Esc, "Stop."): Claude Code runs no Stop hook then
            else:  # no hook event yet: Claude Code's own busy/idle
                s.state = "working" if reg.get("status") == "busy" else "idle"
            self._update_transcript(s)
            hook_mode = max((r for r in events.values() if r.get("permission_mode")), default=None,
                            key=lambda r: r.get("time", 0))
            if hook_mode:
                s.mode = str(hook_mode["permission_mode"])
                s.bypass_seen = s.bypass_seen or s.mode == "bypassPermissions"
            self._update_status(s)
            if not s.hwnd or not _user32.IsWindow(wintypes.HWND(s.hwnd)) \
                    or not _user32.IsWindowVisible(wintypes.HWND(s.hwnd)):
                s.hwnd = _terminal_by_title(s.topic)
            if self._first:
                s.announced = s.since
            elif s.state != before and s.state in ("waiting", "done", "error") and s.since > s.announced:
                s.announced = s.since  # a "busy" blip in between doesn't bring back an old "hotovo"
                changes.append((s, s.state))
            self.sessions[sid] = s
        for sid in set(self.sessions) - set(records) - set(running):
            del self.sessions[sid]
        windows: dict[int, int] = {}
        for s in self.sessions.values():
            windows[s.hwnd] = windows.get(s.hwnd, 0) + 1
        for s in self.sessions.values():
            s.shared = bool(s.hwnd) and windows[s.hwnd] > 1
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
            note = events.get("Notification", {})
            if note.get("notification_type") == "idle_prompt" and note.get("time", 0) > s.since:
                s.state = "idle"  # waiting for the user again without a Stop: the turn was interrupted
        elif event == "Notification":
            s.state, s.message = "waiting", rec.get("message", "")
            if self._transcript_mtime(s) > s.since + 1.5:  # the user answered the prompt, the tool is running
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

    def _update_transcript(self, s: Session) -> None:
        mtime = self._transcript_mtime(s)
        cached = self._transcript_cache.get(s.transcript)
        if not cached or cached[0] != mtime:
            lines = _tail(s.transcript)
            # the title is repeated in the transcript as it grows; the whole file is searched only the first time
            topic = _topic(lines) or (cached[2] if cached else _topic(_title_lines(s.transcript)))
            mode, bypass = _permission_mode(lines)
            cached = self._transcript_cache[s.transcript] = (mtime, _context_tokens(lines), topic,
                                                             mode or (cached[3] if cached else ""),
                                                             bypass or bool(cached and cached[4]))
        _, tokens, s.topic, mode, bypass = cached
        s.mode = mode or s.mode
        s.bypass_seen = s.bypass_seen or bypass
        s.context_tokens, s.context_pct = tokens, None
        s.context_size = (1_000_000 if tokens > 200_000 or "[1m]" in _default_model() else 200_000) if tokens else 0

    def _update_status(self, s: Session) -> None:
        """The exact context use from Orbit's status line, when it's there and current (else the estimate stays)."""
        path = STATUS_DIR / f"{s.id}.json"
        try:
            mtime = path.stat().st_mtime
            cached = self._status_cache.get(s.id)
            if not cached or cached[0] != mtime:
                record = json.loads(path.read_text(encoding="utf-8"))
                cached = self._status_cache[s.id] = (mtime, record if isinstance(record, dict) else {})
        except (OSError, ValueError):
            return
        record = cached[1]
        window = record.get("context_window") if isinstance(record.get("context_window"), dict) else {}
        pct, size = window.get("used_percentage"), window.get("context_window_size")
        if not isinstance(pct, (int, float)) or record.get("time", 0) < self._transcript_mtime(s) - STATUS_FRESH_S:
            return
        s.context_pct = float(pct)
        if isinstance(size, int) and size > 0:
            usage = window.get("current_usage") if isinstance(window.get("current_usage"), dict) else {}
            used = sum(v for k, v in usage.items() if k in ("input_tokens", "cache_creation_input_tokens",
                                                            "cache_read_input_tokens") and isinstance(v, int))
            s.context_size, s.context_tokens = size, used or int(size * pct / 100)


def _running() -> tuple[dict[str, dict], set[int]]:
    """Interactive sessions from Claude Code's own list whose process still runs: session id -> its entry
    (pid, cwd, status "busy"/"idle", startedAt in ms, name = address for messages). Not an official interface
    either. Headless runs (entrypoint "sdk-cli": Orbit's own agent, vocabulary learning, the user's scripts) are left
    out; their pids come second, so hook files they left behind don't show up as sessions either."""
    found, headless = {}, set()
    try:
        files = list(_registry_dir().glob("*.json"))
    except OSError:
        return found, headless
    for f in files:
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(entry, dict):
            continue
        if str(entry.get("entrypoint", "")).startswith("sdk"):
            if entry.get("pid"):
                headless.add(entry["pid"])
        elif entry.get("sessionId") and entry.get("kind", "interactive") == "interactive" \
                and _alive(entry.get("pid", 0), 0, 0):
            found[entry["sessionId"]] = entry
    return found, headless


def _find_transcript(session_id: str) -> str:
    return str(next(paths.claude_dir().glob(f"projects/*/{session_id}.jsonl"), ""))


_WT_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
_CONSOLE_CLASS = "ConsoleWindowClass"  # the classic console: sessions the voice agent opened minimized


def _title(hwnd: int) -> str:
    """A terminal's title without Claude Code's spinner ("✳ Analýza ceníků…" → "Analýza ceníků…")."""
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(wintypes.HWND(hwnd), buf, 256)
    return re.sub(r"^[^\w]+", "", buf.value).strip()


def _terminal_by_title(topic: str) -> int:
    """The terminal window whose title is the session's topic (Claude Code puts it there after a spinner,
    "✳ Analýza ceníků…"). For sessions whose hooks haven't told us their window yet."""
    if not topic:
        return 0
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def check(hwnd, _):
        cls = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(wintypes.HWND(hwnd), cls, 64)
        if cls.value in (_WT_CLASS, _CONSOLE_CLASS) and _title(hwnd) == topic:
            found.append(hwnd)
        return True

    _user32.EnumWindows(check, 0)
    return found[0] if len(found) == 1 else 0  # two windows with the same title: can't tell


def topic(transcript: str) -> str:
    """What Claude Code named the session, from its transcript ("" if it hasn't named it yet)."""
    return _topic(_tail(transcript)) or _topic(_title_lines(transcript))


def _tail(transcript: str) -> list[bytes]:
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 512 * 1024))
            return f.read().splitlines()
    except (OSError, ValueError):
        return []


def _title_lines(transcript: str) -> list[bytes]:
    try:
        with open(transcript, "rb") as f:
            return [line for line in f if b'"ai-title"' in line]
    except (OSError, ValueError):
        return []


def _topic(lines: list[bytes]) -> str:
    """The newest {"type": "ai-title", "aiTitle": ...} entry. The transcript format isn't an official interface –
    if it changes, sessions are simply called by their folder again."""
    for line in reversed(lines):
        if b'"ai-title"' in line:
            try:
                title = json.loads(line).get("aiTitle")
            except (ValueError, AttributeError):
                continue
            if title:
                return " ".join(str(title).split())
    return ""


_MODE_RE = re.compile(rb'"permissionMode"\s*:\s*"(\w+)"')


def _permission_mode(lines: list[bytes]) -> tuple[str, bool]:
    """The newest "permissionMode" of the user's entries, and whether it was ever bypassPermissions (in this tail)."""
    mode, bypass = "", False
    for line in reversed(lines):
        if b'"permissionMode"' in line:
            for m in _MODE_RE.finditer(line):
                mode = mode or m.group(1).decode()
                bypass = bypass or m.group(1) == b"bypassPermissions"
            if bypass:
                break
    return mode, bypass


def _context_tokens(lines: list[bytes]) -> int:
    """Tokens the session's last main-thread request sent (= how full its context is), from the transcript's end."""
    for line in reversed(lines):
        if b'"usage"' not in line:
            continue
        try:
            entry = json.loads(line)
            usage = (entry.get("message") or {}).get("usage")
        except (ValueError, AttributeError):
            continue
        if entry.get("type") == "assistant" and not entry.get("isSidechain") and isinstance(usage, dict):
            return sum(usage.get(k) or 0 for k in
                       ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return 0


_model_cache: tuple[float, str] = (0.0, "")


def _settings_json() -> dict:
    try:
        settings = json.loads(_settings().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def _default_model() -> str:
    global _model_cache
    try:
        mtime = _settings().stat().st_mtime
        if mtime != _model_cache[0]:
            _model_cache = (mtime, str(_settings_json().get("model", "")))
    except OSError:
        pass
    return _model_cache[1]


def bypass_in_use(tracked=()) -> bool:
    """Does the user run Claude Code without permission prompts (--dangerously-skip-permissions)? The newest session
    whose mode is known decides (`tracked` sessions, else the hook files); with none known, Claude Code's settings
    (the bypass warning switched off for good, or bypass as the default mode)."""
    known = [(s.since or s.started, s.mode) for s in tracked if s.mode and s.mode != "plan"]
    if not known:
        try:
            files = list(SESSIONS_DIR.glob("*.json"))
        except OSError:
            files = []
        for f in files:
            try:
                record = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(record, dict) and record.get("permission_mode") not in (None, "", "plan"):
                known.append((record.get("time", 0), str(record["permission_mode"])))
    if known:
        return max(known)[1] == "bypassPermissions"
    settings = _settings_json()
    permissions = settings.get("permissions") if isinstance(settings.get("permissions"), dict) else {}
    return settings.get("skipDangerousModePermissionPrompt") is True or \
        permissions.get("defaultMode") == "bypassPermissions"


def bypass_prompt_skipped() -> bool:
    """Has the user switched Claude Code's "Bypass Permissions mode – accept?" question off for good?"""
    return _settings_json().get("skipDangerousModePermissionPrompt") is True


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
            # STILL_ACTIVE and not a reused PID. Claude Code's auto-update renames the binary of running sessions to
            # claude.exe.old.<n>, so only the start of the file name is checked.
            return code.value == 259 and Path(name.value).name.lower().startswith("claude.exe")
        finally:
            _kernel32.CloseHandle(handle)
    if hwnd:
        return bool(_user32.IsWindow(wintypes.HWND(hwnd)))
    return time.time() - last_event < STALE_S


def is_foreground(s: Session) -> bool:
    """Is the user looking at the session? With several sessions in one window (tabs), only when the window's title
    is this session's topic (Claude Code shows the active tab's)."""
    if not s.hwnd or _user32.GetForegroundWindow() != s.hwnd:
        return False
    return not s.shared or (bool(s.topic) and _title(s.hwnd) == s.topic)


def focus(s: Session) -> bool:
    """Brings the session's window to the front (with tabs, the window; the tab is up to the user)."""
    return bool(s.hwnd) and focus_window(s.hwnd)


def focus_window(handle: int) -> bool:
    hwnd = wintypes.HWND(handle)
    if not _user32.IsWindow(hwnd):
        return False
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if _user32.SetForegroundWindow(hwnd):
        return True
    # Windows lets only the app with the last input change the foreground; sharing input state with the current
    # foreground thread for a moment gets around that without sending any keys.
    fg_thread = _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), None)
    our_thread = _kernel32.GetCurrentThreadId()
    attached = bool(fg_thread) and fg_thread != our_thread and _user32.AttachThreadInput(our_thread, fg_thread, True)
    try:
        _user32.BringWindowToTop(hwnd)
        return bool(_user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
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
