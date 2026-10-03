"""Headless Claude through the local Claude Code CLI, on the user's own subscription (vocabulary learning, artifact
summaries; the voice agent uses claude_exe() and environment() too).

It runs in safe mode, without tools and without saving the session, so it can't touch anything and doesn't clutter
the user's Claude Code history. Finding Claude Code and its environment: claude_setup.py.
"""
import json
import subprocess

from .claude_setup import environment, find_exe
from .config import ROOT

__all__ = ["ClaudeError", "NOT_CONNECTED", "ask", "claude_exe", "environment"]

NOT_CONNECTED = "Claude Code tu není nainstalovaný. Připojíš ho v nastavení Orbitu (Claude › Nainstalovat)."
NOT_LOGGED_IN = "Claude Code není přihlášený. Přihlásíš se v nastavení Orbitu (Claude › Přihlásit se)."


class ClaudeError(Exception):
    pass


def claude_exe() -> str:
    """The real claude.exe (see claude_setup.find_exe), looked up on every call."""
    exe = find_exe()
    if not exe:
        raise ClaudeError(NOT_CONNECTED)
    return exe


def ask(prompt: str, system_prompt: str, schema: dict, model: str = "sonnet") -> dict:
    """Blocking (tens of seconds): Claude's answer to `prompt`, shaped by the JSON `schema`."""
    cmd = [claude_exe(), "-p", "--safe-mode", "--model", model, "--tools", "", "--no-session-persistence",
           "--output-format", "json", "--json-schema", json.dumps(schema), "--system-prompt", system_prompt]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=300, cwd=ROOT, env=environment(), creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise ClaudeError("Claude neodpověděl do 5 minut.")
    except OSError as e:  # Claude Code removed or updating itself right now
        raise ClaudeError(f"Claude Code nejde spustit: {e}")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict):
        raise ClaudeError(f"Claude Code skončil s kódem {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
    if result.get("is_error") or not isinstance(result.get("structured_output"), dict):
        if "not logged in" in str(result.get("result", "")).lower():  # "Not logged in · Please run /login"
            raise ClaudeError(NOT_LOGGED_IN)
        raise ClaudeError(f"Claude Code vrátil chybu: {str(result.get('result'))[:300]}")
    return result["structured_output"]
