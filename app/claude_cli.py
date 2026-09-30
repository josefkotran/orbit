"""Headless Claude through the local Claude Code CLI, on Pepa's subscription (vocabulary learning, artifact summaries).

It runs in safe mode, without tools and without saving the session, so it can't touch anything and doesn't clutter
Pepa's Claude Code history.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from .config import ROOT


class ClaudeError(Exception):
    pass


def _claude_exe() -> str:
    npm = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    exe = npm if npm.exists() else shutil.which("claude.exe") or shutil.which("claude")
    if not exe:
        raise ClaudeError("Claude Code (claude.exe) nebyl nalezen.")
    return str(exe)


def ask(prompt: str, system_prompt: str, schema: dict, model: str = "sonnet") -> dict:
    """Blocking (tens of seconds): Claude's answer to `prompt`, shaped by the JSON `schema`."""
    cmd = [_claude_exe(), "-p", "--safe-mode", "--model", model, "--tools", "", "--no-session-persistence",
           "--output-format", "json", "--json-schema", json.dumps(schema), "--system-prompt", system_prompt]
    # Without ANTHROPIC_API_KEY the CLI uses the Claude subscription login (Pepa's key has no credit), and without
    # the CLAUDE* variables it doesn't think it runs inside another Claude Code session (when started from one).
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY" and not k.startswith("CLAUDE")}
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=300,
                              cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise ClaudeError("Claude neodpověděl do 5 minut.")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeError(f"Claude Code skončil s kódem {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
    if result.get("is_error") or not isinstance(result.get("structured_output"), dict):
        raise ClaudeError(f"Claude Code vrátil chybu: {str(result.get('result'))[:300]}")
    return result["structured_output"]
