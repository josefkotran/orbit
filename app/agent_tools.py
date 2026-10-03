"""Orbit's own tools for the voice agent, as a tiny MCP server over stdio (newline-delimited JSON-RPC).

open_session starts a new Claude Code session in a folder, in its own console window. It runs the way the user's own
sessions run: with --dangerously-skip-permissions only when they use it (sessions.bypass_in_use), otherwise plain.
Orbit lets the call through only after the user's "jo" (a PreToolUse hook, see agent.py); this server just does it.
find_pages and open_page find a page in the user's Chrome history and open it (app/browser.py), without asking: they
only show a page. That's why open_page opens only what find_pages found here (the same page with another number is
fine), never an address the model made up or read somewhere.

Its own process (Claude Code starts it): standard library and app modules without Qt only.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import browser, sessions  # noqa: E402
from app.agent import prefix  # noqa: E402
from app.claude_setup import environment, find_exe  # noqa: E402

TOOLS = [{
    "name": "open_session",
    "description": "Otevře novou relaci Claude Code v zadané složce v novém okně terminálu, volitelně rovnou "
                   "s prvním zadáním. Složku ber ze seznamu složek v přehledu (celá cesta).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "folder": {"type": "string", "description": "Celá cesta ke složce, např. C:/Users/jana/projekty/web"},
            "prompt": {"type": "string", "description": "První zadání pro novou relaci (slova uživatele), "
                                                        "nebo prázdné, když ji chce jen otevřít."},
        },
        "required": ["folder"],
    },
}, {
    "name": "find_pages",
    "description": "Najde webové stránky v historii Google Chromu uživatele podle klíčových slov a čísel. Vrátí "
                   "název, adresu a kdy byla naposledy otevřená, nejlepší a nejnovější první.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Klíčová slova a čísla z věty uživatele, např. „objednávka "
                                                       "82“ nebo „admin faktury“. Každé číslo musí být v adrese "
                                                       "nebo názvu stránky."},
        },
        "required": ["query"],
    },
}, {
    "name": "open_page",
    "description": "Otevře webovou stránku v nové kartě Google Chromu uživatele a přenese Chrome do popředí. "
                   "Otevře jen adresu, kterou vrátil find_pages (nebo stejnou stránku s jiným číslem).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Celá adresa z výsledku find_pages"},
            "title": {"type": "string", "description": "Název stránky z find_pages (nebo krátký popis)."},
        },
        "required": ["url"],
    },
}]

_found: dict[str, str] = {}  # pages find_pages returned in this process: URL -> Chrome profile folder


def _shape(url: str) -> str:
    """The page without its numbers: .../order-detail.php?id=82 and ?id=83 are the same page."""
    return re.sub(r"\d+", "#", url.split("#")[0].rstrip("/"))


def find_pages(query: str) -> str:
    pages = browser.find_pages(query)
    for page in pages:
        _found[page["url"]] = page.get("profile", "")
    return browser.describe(pages)


def open_page(url: str, title: str = "") -> str:
    url = url.strip()
    profile = _found.get(url)
    if profile is None:
        profile = next((p for known, p in _found.items() if _shape(known) == _shape(url)), None)
    if profile is None:
        raise ValueError("Otevírám jen stránky, které jsem předtím našel v historii Chromu (find_pages), případně "
                         "stejnou stránku s jiným číslem. Tuhle adresu nejdřív najdi.")
    return browser.open_page(url, title, profile)


def open_session(folder: str, prompt: str = "") -> str:
    if folder.startswith(("\\\\", "//")):
        raise ValueError("Složka na síťovém disku (\\\\server\\…) nejde, relaci otevřu jen v místní složce.")
    path = Path(folder).expanduser()
    if not path.is_dir():
        raise ValueError(f"Složka {folder} neexistuje.")
    exe = find_exe()
    if not exe:
        raise ValueError("Claude Code tu není nainstalovaný.")
    # one line, without " (it would end the quoted argument below) and a trailing \ (it would escape the quote)
    task = " ".join(prompt.split()).replace('"', "”").rstrip("\\")
    if task and not task.startswith(prefix(os.environ.get("ORBIT_USER_NAME", ""))):
        task = f"{prefix(os.environ.get('ORBIT_USER_NAME', ''))} {task}"  # whose words; and never a "-switch"
    if task[:1] in ("-", "/"):
        task = f"Úkol: {task}"
    bypass = sessions.bypass_in_use()
    # In a normal console window like the user's own sessions (cmd.exe → claude.exe; claude.exe alone shows on the
    # taskbar as "some Claude program"). Claude's path and the task reach cmd only as variables expanded after cmd has
    # parsed the line (/v:on, !ORBIT_…!), so nothing in them – & | > ^ % – can run as a command. /s: cmd drops just
    # the outer quotes. The folder is the working directory, not part of the line.
    command = '"!ORBIT_CLAUDE!"' + (" --dangerously-skip-permissions" if bypass else "") + \
        (' "!ORBIT_TASK!"' if task else "")
    # With a task it works in the background: only on the taskbar, never on screen. Started minimized
    # (SW_SHOWMINNOACTIVE, it doesn't take the focus either), Windows keeps it in the classic console window instead
    # of handing it to Windows Terminal – that one would show up first. Not when Claude Code will first ask whether
    # running without permission prompts is all right: that question must be seen.
    background = bool(task) and (not bypass or sessions.bypass_prompt_skipped())
    info = subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=7) if background else None
    subprocess.Popen(f'cmd.exe /s /v:on /k "{command}"', cwd=path,
                     env=dict(environment(), ORBIT_CLAUDE=exe, ORBIT_TASK=task),
                     close_fds=True, startupinfo=info,
                     creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP)
    if background:
        return f"Nová relace se zadáním běží ve složce {path}, minimalizovaná na liště."
    if task:
        return f"Nová relace se otevírá ve složce {path}. Claude Code se nejdřív zeptá na běh bez oprávnění."
    return f"Nová relace se otevírá ve složce {path} v novém okně terminálu."


def _result(request_id, result=None, error=None) -> dict:
    reply = {"jsonrpc": "2.0", "id": request_id}
    if error:
        reply["error"] = {"code": -32601, "message": error}
    else:
        reply["result"] = result
    return reply


def handle(request: dict) -> dict | None:
    method, params, request_id = request.get("method"), request.get("params") or {}, request.get("id")
    if request_id is None:  # a notification (e.g. notifications/initialized)
        return None
    if method == "initialize":
        return _result(request_id, {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                                    "capabilities": {"tools": {}},
                                    "serverInfo": {"name": "orbit", "version": "1"}})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        args = params.get("arguments") or {}
        name = params.get("name")
        try:
            if name == "open_session":
                text = open_session(str(args.get("folder", "")), str(args.get("prompt", "")))
            elif name == "find_pages":
                text = find_pages(str(args.get("query", "")))
            elif name == "open_page":
                text = open_page(str(args.get("url", "")), str(args.get("title", "")))
            else:
                raise ValueError(f"Neznámý nástroj {name}.")
            failed = False
        except Exception as e:
            text, failed = str(e), True
        return _result(request_id, {"content": [{"type": "text", "text": text}], "isError": failed})
    if method == "ping":
        return _result(request_id, {})
    return _result(request_id, error=f"Metoda {method} není podporovaná.")


def main() -> None:
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        if not isinstance(request, dict):
            continue
        reply = handle(request)
        if reply is not None:
            sys.stdout.buffer.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
