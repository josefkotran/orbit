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
INLINE_MAX = 6000  # a longer task goes to the session as a file (cmd's line holds ~8000 characters)
SOURCE = "úkol z poznámek Orbitu"  # "Pepa (úkol z poznámek Orbitu): …" starts the session's first message


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


def start_session(folder: str, prompt: str, name: str, timeout: float = 30) -> tuple[bool, str]:
    """Opens the task's session (agent_tools.open_session: the folder must be one of the user's, Windows Terminal,
    minimized) in a small process of its own: it attaches to the new console to minimize it, which Orbit's own
    process mustn't. Blocking (a worker thread): (True, its message) or (False, why not)."""
    code = ("import json, sys, threading; sys.path.insert(0, sys.argv[1]); from app import agent_tools\n"
            "try:\n"
            "    r = {'ok': True, 'text': agent_tools.open_session(sys.argv[2], sys.argv[3], source=sys.argv[4])}\n"
            "except Exception as e:\n"
            "    r = {'ok': False, 'text': str(e)}\n"
            "[t.join(12) for t in threading.enumerate() if t is not threading.main_thread()]\n"
            "print(json.dumps(r))")
    python = Path(sys.executable).with_name("python.exe")
    try:
        run = subprocess.run([str(python if python.is_file() else sys.executable), "-I", "-c", code,
                              str(Path(__file__).resolve().parent.parent), folder, prompt, SOURCE],
                             env=dict(os.environ, ORBIT_USER_NAME=name), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        result = json.loads(run.stdout.strip().splitlines()[-1])
        return bool(result["ok"]), str(result["text"])
    except Exception as e:
        log.exception("Relaci pro úkol nejde otevřít")
        return False, f"Relaci nejde otevřít: {e}"
