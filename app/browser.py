"""Web pages in the user's Google Chrome for the voice agent: find one they have had open (Chrome's own history, every
profile) and open it, in the profile it was found in.

"Otevři mi objednávku 82" -> find_pages("objednávka 82") finds https://www.m-tex.cz/admin/order-detail.php?id=82
("Objednávka #82 | M-tex Admin") -> open_page() opens it in a new tab and brings Chrome to the front.

Links that do something instead of showing something (log out, delete, cancel, pay…) and links carrying secrets
(tokens, session ids, password resets) are left out of the results, and open_page refuses them.
"""
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unicodedata
import winreg
from ctypes import byref, create_unicode_buffer, windll, WINFUNCTYPE
from ctypes import wintypes
from pathlib import Path

from .sessions import focus_window

USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
MAX_RESULTS = 8
FRONT_WAIT_S = 3.0  # how long Chrome gets to show the new tab before Orbit brings its window up itself
# Links that do something rather than show something: opening one again could delete, log out, cancel, pay, send or
# download. Words anywhere in the URL, and query parameters that name an action (Nette's ?do=…, ?action=…).
ACTION = re.compile(r"csrf|token|logout|log-out|signout|sign-out|odhlas|delete|smaz|remove|odstran|/pay\b|/download/"
                    r"|cancel|storno|zrus|odebr|vymaz|unsubscribe|odhlasit|approve|confirm|potvr|reject|zamit"
                    r"|/send\b|odesl|checkout|objednat|zaplat|platb|payment|export|/print\b|tisk|\.pdf\b"
                    r"|[?&](?:do|action|act|op|cmd|task|set|state|status)=", re.I)
# Query parameters that carry a secret: such a link mustn't go to the model, the panel or the log
_SECRET_PARAMS = {"key", "apikey", "api_key", "token", "access_token", "refresh_token", "id_token", "auth",
                  "authorization",
                  "sig", "signature", "session", "sessionid", "session_id", "sid", "phpsessid", "jsessionid",
                  "password", "passwd", "pwd", "pass", "reset", "otp", "ticket", "nonce", "secret", "client_secret",
                  "hmac", "hash", "login_token", "magic"}


def _secret(url: str) -> bool:
    names = {n.lower() for n in re.findall(r"[?&#;]([^=&#;]+)=", url)}
    return bool(names & _SECRET_PARAMS) or {"code", "state"} <= names  # an OAuth sign-in's return address
_EPOCH = 11644473600  # Chrome stores microseconds since 1601

_user32 = windll.user32
_kernel32 = windll.kernel32
_kernel32.OpenProcess.restype = wintypes.HANDLE
_user32.GetForegroundWindow.restype = wintypes.HWND


def _plain(text: str) -> str:
    """Lower case without diacritics, so "objednávku" finds "Objednávka"."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def _profiles() -> list[Path]:
    return [p.parent for p in USER_DATA.glob("*/History")]


def _history(profile: Path) -> list[tuple[str, str, int, float]]:
    """(url, title, visit count, last visit as Unix time) of every page in the profile's history. Chrome keeps the
    database open, so it's read from a copy."""
    with tempfile.TemporaryDirectory(prefix="orbit-chrome-") as tmp:
        copy = Path(tmp) / "History"
        shutil.copyfile(profile / "History", copy)
        db = sqlite3.connect(copy)
        try:
            rows = db.execute("SELECT url, title, visit_count, last_visit_time FROM urls WHERE hidden = 0").fetchall()
        finally:
            db.close()
    return [(url, title or "", count, t / 1e6 - _EPOCH if t else 0.0) for url, title, count, t in rows]


def find_pages(query: str) -> list[dict]:
    """Pages from the history matching the words of `query`: every number in it must be there as a whole number,
    the words count by how many match (from their stem, Czech words change their endings). Best and newest first.
    Each with the Chrome profile folder it was found in."""
    words = re.findall(r"\w+", _plain(query))
    numbers = [w for w in words if w.isdigit()]
    stems = [w[:max(4, len(w) - 2)] for w in words if not w.isdigit() and len(w) > 1]
    if not words:
        return []
    if not USER_DATA.is_dir():
        raise ValueError("Google Chrome tu není nainstalovaný (nebo nemá historii). Stránky umím otevírat jen "
                         "z historie Chromu.")
    found = []
    for profile in _profiles():
        try:
            history = _history(profile)
        except (OSError, sqlite3.Error):
            continue
        for url, title, count, last in history:
            if not url.startswith(("http://", "https://")) or ACTION.search(url) or _secret(url):
                continue
            text = _plain(f"{url} {title}")
            if not all(re.search(rf"(?<!\d){n}(?!\d)", text) for n in numbers):
                continue
            score = sum(stem in text for stem in stems)
            if score or (numbers and not stems):
                found.append({"url": url, "title": title, "visits": count, "last": last, "score": score,
                              "profile": profile.name})
    found.sort(key=lambda p: (-p["score"], -p["last"]))
    pages, seen = [], set()
    for page in found:
        key = page["url"].split("#")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            pages.append(page)
    return pages[:MAX_RESULTS]


