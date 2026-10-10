"""Past Claude Code sessions (the clock above Orbit's panel, "Historie relací…" in its menu), the ones `claude
--resume` offers: Claude Code's transcripts (<Claude Code>/projects/<folder>/<session id>.jsonl), newest first, each
with its name (what /rename gave it, else what Claude Code named it, else its first prompt: the order of Claude Code's
own picker), its folder, git branch, and the first and the newest prompt. Resuming one runs `claude --resume <id>` in
its folder (favorites.start_session → agent_tools.resume_folder, a window like the user's own sessions).

Left out, as Claude Code's picker leaves them out: headless runs (entrypoint "sdk-…": Orbit's own agent, vocabulary
learning, the user's scripts), subagents' transcripts, sessions with nothing said in them and ones that went on in
another session ("continued-in"). The transcript format isn't an official interface (neither is it for sessions.py):
what can't be read is left out. Only the start and the end of a transcript are read (they reach 70 MB, 3 GB all of
them), and only again when it changed: a transcript that grew only gets its end read again. No Qt."""
import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import paths

BLOCK = 256 * 1024
HEAD_MAX = 4 * 1024 * 1024  # the first prompt further in than this (huge attachments before it): none
BACK_MAX = 8 * 1024 * 1024  # how far back from the end its name and the newest prompt are looked for
PROMPT_MAX = 2000  # characters kept of a prompt
_ID_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_COMMAND_RE = re.compile(r"<command-name>\s*(/?[\w:.-]+)\s*</command-name>")
_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_BRANCH_RE = re.compile(rb'"gitBranch":"([^"\\]*)"')
_PROMPT_INDEX_RE = re.compile(rb'"promptIndex":(\d+)')
_TAIL_MARKS = (b'"custom-title"', b'"ai-title"', b'"type":"summary"', b'"last-prompt"', b'"type":"user"',
               b'"continued-in"')


def is_id(text: str) -> bool:
    return bool(_ID_RE.fullmatch(text or ""))


@dataclass
class Past:
    id: str
    transcript: str
    cwd: str = ""  # the folder it started in (its project folder, where it's resumed)
    created: float = 0.0  # its first entry
    modified: float = 0.0  # the transcript's last change
    title: str = ""  # /rename's, else Claude Code's (ai-title), else a summary
    first: str = ""  # the first prompt
    last: str = ""  # the newest prompt
    branch: str = ""  # git branch at its end ("HEAD" without a branch)
    prompts: int = 0  # how many prompts (Claude Code's own count, 0 = not known)
    continued_in: str = ""  # it went on in this session ("continued-in")

    @property
    def folder(self) -> str:
        return Path(self.cwd).name or self.cwd

    @property
    def name(self) -> str:
        return self.title or " ".join(self.first.split())[:120] or self.id[:8]


def prompt_of(entry: dict) -> str:
    """What the user wrote in a transcript entry, "" when the entry isn't their prompt (a tool result, Claude Code's
    own note, a task notification, a message from another session…). A slash command as "/loop 5m …"."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain") \
            or entry.get("isCompactSummary"):
        return ""
    origin = entry.get("origin")
    if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
        return ""
    message = entry.get("message")
    if not isinstance(message, dict) or message.get("role") != "user":
        return ""
    content = message.get("content")
    if isinstance(content, list):  # text and images; tool results have no text block of their own
        content = "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text")
    text = content.strip() if isinstance(content, str) else ""
    if command := _COMMAND_RE.search(text):
        args = _ARGS_RE.search(text)
        return " ".join(f"{command.group(1)} {args.group(1) if args else ''}".split())[:PROMPT_MAX]
    if text.startswith(("<", "[Request interrupted", "Caveat:")):
        return ""
    return text[:PROMPT_MAX]


def _forward(f, limit: int):
    """Whole lines from the file's start, up to limit bytes."""
    carry, read = b"", 0
    while read < limit:
        block = f.read(BLOCK)
        if not block:
            if carry:
                yield carry
            return
        read += len(block)
        lines = (carry + block).split(b"\n")
        carry = lines.pop()
        yield from lines


def _backward(f, end: int, limit: int):
    """Whole lines from the end backwards, up to limit bytes."""
    carry, pos = b"", end
    while pos > 0 and end - pos < limit:
        start = max(0, pos - BLOCK)
        f.seek(start)
        lines = (f.read(pos - start) + carry).split(b"\n")
        carry = lines.pop(0) if start else b""  # may start mid-line: completed by the block before it
        yield from reversed(lines)
        pos = start


def _loads(line: bytes) -> dict | None:
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    return entry if isinstance(entry, dict) else None


@dataclass
class _Head:
    """What the start of a transcript says (it doesn't change while the transcript grows)."""
    cwd: str = ""
    created: float = 0.0
    first: str = ""
    headless: bool = False
    sidechain: bool = False


