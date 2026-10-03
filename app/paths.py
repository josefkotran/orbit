"""Where Orbit's files are: the app folder, Orbit's data folder and Claude Code's folder.

Standard library only and no imports from the app package: app/cc_hook.py runs as a plain script (Claude Code starts
it for every event of every session) and imports this as a sibling module.

App folder (ROOT): code, assets\\ (static files only) and whisper\\. Read-only once installed into
%LOCALAPPDATA%\\Programs\\Orbit.

Data folder, the first that applies:
1. ORBIT_DATA_DIR (tests, or a second copy with its own data)
2. the app folder itself when it holds config.json or a file named "portable" (a dev checkout like Pepa's, or a
   portable copy on a USB stick): nothing to migrate
3. %LOCALAPPDATA%\\Orbit
Inside: config.json, orbit.log, recordings\\, models\\ (+ piper\\), sessions\\ (+ artifacts\\), cache\\.

Claude Code's folder: ORBIT_CLAUDE_DIR (tests: a fake one, with its .claude.json inside), else CLAUDE_CONFIG_DIR
(Claude Code's own setting, .claude.json is inside it then too), else ~/.claude with ~/.claude.json next to it.
Everything Orbit reads or writes of Claude Code's goes through claude_dir() / claude_json().

Worked out on every call, so a test can point them elsewhere before it uses a module.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    env = os.environ.get("ORBIT_DATA_DIR")
    if env:
        return Path(os.path.abspath(os.path.expanduser(env)))
    if (ROOT / "config.json").is_file() or (ROOT / "portable").exists():
        return ROOT
    local = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), "AppData", "Local")
    return Path(local) / "Orbit"


def config_path() -> Path:
    return data_dir() / "config.json"


def log_path() -> Path:
    return data_dir() / "orbit.log"


def models_dir() -> Path:
    return data_dir() / "models"


def recordings_dir() -> Path:
    return data_dir() / "recordings"


def sessions_dir() -> Path:
    """The hook's files, one per session and event (see cc_hook.py)."""
    return data_dir() / "sessions"


def artifacts_dir() -> Path:
    return sessions_dir() / "artifacts"


def cache_dir() -> Path:
    """Things Orbit generates and can make again: sounds, icons."""
    return data_dir() / "cache"


def _claude_override() -> str:
    return os.environ.get("ORBIT_CLAUDE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR") or ""


def claude_dir() -> Path:
    """Claude Code's folder: settings.json, sessions\\ (its list of running sessions), projects\\ (transcripts)."""
    override = _claude_override()
    return Path(os.path.expanduser(override)) if override else Path.home() / ".claude"


def claude_json() -> Path:
    """Claude Code's state file (its projects = the folders it was used in)."""
    override = _claude_override()
    return Path(os.path.expanduser(override)) / ".claude.json" if override else Path.home() / ".claude.json"