def describe(pages: list[dict]) -> str:
    """The search result for the agent."""
    if not pages:
        return "V historii Chromu jsem nic takového nenašel."
    lines = []
    for p in pages:
        when = time.strftime("%d. %m. %H:%M", time.localtime(p["last"])).lstrip("0").replace(". 0", ". ")
        lines.append(f"- {p['title'] or '(bez názvu)'} | {p['url']} | naposledy {when}, {p['visits']}×")
    return "Stránky z historie Chromu (nejlepší a nejnovější první):\n" + "\n".join(lines)


def chrome_exe() -> str:
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                path = winreg.QueryValue(key, None)
            if Path(path).is_file():
                return path
        except OSError:
            pass
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        path = Path(base or "") / "Google" / "Chrome" / "Application" / "chrome.exe"
        if base and path.is_file():
            return str(path)
    raise RuntimeError("Google Chrome jsem na tomhle počítači nenašel.")


def _process_name(hwnd) -> str:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, byref(pid))
    handle = _kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        name, size = create_unicode_buffer(512), wintypes.DWORD(512)
        _kernel32.QueryFullProcessImageNameW(handle, 0, name, byref(size))
        return Path(name.value).name.lower()
    finally:
        _kernel32.CloseHandle(handle)


def _chrome_windows() -> list[tuple[int, str]]:
    """Chrome's browser windows as (hwnd, title), the topmost first."""
    windows = []

    @WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def check(hwnd, _):
        cls, title = create_unicode_buffer(64), create_unicode_buffer(512)
        _user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == "Chrome_WidgetWin_1" and _user32.IsWindowVisible(hwnd):
            _user32.GetWindowTextW(hwnd, title, 512)
            if title.value and _process_name(hwnd) == "chrome.exe":
                windows.append((hwnd, title.value))
        return True

    _user32.EnumWindows(check, 0)
    return windows


def open_page(url: str, title: str = "", profile: str = "") -> str:
    """Opens `url` in a new tab of the user's Chrome (in `profile`, the folder it was found in) and brings its window
    to the front."""
    url = url.strip()
    if not re.match(r"https?://[^\s/]+", url):
        raise ValueError("Otevřít umím jen webovou adresu začínající http:// nebo https://.")
    if ACTION.search(url) or _secret(url):
        raise ValueError("Tahle adresa vypadá jako odkaz, který něco provede (mazání, odhlášení, platba) nebo nese "
                         "přihlašovací údaje, ne jako stránka k prohlížení. Takovou neotevírám, ať si ji uživatel "
                         "otevře sám.")
    # the profile it was found in (a work profile is logged in where a personal one isn't); only an existing one
    switch = [f"--profile-directory={profile}"] if profile and (USER_DATA / profile / "History").is_file() else []
    # the URL is one argument and starts with http, so Chrome can't take it for a switch; no handles of the agent's
    # pipes go along (a Chrome that wasn't running would keep them open)
    subprocess.Popen([chrome_exe(), *switch, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    # Chrome comes to the front by itself only when Windows lets it; Orbit runs in the background, so usually it just
    # blinks in the taskbar. Then its window (the one with the new tab, recognised by its title) is brought up here.
    hint, deadline = _plain(title)[:40], time.monotonic() + FRONT_WAIT_S
    while True:
        time.sleep(0.15)
        if _process_name(_user32.GetForegroundWindow()) == "chrome.exe":
            break
        windows = _chrome_windows()
        tab = next((hwnd for hwnd, text in windows if hint and hint in _plain(text)), None)
        if tab or (windows and time.monotonic() > deadline):
            focus_window(tab or windows[0][0])
            break
        if time.monotonic() > deadline + 2:
            break
    return f"Otevřeno v Chromu: {title or url}"
