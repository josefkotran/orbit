"""Headless Claude through the local Claude Code CLI, on the user's own subscription (vocabulary learning, artifact
summaries, editing text by voice; the voice agent uses claude_exe() and environment() too).

It runs in safe mode, without tools and without saving the session, so it can't touch anything and doesn't clutter
the user's Claude Code history. Finding Claude Code and its environment: claude_setup.py.
"""
import json
import subprocess

from .claude_setup import environment, find_exe
from .config import ROOT

__all__ = ["ClaudeError", "NOT_CONNECTED", "Prepared", "ask", "claude_exe", "environment"]

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


def _command(system_prompt: str, schema: dict, model: str, effort: str) -> list[str]:
    return [claude_exe(), "-p", "--safe-mode", "--model", model, *(["--effort", effort] if effort else []),
            "--tools", "", "--no-session-persistence", "--output-format", "json", "--json-schema", json.dumps(schema),
            "--system-prompt", system_prompt]


def _result(stdout: str, stderr: str, code: int | None) -> dict:
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict):
        raise ClaudeError(f"Claude Code skončil s kódem {code}: {(stderr or stdout)[:300]}")
    if result.get("is_error") or not isinstance(result.get("structured_output"), dict):
        if "not logged in" in str(result.get("result", "")).lower():  # "Not logged in · Please run /login"
            raise ClaudeError(NOT_LOGGED_IN)
        raise ClaudeError(f"Claude Code vrátil chybu: {str(result.get('result'))[:300]}")
    return result["structured_output"]


def ask(prompt: str, system_prompt: str, schema: dict, model: str = "sonnet", effort: str = "") -> dict:
    """Blocking (tens of seconds): Claude's answer to `prompt`, shaped by the JSON `schema`."""
    try:
        proc = subprocess.run(_command(system_prompt, schema, model, effort), input=prompt, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=300, cwd=ROOT, env=environment(),
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise ClaudeError("Claude neodpověděl do 5 minut.")
    except OSError as e:  # Claude Code removed or updating itself right now
        raise ClaudeError(f"Claude Code nejde spustit: {e}")
    return _result(proc.stdout, proc.stderr, proc.returncode)


class Prepared:
    """`claude -p` started before its prompt is known (the user is still talking): its own start-up overlaps that,
    answer() then only writes the prompt. One answer per process; cancel() ends one that isn't needed."""

    def __init__(self, system_prompt: str, schema: dict, model: str = "sonnet", effort: str = ""):
        try:
            self._proc = subprocess.Popen(_command(system_prompt, schema, model, effort), stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                          errors="replace", cwd=ROOT, env=environment(),
                                          creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as e:
            raise ClaudeError(f"Claude Code nejde spustit: {e}")

    def answer(self, prompt: str, timeout: float = 120) -> dict:
        """Blocking: Claude's answer to `prompt`."""
        try:
            stdout, stderr = self._proc.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            self.cancel()
            raise ClaudeError(f"Claude neodpověděl do {int(timeout)} s.")
        except (OSError, ValueError) as e:  # ended meanwhile (cancel)
            raise ClaudeError(f"Claude Code skončil dřív, než odpověděl: {e}")
        return _result(stdout, stderr, self._proc.returncode)

    def cancel(self) -> None:
        if self._proc.poll() is None:
            try:
                self._proc.kill()
            except OSError:
                pass