def _when(entry: dict) -> float:
    try:
        return datetime.fromisoformat(str(entry.get("timestamp")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _read_head(f) -> _Head:
    head, entrypoint, message_seen = _Head(), "", False
    for line in _forward(f, HEAD_MAX):
        if not line.strip() or not (b'"cwd"' in line or b'"type":"user"' in line):
            continue
        entry = _loads(line)
        if entry is None:
            continue
        head.cwd = head.cwd or str(entry.get("cwd") or "")
        head.created = head.created or _when(entry)
        entrypoint = entrypoint or str(entry.get("entrypoint") or "")
        if entry.get("type") in ("user", "assistant") and not message_seen:
            message_seen, head.sidechain = True, bool(entry.get("isSidechain"))
        head.first = head.first or prompt_of(entry)
        if head.cwd and head.first and entrypoint:
            break
    head.headless = entrypoint.startswith("sdk")
    return head


@dataclass
class _Tail:
    """What its end says: its name, the newest prompt, the branch, where it went on."""
    custom: str = ""
    ai: str = ""
    summary: str = ""
    last: str = ""  # the newest prompt the user wrote
    noted: str = ""  # Claude Code's "last-prompt" note, only when no prompt is that near the end: when it puts its
    # notes at the end again (leaving the session), the note can be the first prompt again
    branch: str = ""
    prompts: int = 0
    continued_in: str = ""


def _read_tail(f, size: int) -> _Tail:
    tail = _Tail()
    for line in _backward(f, size, BACK_MAX):
        if not tail.branch and (m := _BRANCH_RE.search(line)):
            tail.branch = m.group(1).decode("utf-8", "replace")
        if not tail.prompts and (m := _PROMPT_INDEX_RE.search(line)):
            tail.prompts = int(m.group(1))
        if not any(mark in line for mark in _TAIL_MARKS):
            continue
        entry = _loads(line)
        if entry is None:
            continue
        kind = entry.get("type")
        if kind == "custom-title" and not tail.custom:
            tail.custom = " ".join(str(entry.get("customTitle") or "").split())
        elif kind == "ai-title" and not tail.ai:
            tail.ai = " ".join(str(entry.get("aiTitle") or "").split())
        elif kind == "summary" and not tail.summary:
            tail.summary = " ".join(str(entry.get("summary") or "").split())
        elif kind == "last-prompt" and not tail.noted:
            tail.noted = str(entry.get("lastPrompt") or "").strip()[:PROMPT_MAX]
        elif kind == "continued-in" and not tail.continued_in:
            tail.continued_in = str(entry.get("continuedInSessionId") or "")
        elif kind == "user" and not tail.last:
            tail.last = prompt_of(entry)
        if (tail.custom or tail.ai) and tail.last and tail.branch and tail.prompts:
            break
    return tail


def read(transcript: Path, head: _Head | None = None) -> tuple[_Head, Past | None]:
    """One transcript (head: what its start said before, when it only grew since): what its start says, and the
    session (None when it isn't one to resume: headless, a subagent's, nothing said in it)."""
    with open(transcript, "rb") as f:
        size, modified = f.seek(0, 2), transcript.stat().st_mtime
        if head is None:
            f.seek(0)
            head = _read_head(f)
        if head.headless or head.sidechain or not head.cwd:
            return head, None
        tail = _read_tail(f, size)
    title = tail.custom or tail.ai or tail.summary
    if not (head.first or title):
        return head, None
    return head, Past(transcript.stem, str(transcript), head.cwd, head.created or modified, modified, title,
                      head.first, tail.last or tail.noted or head.first, tail.branch, tail.prompts, tail.continued_in)


class Index:
    """All past sessions, read again only where a transcript changed (scan from any thread, one at a time)."""

    def __init__(self):
        self._lock = threading.Lock()
        # transcript -> (size, mtime, what its start says, the session or None)
        self._cache: dict[str, tuple[int, float, _Head, Past | None]] = {}
        self._by_id: dict[str, Past] = {}

    def scan(self) -> list[Past]:
        with self._lock:
            found, seen = [], set()
            try:
                files = [p for p in (paths.claude_dir() / "projects").glob("*/*.jsonl") if is_id(p.stem)]
            except OSError:
                files = []
            for path in files:
                key = str(path)
                seen.add(key)
                try:
                    stat = path.stat()
                except OSError:
                    continue
                cached = self._cache.get(key)
                if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime:
                    past = cached[3]
                else:
                    grew = cached is not None and stat.st_size > cached[0]
                    try:
                        head, past = read(path, cached[2] if grew else None)
                    except OSError:
                        continue
                    self._cache[key] = (stat.st_size, stat.st_mtime, head, past)
                if past is not None:
                    found.append(past)
            self._cache = {k: v for k, v in self._cache.items() if k in seen}
            ids = {p.id for p in found}
            # went on in another session that is still there: that one is the session now (as in Claude Code)
            found = [p for p in found if not (p.continued_in in ids and p.continued_in != p.id)]
            found.sort(key=lambda p: p.modified, reverse=True)
            self._by_id = {p.id: p for p in found}
            return found

    def get(self, session_id: str) -> Past | None:
        return self._by_id.get(session_id)


def fold(text: str) -> str:
    """For the search: lower case without diacritics ("cenik" finds "Ceník")."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def matches(past: Past, query: str) -> bool:
    """Every word of the (folded) query is in its name, folder, branch or prompts."""
    hay = fold(f"{past.name} {past.cwd} {past.branch} {past.first} {past.last} {past.id}")
    return all(word in hay for word in query.split())


def when(at: float) -> str:
    """"dnes 14:32", "včera 9:05", "8. 10. 14:32", a year ago with the year."""
    t, today = datetime.fromtimestamp(at), datetime.now().date()
    clock = f"{t.hour}:{t.minute:02d}"
    if t.date() == today:
        return f"dnes {clock}"
    if t.date() == today - timedelta(days=1):
        return f"včera {clock}"
    return f"{t.day}. {t.month}. " + (f"{t.year} " if t.year != today.year else "") + clock


def kept_days() -> int:
    """How long Claude Code keeps transcripts (cleanupPeriodDays in its settings.json, 30 days by default)."""
    try:
        days = json.loads((paths.claude_dir() / "settings.json").read_text(encoding="utf-8-sig")).get(
            "cleanupPeriodDays")
    except (OSError, ValueError, AttributeError):
        days = None
    return days if isinstance(days, int) and not isinstance(days, bool) and days > 0 else 30
