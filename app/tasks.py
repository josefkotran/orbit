"""The user's own tasks, Orbit's notebook (the window is notebook.py): a title, the folder to work in, context and
notes added over time, and where it stands: Poznámky (new), V plánu, Aktivní, Hotovo. Every CHECK_EVERY_MS Orbit looks
at the active ones, and the first that hasn't run yet it offers to start: a new Claude Code session in its folder with
the task as the first message, after the user's yes (main.Dictation._check_tasks).

Stored in <data>/tasks.json (written atomically, never in git: it's the user's own text). No Qt here."""
import json
import logging
import os
import re
import subprocess
import sys
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

STATUSES = {"active": "Aktivní", "planned": "V plánu", "note": "Poznámky", "done": "Hotovo"}  # in the window's order
CHECK_EVERY_MS = 30 * 60 * 1000
FIRST_CHECK_MS = 2 * 60 * 1000  # after Orbit starts (a restart used to push every waiting task half an hour back)
NEXT_SOON_MS = 60 * 1000  # a task started or turned down: the next active one is offered a minute later
RETRY_MS = 10 * 60 * 1000  # an offer nobody answered (or that had to give way) comes back after this
INLINE_MAX = 6000  # a longer task goes to the session as a file (cmd's line holds ~8000 characters)
SOURCE = "úkol z poznámek Orbitu"  # "Pepa (úkol z poznámek Orbitu): …" starts the session's first message
INBOX_EVERY_MS = 3000  # how often Orbit looks for what a task's session has to say (Dictation._check_inbox)
INBOX_TEXT_MAX = 2000  # characters of one message from a session
INBOX_UNREADABLE_S = 10  # a file that isn't JSON yet may still be being written: dropped only after this long


@dataclass
class Task:
    id: str
    title: str = ""
    folder: str = ""  # one of agent.project_folders(): where its session works
    context: str = ""
    notes: list = field(default_factory=list)  # [{"at": epoch seconds, "text": "…"}], oldest first
    status: str = "note"  # a key of STATUSES
    created: float = 0.0
    started: float = 0.0  # a session was opened for it then (0 = not yet)
    declined: float = 0.0  # the user said no to starting it: not offered again by itself (only "Začít teď")


def path() -> Path:
    return config.DATA_DIR / "tasks.json"


def new(title: str = "", status: str = "note") -> Task:
    return Task(id=uuid.uuid4().hex[:12], title=title, status=status, created=time.time())


def load() -> list[Task]:
    """The tasks in their order. A file that can't be read is copied aside (it's the user's text), then it's empty."""
    try:
        data = json.loads(path().read_text(encoding="utf-8-sig"))
        known = {f.name for f in fields(Task)}
        items = [Task(**{k: v for k, v in item.items() if k in known}) for item in data.get("tasks", [])
                 if isinstance(item, dict) and isinstance(item.get("id"), str)]
        for t in items:
            t.status = t.status if t.status in STATUSES else "note"
            t.notes = [n for n in t.notes if isinstance(n, dict) and isinstance(n.get("text"), str)]
        return items
    except FileNotFoundError:
        return []
    except Exception:
        log.exception("Úkoly nejde načíst")
        try:
            backup = path().with_name(f"tasks.json.bad-{time.strftime('%Y%m%d-%H%M%S')}")
            backup.write_bytes(path().read_bytes())
        except OSError:
            pass
        return []


def save(tasks: list[Task]) -> None:
    """A temporary file swapped in: a crash never leaves half of the user's notes."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name("tasks.json.tmp")
    tmp.write_text(json.dumps({"version": 1, "tasks": [asdict(t) for t in tasks]}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, target)


def settle_started(items: list[Task]) -> bool:
    """A task whose session Orbit opened is off the user's plate: it goes to Hotovo (Pepa, 8 Oct: once its session
    runs it should leave the active ones). For tasks started before that rule. True when something moved."""
    moved = False
    for t in items:
        if t.status == "active" and t.started:
            t.status, moved = "done", True
    return moved


def next_to_offer(tasks: list[Task]) -> Task | None:
    """The first active task (the top one comes first) that has a folder, hasn't run and wasn't turned down."""
    return next((t for t in tasks if t.status == "active" and t.folder and not t.started and not t.declined), None)


def when(stamp: float) -> str:
    """"9:30" today, "7. 10. 9:30" another day."""
    t = time.localtime(stamp)
    clock = f"{t.tm_hour}:{t.tm_min:02d}"
    return clock if time.strftime("%Y%m%d", t) == time.strftime("%Y%m%d") else f"{t.tm_mday}. {t.tm_mon}. {clock}"


def _clean(text: str) -> str:
    """The user's own text as the session gets it: a Markdown link as its text and address (agent_tools refuses a
    link whose address isn't shown), no invisible characters (they'd be refused too), no Orbit's voice mark."""
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\1 (\2)", text)
    text = "".join(c for c in text if c in "\n\t" or not unicodedata.category(c).startswith("C"))
    return re.sub(r"\(\s*hlasem přes orbit\s*\)", "", text, flags=re.IGNORECASE)


