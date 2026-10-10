"""Favourite folders (the + above Orbit's panel, and "Nová relace Claude Code" in its menu): the user's repos, each
one click from a new Claude Code session in it, and new repos made right there (a folder, git init). Which folders
show is the user's own choice (config favorite_folders, "Vybrat složky…", favoritesview.py). The session opens through
agent_tools.open_folder in a small process of its own: it attaches to the new console to find its window and bring it
to the front, which Orbit's own process mustn't. No Qt."""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

log = logging.getLogger(__name__)

NAME_MAX = 100
# names Windows keeps for devices, also with an extension ("con.txt")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _key(folder: str) -> str:
    return os.path.normcase(os.path.normpath(folder))


def clean(folders) -> list[str]:
    """Full local paths, each once (Windows compares them without case), in the order given."""
    seen, out = set(), []
    for folder in folders if isinstance(folders, list) else []:
        if not isinstance(folder, str) or not folder.strip():
            continue
        path = os.path.normpath(folder.strip())
        if os.path.isabs(path) and _key(path) not in seen:
            seen.add(_key(path))
            out.append(path)
    return out


def contains(folders: list[str], folder: str) -> bool:
    return _key(folder) in {_key(f) for f in folders}


def add(folders: list[str], folder: str) -> list[str]:
    return clean([*folders, folder])


def ordered(folders: list[str]) -> list[str]:
    """By name, as the panel orders sessions by folder."""
    return sorted(folders, key=lambda f: (Path(f).name.lower(), f.lower()))


def labels(folders: list[str]) -> dict[str, str]:
    """How each folder shows: its name, with the folder above it when another one has the same name ("web (ondra)")."""
    counts = Counter(Path(f).name.lower() for f in folders)
    return {f: f"{Path(f).name} ({Path(f).parent.name})" if counts[Path(f).name.lower()] > 1 and Path(f).parent.name
            else Path(f).name or f for f in folders}


def default_parent(folders: list[str]) -> str:
    """Where a new repo goes: the folder most of the user's folders are in (C:\\Users\\josef), else the home folder."""
    parents = Counter(_key(str(Path(f).parent)) for f in folders)
    original = {_key(str(Path(f).parent)): str(Path(f).parent) for f in folders}
    for key, _ in parents.most_common():
        if os.path.isdir(original[key]):
            return original[key]
    return str(Path.home())


def name_problem(name: str) -> str:
    """Why `name` can't be a new folder's name ("" = it can)."""
    name = name.strip()
    if not name:
        return "Napiš název složky."
    if len(name) > NAME_MAX:
        return "Název je moc dlouhý."
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        return 'Název nesmí obsahovat < > : " / \\ | ? *'
    if name.endswith((".", " ")):
        return "Název nesmí končit tečkou ani mezerou."
    if name.split(".")[0].strip().lower() in RESERVED:
        return f"Název „{name}“ si nechávají Windows pro sebe, zvol jiný."
    return ""


def git_exe() -> str | None:
    return shutil.which("git")  # never .\git.cmd from the current folder: Orbit.pyw sets NoDefaultCurrentDirectory…


def create(parent: str, name: str, git: bool) -> tuple[str, str]:
    """Makes the folder parent\\name, with git init in it when git is True: (its path, what went wrong with git, "" =
    nothing). Raises ValueError with a Czech message when the folder can't be made (it is then not there)."""
    problem = name_problem(name)
    if problem:
        raise ValueError(problem)
    parent = parent.strip()
    if parent.startswith(("\\\\", "//")):
        raise ValueError("Na síťovém disku (\\\\server\\…) relaci neotevřu, vyber místní složku.")
    if not os.path.isabs(parent) or not os.path.isdir(parent):
        raise ValueError(f"Složka {parent or '(žádná)'} neexistuje.")
    path = Path(parent) / name.strip()
    if path.exists():
        raise ValueError(f"{path} už existuje. Přidáš ji přes „Vybrat složky…“.")
    try:
        path.mkdir()
    except OSError as e:
        raise ValueError(f"Složku {path} nejde založit: {e.strerror or e}") from None
    return str(path), _git_init(path) if git else ""


def _git_init(path: Path) -> str:
    exe = git_exe()
    if not exe:
        return "git tu není nainstalovaný, složka je bez gitu."
    try:
        run = subprocess.run([exe, "init"], cwd=path, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30, stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("git init v nové složce selhal: %s", e)
        return "git init selhal, složka je bez gitu."
    if run.returncode:
        log.warning("git init v nové složce skončil kódem %s: %s", run.returncode, run.stderr.strip()[-300:])
        return "git init selhal, složka je bez gitu."
    return ""


def start_session(folder: str, resume: str = "", timeout: float = 30) -> tuple[bool, str]:
    """A new Claude Code session in folder (agent_tools.open_folder: Windows Terminal like the user's own sessions,
    brought to the front), or with resume a past session going on there (agent_tools.resume_folder, the session
    history), in a small process of its own. Blocking (a worker thread): (True, its message) or (False, why not)."""
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); from app import agent_tools\n"
            "try:\n"
            "    r = {'ok': True, 'text': agent_tools.resume_folder(sys.argv[2], sys.argv[3]) if sys.argv[3:] else\n"
            "         agent_tools.open_folder(sys.argv[2])}\n"
            "except Exception as e:\n"
            "    r = {'ok': False, 'text': str(e)}\n"
            "print(json.dumps(r))")
    python = Path(sys.executable).with_name("python.exe")
    try:
        run = subprocess.run([str(python if python.is_file() else sys.executable), "-I", "-c", code,
                              str(Path(__file__).resolve().parent.parent), folder, *([resume] if resume else [])],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                             stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        result = json.loads(run.stdout.strip().splitlines()[-1])
        return bool(result["ok"]), str(result["text"])
    except Exception as e:
        log.exception("Relaci v oblíbené složce nejde otevřít")
        return False, f"Relaci nejde otevřít: {e}"
