"""Orbit's own tools for the voice agent, as a tiny MCP server over stdio (newline-delimited JSON-RPC).

open_session starts a new Claude Code session in a folder, in its own console window. It runs the way the user's own
sessions run: with --dangerously-skip-permissions only when they use it (sessions.bypass_in_use), otherwise plain.
Orbit lets the call through only after the user's "jo" (a PreToolUse hook, see agent.py); this server does it, but
again only in one of the user's folders and with a task that was read out whole (no hidden part, see _task).
find_pages and open_page find a page in the user's Chrome history and open it (app/browser.py), without asking: they
only show a page. That's why open_page opens only what find_pages found here (the same page with another number in
its path or query is fine), never an address the model made up or read somewhere.

Its own process (Claude Code starts it): standard library and app modules without Qt only.
"""
import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlsplit

# a program by its bare name (claude, cmd) never from the current folder, whatever folder this was started in
os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import browser, sessions  # noqa: E402
from app.agent import is_screenshot, known_folder, prefix  # noqa: E402
from app.claude_setup import environment, find_exe  # noqa: E402

CMD = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "cmd.exe")

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
            "screenshot": {"type": "boolean", "description": "true, když uživatel chce k zadání přiložit svůj "
                                                             "poslední snímek obrazovky (screenshot). Orbit ho najde "
                                                             "sám."},
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
_console_lock = threading.Lock()


def _shape(url: str) -> str:
    """The page without the numbers in its path and query: .../order-detail.php?id=82 and ?id=83 are the same page.
    The server and port stay as they are: 10.0.0.5 or localhost:3001 is another computer or program."""
    parts = urlsplit(url)
    rest = parts.path.rstrip("/") + (f"?{parts.query}" if parts.query else "")
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{re.sub(r'\d+', '#', rest)}"


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


def _start(source: str = "") -> str:
    """How the first message starts: "<name> (hlasem přes Orbit):", or "<name> (<source>):" for a task from Orbit's
    notebook (tasks.SOURCE; only Orbit itself passes a source, the MCP tool never does)."""
    name = os.environ.get("ORBIT_USER_NAME", "")
    return f"{name or 'Uživatel'} ({source}):" if source else prefix(name)


def _task(prompt: str, source: str = "") -> str:
    """The new session's first message on one line, "<name> (hlasem přes Orbit): <the user's words>" ("" = none).
    Before the user's "jo" Orbit reads the words out without a "… (hlasem přes Orbit):" start and a Markdown link
    as its text only (main._ask_confirm), so what could hide there is refused: what was heard must be all that runs."""
    name = os.environ.get("ORBIT_USER_NAME", "")
    task = " ".join(prompt.split())
    for start in (prefix(name), prefix()):
        if task.startswith(start):
            task = task[len(start):].lstrip()
            break
    if "(hlasem přes orbit)" in task.lower():
        raise ValueError("Zadání má „(hlasem přes Orbit)“ uprostřed a text před tím uživatel neslyšel, relaci jsem "
                         "neotevřel. Napiš zadání jen slovy uživatele, bez toho označení (doplní se samo).")
    if re.search(r"\[[^\]]*\]\([^)]*\)", task):
        raise ValueError("Zadání obsahuje odkaz v Markdownu a jeho adresu uživatel neslyšel, relaci jsem neotevřel. "
                         "Napiš zadání prostým textem.")
    if any(unicodedata.category(c).startswith("C") for c in task):  # control, zero-width, bidi, tag characters…
        raise ValueError("Zadání obsahuje neviditelné znaky, které se nepřečtou nahlas, relaci jsem neotevřel. "
                         "Napiš ho znovu prostým textem.")
    # without " (it would end the quoted argument below) and a trailing \ (it would escape the quote)
    task = task.replace('"', "”").rstrip("\\")
    return f"{_start(source)} {task}" if task else ""  # whose words; and never a "-switch"


def _console_window(pid: int) -> int:
    """The visible window showing pid's console (Windows Terminal owns the hidden pseudo-console window, the classic
    console is that window itself), 0 while there is none yet."""
    k32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GetConsoleWindow.restype = wintypes.HWND
    user32.GetAncestor.restype = wintypes.HWND
    with _console_lock:  # a process can be attached to one console only: two sessions opened at once take turns
        k32.FreeConsole()
        if not k32.AttachConsole(pid):
            return 0
        hwnd = k32.GetConsoleWindow()
        k32.FreeConsole()
    root = user32.GetAncestor(wintypes.HWND(hwnd), 3) if hwnd else None  # GA_ROOTOWNER
    return int(root) if root and user32.IsWindowVisible(wintypes.HWND(root)) else 0


def _minimize(pid: int, focused: int | None) -> None:
    """Minimizes the new session's window as soon as it shows (Windows Terminal: ~0.1 s after the start) and keeps it
    so, until it has stayed down and out of focus for 1.5 s: Windows Terminal shows its new window once more within
    ~0.2 s and then activates it again, minimized, so the user's typing would go to the hidden session. The focus goes
    back to the window the user was in (focused): SW_MINIMIZE activates the window below, focus_window that one."""
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    start, hwnd, calm_since = time.monotonic(), 0, None
    while time.monotonic() - start < 10:
        hwnd = hwnd or _console_window(pid)
        if hwnd:
            handle = wintypes.HWND(hwnd)
            if not user32.IsWindow(handle):
                return
            in_front = user32.GetForegroundWindow() == hwnd
            if not user32.IsIconic(handle):
                calm_since = None
                user32.ShowWindow(handle, 6 if in_front else 7)  # SW_MINIMIZE / SW_SHOWMINNOACTIVE
            elif in_front:
                calm_since = None
                if not (focused and sessions.focus_window(focused)):
                    focused = None  # gone (or the desktop had the focus): no use trying again
            elif calm_since is None:
                calm_since = time.monotonic()
            elif time.monotonic() - calm_since > 1.5:
                return
        time.sleep(0.01)