def prompt_for(task: Task) -> str:
    """The new session's first message: the task, its context and notes. Too long for cmd's line, it goes to a file
    in the data folder and the message points there."""
    parts = [f"Úkol: {task.title.strip() or 'bez názvu'}."]
    if task.context.strip():
        parts.append(f"Kontext: {task.context.strip()}")
    if task.notes:
        parts.append("Poznámky: " + " | ".join(f"{when(n.get('at', 0))} {n['text'].strip()}" for n in task.notes))
    text = _clean(" ".join(parts))
    if len(text) <= INLINE_MAX:
        return text
    file = config.DATA_DIR / "tasks" / f"{task.id}.md"
    file.parent.mkdir(parents=True, exist_ok=True)
    body = [f"# {task.title.strip() or 'Úkol'}", "", task.context.strip(), ""]
    body += [f"- {when(n.get('at', 0))}: {n['text'].strip()}" for n in task.notes]
    file.write_text("\n".join(body), encoding="utf-8")
    return _clean(f"Úkol: {task.title.strip() or 'bez názvu'}. Celé zadání s kontextem a poznámkami je v souboru "
                  f"{file}, přečti si ho a pracuj podle něj.")


def inbox() -> Path:
    """Where a Claude Code session working on a task (the orbit-ukoly mod, mods/orbit-ukoly) leaves what it has to say
    about it: one JSON file per message, {"task", "action": "note" | "done", "text", "from": "claude" | "user", "at"}.
    Orbit reads and removes them (Dictation._check_inbox), so tasks.json keeps a single writer."""
    return config.DATA_DIR / "tasks" / "inbox"


def read_inbox() -> list[dict]:
    """The messages waiting, oldest first, each file removed once read. One that isn't JSON yet may still be being
    written and waits; after INBOX_UNREADABLE_S, or with a wrong shape, it's dropped (and logged)."""
    try:
        files = sorted(inbox().glob("*.json"))
    except OSError:
        return []
    messages = []
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            try:
                if time.time() - file.stat().st_mtime < INBOX_UNREADABLE_S:
                    continue
            except OSError:
                continue
            data = None
        try:
            file.unlink()
        except OSError:
            continue  # still open elsewhere: next time
        ok = (isinstance(data, dict) and isinstance(data.get("task"), str) and data.get("action") in ("note", "done")
              and isinstance(data.get("text", ""), str))
        if not ok:
            log.warning("Zpráva k úkolu má špatný tvar, zahozena: %s", file.name)
            continue
        at = data.get("at")
        messages.append({"task": data["task"], "action": data["action"],
                         "text": _clean(data.get("text", "")).strip()[:INBOX_TEXT_MAX],
                         "from": "user" if data.get("from") == "user" else "claude",
                         "at": float(at) if isinstance(at, (int, float)) and 0 < at < time.time() + 60 else time.time()})
    return messages


def apply_inbox(items: list[Task], messages: list[dict]) -> list[tuple[Task, dict]]:
    """A session's note goes to its task (with "Claude:" before what Claude wrote), "done" moves the task to Hotovo.
    Returns what was applied; a message for a task that's gone is left out."""
    applied = []
    for msg in messages:
        task = next((t for t in items if t.id == msg["task"]), None)
        if task is None:
            log.info("Zpráva k úkolu, který už není: zahozena")
            continue
        author = "Claude: " if msg["from"] == "claude" else ""
        if msg["action"] == "done":
            task.status = "done"
            text = f"{author}hotovo" + (f" – {msg['text']}" if msg["text"] else "")
        elif msg["text"]:
            text = author + msg["text"]
        else:
            continue
        task.notes.append({"at": msg["at"], "text": text})
        applied.append((task, msg))
    return applied


def start_session(folder: str, prompt: str, name: str, task_id: str = "", timeout: float = 30) -> tuple[bool, str]:
    """Opens the task's session (agent_tools.open_session: the folder must be one of the user's, Windows Terminal,
    minimized) in a small process of its own: it attaches to the new console to minimize it, which Orbit's own
    process mustn't. task_id goes to the session as ORBIT_TASK_ID (the orbit-ukoly mod shows the task there).
    Blocking (a worker thread): (True, its message) or (False, why not)."""
    code = ("import json, sys, threading; sys.path.insert(0, sys.argv[1]); from app import agent_tools\n"
            "try:\n"
            "    r = {'ok': True, 'text': agent_tools.open_session(sys.argv[2], sys.argv[3], source=sys.argv[4],\n"
            "                                                     task_id=sys.argv[5])}\n"
            "except Exception as e:\n"
            "    r = {'ok': False, 'text': str(e)}\n"
            "[t.join(12) for t in threading.enumerate() if t is not threading.main_thread()]\n"
            "print(json.dumps(r))")
    python = Path(sys.executable).with_name("python.exe")
    try:
        run = subprocess.run([str(python if python.is_file() else sys.executable), "-I", "-c", code,
                              str(Path(__file__).resolve().parent.parent), folder, prompt, SOURCE, task_id],
                             env=dict(os.environ, ORBIT_USER_NAME=name), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        result = json.loads(run.stdout.strip().splitlines()[-1])
        return bool(result["ok"]), str(result["text"])
    except Exception as e:
        log.exception("Relaci pro úkol nejde otevřít")
        return False, f"Relaci nejde otevřít: {e}"
