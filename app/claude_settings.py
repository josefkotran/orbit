"""Orbit's entries in Claude Code's settings.json: the hooks (session overview, artifacts read aloud, app/cc_hook.py)
and the status line (limits and the sessions' context, app/cc_status.py).

They're added only with the user's yes (main), and Orbit only ever changes or removes entries of THIS installation,
recognised by the path of its own script: the user's own hooks and status line, and another Orbit copy's (a dev
checkout next to an installed one), stay as they are. A status line the user had before is saved in Orbit's data
folder; cc_status.py keeps showing it, and it comes back when Orbit's is removed.

settings.json is never written when it can't be read as JSON (SettingsError), always atomically, and the first change
keeps a copy of the original (settings.json.orbit-backup). Claude Code's folder: paths.claude_dir().

No Qt: `Orbit.pyw --cleanup` (the uninstaller) uses it too.
"""
import json
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path

from . import paths
from .config import DATA_DIR, ROOT

log = logging.getLogger(__name__)

HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "Notification", "Stop", "StopFailure", "SessionEnd", "PostToolUse")
HOOK_MATCHERS = {"PostToolUse": "Artifact"}  # only published artifacts, not every tool call
HOOK_SCRIPT = ROOT / "app" / "cc_hook.py"
STATUS_SCRIPT = ROOT / "app" / "cc_status.py"
PREVIOUS_STATUSLINE = DATA_DIR / "statusline-previous.json"  # read by cc_status.py
BACKUP_NAME = "settings.json.orbit-backup"
_KEPT_KEYS = ("padding", "refreshInterval", "hideVimModeIndicator")  # the user's status line look stays with Orbit's


class SettingsError(Exception):
    """settings.json can't be read or has a shape Orbit doesn't know: nothing was changed (Czech text)."""


def settings_path() -> Path:
    return paths.claude_dir() / "settings.json"


def _python() -> Path:
    """The python.exe next to the one Orbit runs on (the dev .venv, the installed runtime\\): a console one, Claude
    Code reads what it prints."""
    return Path(sys.executable).with_name("python.exe")


def _data_args() -> list[str]:
    """Hooks and the status line get Claude Code's environment, not Orbit's: a data folder set by ORBIT_DATA_DIR
    goes along in the command."""
    return ["--data", DATA_DIR.as_posix()] if os.environ.get("ORBIT_DATA_DIR") else []


# --- recognising this installation's entries ------------------------------------------------

def same_path(a, b) -> bool:
    """The same file, whatever the slashes, letter case or 8.3 short names."""
    if not isinstance(a, (str, Path)) or not str(a).strip():
        return False
    try:
        if os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b))):
            return True
        return os.path.samefile(str(a), str(b))
    except (OSError, ValueError):
        return False


def _words(command) -> list[str]:
    """The words of a shell command line, quotes removed (enough to find the paths in it)."""
    return [next(filter(None, m), "") for m in re.findall(r'"([^"]*)"|\'([^\']*)\'|(\S+)', str(command or ""))]


def _mentions(entry, script: Path) -> bool:
    """An entry ({type: command, command, args?}) that runs `script`: in its args (exec form) or its command line."""
    if not isinstance(entry, dict) or entry.get("type", "command") != "command":
        return False
    args = entry.get("args")
    words = [a for a in args if isinstance(a, str)] if isinstance(args, list) else []
    return any(same_path(w, script) for w in words + _words(entry.get("command")))


def is_our_hook(hook) -> bool:
    return _mentions(hook, HOOK_SCRIPT)


def is_our_statusline(line) -> bool:
    return _mentions(line, STATUS_SCRIPT)


def _any_orbit_statusline(line) -> bool:
    """Any Orbit copy's status line (for not bringing back one whose Orbit is gone)."""
    return isinstance(line, dict) and any(Path(w).name.lower() == "cc_status.py" for w in _words(line.get("command")))


# --- reading and writing settings.json ------------------------------------------------------

def _read(path: Path) -> tuple[str, dict]:
    try:
        text = path.read_text(encoding="utf-8-sig")  # PowerShell 5.1 writes a BOM
    except FileNotFoundError:
        return "", {}
    except OSError as e:
        raise SettingsError(f"Nastavení Claude Code ({path}) nejde přečíst: {e}")
    if not text.strip():
        return text, {}
    try:
        settings = json.loads(text)
    except ValueError:
        raise SettingsError(f"Nastavení Claude Code ({path}) není platný JSON. Nic jsem v něm neměnil, oprav ho "
                            "prosím (nebo ho Claude Code opraví sám).")
    if not isinstance(settings, dict):
        raise SettingsError(f"Nastavení Claude Code ({path}) nemá tvar, jaký znám. Nic jsem v něm neměnil.")
    return text, settings