def _user_environment() -> dict:
    """The environment a program started from the desktop gets (Windows' and the user's variables from the registry),
    for a new session instead of this process's own: the agent's Claude Code gives the tools it runs NO_COLOR=1,
    CLAUDE_PROJECT_DIR (its own empty folder), GCM_INTERACTIVE=never, GIT_TERMINAL_PROMPT=0, GIT_EDITOR=true…, and a
    session that inherited them had no colours and git couldn't ask for a login. Without ANTHROPIC_API_KEY, like every
    Claude Code Orbit starts (claude_setup.environment, also used when Windows won't build the block)."""
    k32, advapi, userenv = ctypes.WinDLL("kernel32"), ctypes.WinDLL("advapi32"), ctypes.WinDLL("userenv")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    token, block, env = wintypes.HANDLE(), ctypes.c_void_p(), {}
    if not advapi.OpenProcessToken(wintypes.HANDLE(k32.GetCurrentProcess()), 0x000A, ctypes.byref(token)):
        return environment()  # (TOKEN_QUERY | TOKEN_DUPLICATE)
    try:
        if not userenv.CreateEnvironmentBlock(ctypes.byref(block), token, False):
            return environment()
        try:
            pos = block.value
            while entry := ctypes.wstring_at(pos):  # "NAME=value\0…\0\0"
                name, _, value = entry.partition("=")
                if name and name.upper() != "ANTHROPIC_API_KEY":
                    env[name] = value
                pos += (len(entry) + 1) * ctypes.sizeof(ctypes.c_wchar)
        finally:
            userenv.DestroyEnvironmentBlock(block)
    finally:
        k32.CloseHandle(token)
    if os.environ.get("ORBIT_CLAUDE_DIR"):  # tests: the same fake Claude Code folder as Orbit
        env["CLAUDE_CONFIG_DIR"] = os.environ["ORBIT_CLAUDE_DIR"]
    return env or environment()


def open_session(folder: str, prompt: str = "", screenshot: str = "", source: str = "") -> str:
    """screenshot: the path of the screenshot Orbit named in its question (the hook puts it there; the agent's own
    true or anything else isn't a path in the Screenshots folder and is refused). The session gets the path in its
    first message and looks at the picture itself: Alt+V would need its window in front and keys sent into it.
    source: where the task comes from when it isn't the voice agent (tasks.start_session), see _start."""
    # only one of the user's folders (agent.known_folder), the same check Orbit made before asking
    known = known_folder(folder)
    if not known:
        raise ValueError(f"Složka {folder} není v seznamu složek pro nové relace. Vezmi celou cestu ze seznamu.")
    if known.startswith(("\\\\", "//")):
        raise ValueError("Složka na síťovém disku (\\\\server\\…) nejde, relaci otevřu jen v místní složce.")
    path = Path(known)
    if not path.is_dir():
        raise ValueError(f"Složka {folder} neexistuje.")
    if screenshot and not is_screenshot(screenshot):
        raise ValueError("Snímek obrazovky jsem nenašel, relaci jsem neotevřel. Zkus to znovu.")
    task = _task(prompt, source)
    if screenshot:
        task = f"{task or _start(source)} Přiložený snímek obrazovky: {screenshot}"
    exe = find_exe()
    if not exe:
        raise ValueError("Claude Code tu není nainstalovaný.")
    if task[:1] in ("-", "/"):
        task = f"Úkol: {task}"
    bypass = sessions.bypass_in_use()
    # In a normal console window like the user's own sessions (cmd.exe → claude.exe; claude.exe alone shows on the
    # taskbar as "some Claude program"). Claude's path and the task reach cmd only as variables expanded after cmd has
    # parsed the line (/v:on, !ORBIT_…!), so nothing in them – & | > ^ % – can run as a command. /s: cmd drops just
    # the outer quotes. The folder is the working directory, not part of the line.
    command = '"!ORBIT_CLAUDE!"' + (" --dangerously-skip-permissions" if bypass else "") + \
        (' "!ORBIT_TASK!"' if task else "")
    # With a task it works in the background: on the taskbar, minimized as soon as its window shows (_minimize). Not
    # when Claude Code will first ask whether running without permission prompts is all right: that must be seen.
    background = bool(task) and (not bypass or sessions.bypass_prompt_skipped())
    # Started normally, so it gets the same window as the user's own sessions (Windows Terminal, when that's the
    # default terminal); a console started minimized Windows never hands over and keeps it in the classic window.
    focused = ctypes.windll.user32.GetForegroundWindow() if background else None
    proc = subprocess.Popen(f'cmd.exe /s /v:on /k "{command}"', executable=CMD, cwd=path,
                            env=dict(_user_environment(), ORBIT_CLAUDE=exe, ORBIT_TASK=task), close_fds=True,
                            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP)
    shot = " Snímek obrazovky má v zadání." if screenshot else ""
    if background:
        threading.Thread(target=_minimize, args=(proc.pid, focused), daemon=True).start()
        return f"Nová relace se zadáním běží ve složce {path}, minimalizovaná na liště.{shot}"
    if task:
        return f"Nová relace se otevírá ve složce {path}. Claude Code se nejdřív zeptá na běh bez oprávnění.{shot}"
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
                shot = args.get("screenshot")  # a path from Orbit's hook; the agent's own true counts as none
                text = open_session(str(args.get("folder", "")), str(args.get("prompt", "")),
                                    shot if isinstance(shot, str) else "")
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
