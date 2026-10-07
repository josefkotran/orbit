"""Claude Code status line: records each session's limits and context for Orbit, then prints the status line.

Claude Code runs it (through Git Bash, or PowerShell where Git isn't installed) after every answer, with the session's
state as JSON on stdin (code.claude.com/docs/en/statusline). It writes <data>/sessions/status/<session_id>.json: the
plan's limits (rate_limits.five_hour / seven_day: used_percentage, resets_at in Unix seconds; only Pro and Max, only
after the session's first answer), the context window and the model. Orbit's limits panel and its session overview
read them.

What it prints is the status line itself: the user's own previous one when Orbit was put in its place (saved in
<data>/statusline-previous.json; run with the same stdin, through the same shell Claude Code would use), otherwise one
short line of its own. <data>: `--data <folder>` in the command, else paths.py's rules.

Standard library only, quick, and silent on any error: it runs in every session after every answer.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

# git and pwsh never from the current folder (the session's project, maybe a cloned repo); Claude Code sets this for
# its status lines too, this keeps it so with any other caller
os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")
CHAIN_TIMEOUT_S = 5  # the user's previous status line gets this long (Claude Code cancels a slow one anyway)
CHAINED = "ORBIT_STATUSLINE_CHAINED"  # set for the previous command: another Orbit's status line there won't chain on
WINDOWS = ("five_hour", "seven_day")


def _data_dir() -> Path:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--data":
        return Path(args[1])
    # an embedded Python (the installed Orbit) doesn't put the script's folder on sys.path by itself
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import paths
    return paths.data_dir()


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
        tmp.unlink(missing_ok=True)


def _record(data: dict, folder: Path) -> None:
    session = str(data.get("session_id") or "")
    if not re.fullmatch(r"[\w-]{1,128}", session):
        return
    target = folder / f"{session}.json"
    try:
        before = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        before = {}
    # Claude Code leaves out a window once it has reset; the last one known stays (Orbit drops it when it's over)
    limits = before.get("rate_limits") if isinstance(before.get("rate_limits"), dict) else {}
    new = data.get("rate_limits")
    if isinstance(new, dict):
        limits.update({k: v for k, v in new.items() if isinstance(v, dict)})
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    record = {"session_id": session, "time": time.time(), "cwd": data.get("cwd") or workspace.get("current_dir"),
              "project_dir": workspace.get("project_dir"), "session_name": data.get("session_name"),
              "model": data.get("model"), "context_window": data.get("context_window")}
    if limits:
        record["rate_limits"] = limits
    folder.mkdir(parents=True, exist_ok=True)
    _write(target, record)


def _git_bash() -> str | None:
    """Claude Code's own choice: CLAUDE_CODE_GIT_BASH_PATH, Git's usual places, then next to git on the PATH."""
    env = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH", "")
    if os.path.basename(env).lower() in ("bash.exe", "sh.exe", "bash", "sh") and os.path.isfile(env):
        return env
    for path in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if os.path.isfile(path):
            return path
    import shutil
    git = shutil.which("git")
    if git:
        path = os.path.normpath(os.path.join(git, "..", "..", "bin", "bash.exe"))
        if os.path.isfile(path):
            return path
    return None


def _powershell() -> str:
    import shutil
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return shutil.which("pwsh") or os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def _previous(data_dir: Path) -> str:
    """The user's own status line command from before Orbit's ("" = none)."""
    try:
        saved = json.loads((data_dir / "statusline-previous.json").read_text(encoding="utf-8"))
        command = saved["statusLine"]["command"]
    except (OSError, ValueError, KeyError, TypeError):
        return ""
    return command.strip() if isinstance(command, str) else ""


def _chain(command: str, raw: bytes) -> bytes:
    """Runs the previous status line command the way Claude Code would and returns what it printed."""
    import subprocess
    bash = _git_bash()
    argv = [bash, "-c", command] if bash else [_powershell(), "-NoProfile", "-NonInteractive", "-Command", command]
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=dict(os.environ, **{CHAINED: "1"}), creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        out, _ = proc.communicate(raw, timeout=CHAIN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()  # its own children may keep the pipe open: not waited for
        return b""
    return out


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _line(data: dict) -> str:
    """Orbit's own short status line: model · kontext 34 % · 5 h 23 % · týden 41 %."""
    parts = []
    model = data.get("model")
    name = model.get("display_name") if isinstance(model, dict) else model
    if isinstance(name, str) and name.strip():
        parts.append(name.strip())
    context = data.get("context_window") if isinstance(data.get("context_window"), dict) else {}
    used = _number(context.get("used_percentage"))
    if used is not None:
        parts.append(f"kontext {used:.0f} %")
    limits = data.get("rate_limits") if isinstance(data.get("rate_limits"), dict) else {}
    for key, label in zip(WINDOWS, ("5 h", "týden")):
        window = limits.get(key) if isinstance(limits.get(key), dict) else {}
        pct = _number(window.get("used_percentage"))
        if pct is not None:
            parts.append(f"{label} {pct:.0f} %")
    return " · ".join(parts)


def main() -> None:
    raw = sys.stdin.buffer.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    data_dir = _data_dir()
    try:  # the status line shows even when the data folder can't be written
        _record(data, data_dir / "sessions" / "status")
    except Exception:
        pass
    out = b""
    command = "" if os.environ.get(CHAINED) else _previous(data_dir)
    if command:
        try:
            out = _chain(command, raw)
        except Exception:
            out = b""
    if not out.strip():
        out = (_line(data) + "\n").encode("utf-8")
    sys.stdout.buffer.write(out)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never disturb Claude Code