def _write_atomic(path: Path, text: str) -> None:
    """A temporary file next to it and a swap: Claude Code watches settings.json and never sees half of it."""
    tmp = path.with_name(f"{path.name}.orbit-{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Claude Code or an antivirus has it open for a moment
                if attempt == 9:
                    raise
                time.sleep(0.05)
    finally:
        tmp.unlink(missing_ok=True)


def _edit(change) -> bool:
    """Applies change(settings) -> bool (changed?) to settings.json. If Claude Code wrote the file in the meantime,
    starts again from its new content."""
    path = settings_path()
    for _ in range(3):
        text, settings = _read(path)
        if not change(settings):
            return False
        backup = path.with_name(BACKUP_NAME)
        if text and not backup.exists():  # the very first change keeps the original
            backup.write_text(text, encoding="utf-8")
        if _read(path)[0] != text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        return True
    raise SettingsError(f"Nastavení Claude Code ({path}) se pořád mění, zkusím to příště.")


# --- hooks ----------------------------------------------------------------------------------------

def _hook() -> dict:
    return {"type": "command", "command": _python().as_posix(), "args": [HOOK_SCRIPT.as_posix(), *_data_args()],
            "async": True, "timeout": 10}


def _without_ours(hooks: dict) -> dict:
    """The hooks without this installation's; a group keeps its other hooks (and its matcher)."""
    result = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            result[event] = groups  # a shape Orbit doesn't know: not its business
            continue
        kept = []
        for group in groups:
            inner = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(inner, list):
                kept.append(group)
                continue
            others = [h for h in inner if not is_our_hook(h)]
            if len(others) == len(inner):
                kept.append(group)
            elif others:
                kept.append(dict(group, hooks=others))
        if kept or not groups:
            result[event] = kept
    return result


def hooks_installed() -> bool:
    """Are this installation's hooks in Claude Code's settings.json?"""
    try:
        hooks = _read(settings_path())[1].get("hooks")
    except SettingsError:
        return False
    return isinstance(hooks, dict) and any(
        isinstance(g, dict) and isinstance(g.get("hooks"), list) and any(is_our_hook(h) for h in g["hooks"])
        for groups in hooks.values() if isinstance(groups, list) for g in groups)


def set_hooks(enabled: bool) -> bool:
    """Adds (or removes) Orbit's hooks, leaving everything else as it is. True if it changed anything. Running sessions
    pick the change up by themselves."""
    def change(settings: dict) -> bool:
        hooks = settings.get("hooks")
        if hooks is None:
            hooks = {}
        if not isinstance(hooks, dict):
            if enabled:
                raise SettingsError('Hooky v nastavení Claude Code ("hooks") mají tvar, jaký neznám. Nic jsem v něm '
                                    "neměnil.")
            return False
        new = _without_ours(hooks)
        if enabled:
            for event in HOOK_EVENTS:
                if isinstance(new.get(event, []), list):
                    group = {"matcher": HOOK_MATCHERS[event]} if event in HOOK_MATCHERS else {}
                    new[event] = [*new.get(event, []), dict(group, hooks=[_hook()])]
        if new == hooks:
            return False
        if new:
            settings["hooks"] = new
        else:
            settings.pop("hooks", None)
        return True

    changed = _edit(change)
    if changed:
        log.info("Hooky Orbitu v %s %s", settings_path(), "přidány" if enabled else "odebrány")
    return changed


# --- status line ------------------------------------------------------------------------------

def _short_path(path: Path) -> str:
    """The 8.3 short form (C:/Users/JANNOV~1/…), "" when the volume has none."""
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)
    try:
        size = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 1024)
    except OSError:
        return ""
    return buf.value.replace("\\", "/") if 0 < size < 1024 else ""


def _git_bash() -> bool:
    """Will Claude Code run status lines through Git Bash (else PowerShell)? Its own rules, see cc_status.py."""
    env = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH", "")
    if os.path.basename(env).lower() in ("bash.exe", "sh.exe", "bash", "sh") and os.path.isfile(env):
        return True
    if any(os.path.isfile(p) for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe")):
        return True
    git = shutil.which("git")
    return bool(git) and os.path.isfile(os.path.normpath(os.path.join(git, "..", "..", "bin", "bash.exe")))


def statusline_command() -> str:
    """The command line for Claude Code's statusLine. It runs in Git Bash or in PowerShell (without Git), so it has to
    mean the same in both: plain words with forward slashes, no quotes. A path with spaces or other characters
    goes in its 8.3 short form; only where there is none it's quoted (the PowerShell way needs `&` in front)."""
    words, quoted = [], False
    for path in (_python(), STATUS_SCRIPT, *([DATA_DIR] if _data_args() else [])):
        text = path.as_posix()
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]+", text):
            short = _short_path(path)
            if re.fullmatch(r"[A-Za-z0-9_.:/~-]+", short):
                text = short
            elif not re.fullmatch(r"[\w.:/-]+", text):  # letters with diacritics need no quotes, spaces do
                text, quoted = f'"{text}"', True
        words.append(text)
    if _data_args():
        words.insert(2, "--data")
    command = " ".join(words)
    return command if not quoted or _git_bash() else f"& {command}"


def _load_previous() -> dict | None:
    try:
        line = json.loads(PREVIOUS_STATUSLINE.read_text(encoding="utf-8"))["statusLine"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return line if isinstance(line, dict) else None


def _save_previous(line) -> None:
    """The user's status line from before Orbit's (cc_status.py keeps showing it); none: nothing saved."""
    if isinstance(line, dict) and isinstance(line.get("command"), str) and line["command"].strip():
        PREVIOUS_STATUSLINE.parent.mkdir(parents=True, exist_ok=True)
        tmp = PREVIOUS_STATUSLINE.with_name(f"{PREVIOUS_STATUSLINE.name}.tmp")
        tmp.write_text(json.dumps({"statusLine": line, "settings": str(settings_path())}, ensure_ascii=False,
                                  indent=2), encoding="utf-8")
        os.replace(tmp, PREVIOUS_STATUSLINE)
    else:
        PREVIOUS_STATUSLINE.unlink(missing_ok=True)


def _restorable(line) -> bool:
    """Not another Orbit's status line whose script is gone (that copy was uninstalled)."""
    if not isinstance(line, dict) or not isinstance(line.get("command"), str):
        return False
    if _any_orbit_statusline(line):
        return any(Path(w).name.lower() == "cc_status.py" and Path(w).is_file() for w in _words(line["command"]))
    return True


def statusline_installed() -> bool:
    try:
        return is_our_statusline(_read(settings_path())[1].get("statusLine"))
    except SettingsError:
        return False


def set_statusline(enabled: bool) -> bool:
    """Puts Orbit's status line in (the user's own one keeps showing through it) or takes it out (theirs comes back).
    Someone else's status line put in after Orbit's is left alone when removing. True if settings.json changed."""
    def change(settings: dict) -> bool:
        current = settings.get("statusLine")
        ours = is_our_statusline(current)
        if enabled:
            if ours:
                wanted = dict(current)
            else:
                _save_previous(current)
                wanted = {k: current[k] for k in _KEPT_KEYS if k in current} if isinstance(current, dict) else {}
            wanted.update(type="command", command=statusline_command())
            if wanted == current:
                return False
            settings["statusLine"] = wanted
            return True
        if not ours:
            return False
        previous = _load_previous()
        if previous is not None and _restorable(previous):
            settings["statusLine"] = previous
        else:
            settings.pop("statusLine", None)
        return True

    changed = _edit(change)
    if not enabled:
        PREVIOUS_STATUSLINE.unlink(missing_ok=True)
    if changed:
        log.info("Stavový řádek Orbitu v %s %s", settings_path(), "nastaven" if enabled else "odebrán")
    return changed


def cleanup() -> list[str]:
    """Everything of this installation out of Claude Code's settings (`Orbit.pyw --cleanup`). What it did, in Czech."""
    done = []
    for step, removed, absent in ((lambda: set_hooks(False), "hooky odebrány", "hooky tam nebyly"),
                                  (lambda: set_statusline(False), "stavový řádek odebrán", "stavový řádek tam nebyl")):
        try:
            done.append(removed if step() else absent)
        except Exception as e:
            log.exception("Úklid nastavení Claude Code selhal")
            done.append(f"chyba: {e}")
    return done
