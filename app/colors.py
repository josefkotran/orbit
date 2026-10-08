"""Colours of Claude Code sessions by folder: a stripe and the folder's name in Orbit's panel, and a tinted background
of the session's terminal window. The user picks a colour per folder (a right click on a session in the panel, saved
as config folder_colors); every other folder gets a stable one of those left. The names are Claude Code's own /color
names. Standard library only (tint() runs in a small process of its own, see tint_sessions)."""
import ctypes
import os
import subprocess
import sys
import zlib
from ctypes import wintypes
from pathlib import Path

# Claude Code's name: (Czech name, colour in the panel); the terminal gets a dark shade of it (shade())
COLORS = {
    "green": ("zelená", "#3DD68C"),
    "orange": ("oranžová", "#F28C38"),
    "blue": ("modrá", "#5B9DFF"),
    "purple": ("fialová", "#A78BFA"),
    "cyan": ("tyrkysová", "#2DD4BF"),
    "pink": ("růžová", "#F472B6"),
    "yellow": ("žlutá", "#E8C547"),
    "red": ("červená", "#F06A6F"),
}
AUTO = [c for c in COLORS if c != "red"]  # red is Orbit's colour for errors and listening: only when chosen
BACKGROUND = "#0C0C0C"  # Windows Terminal's default background (Campbell)


def key(folder: str) -> str:
    """How a folder is named in folder_colors: its name, lower case ("m-tex")."""
    return (Path(folder).name or folder).lower()


def color_for(folder: str, chosen: dict) -> str:
    """The folder's colour: the user's choice, else a stable one of the colours nobody chose (the same folder name
    always gets the same one, as long as the choices stay the same)."""
    picked = chosen.get(key(folder))
    if picked in COLORS:
        return picked
    left = [c for c in AUTO if c not in chosen.values()] or AUTO
    return left[zlib.crc32(key(folder).encode("utf-8")) % len(left)]


def accent(color: str) -> str:
    return COLORS[color][1]


def shade(color: str, amount: float = 0.15) -> str:
    """The terminal's background for the colour: a dark shade of it, the text stays readable."""
    def channel(hex_: str, i: int) -> int:
        return int(hex_[1 + 2 * i:3 + 2 * i], 16)
    mixed = (round(channel(accent(color), i) * amount + channel(BACKGROUND, i) * (1 - amount)) for i in range(3))
    return "#" + "".join(f"{v:02x}" for v in mixed)


def tint(claude_pid: int, background: str | None) -> bool:
    """Sets the background of the terminal claude_pid runs in (OSC 11; None = the terminal's own again, OSC 111), only
    in a terminal window of its own (Windows Terminal, the classic console), never in an IDE's terminal. It writes into
    that console, so it must run in a process with no console of its own to lose: tint_sessions starts one."""
    k32, user32 = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("user32")
    k32.GetConsoleWindow.restype = wintypes.HWND
    k32.CreateFileW.restype = wintypes.HANDLE
    user32.GetAncestor.restype = wintypes.HWND
    k32.FreeConsole()
    if not k32.AttachConsole(claude_pid):
        return False
    try:
        hwnd = k32.GetConsoleWindow()
        root = user32.GetAncestor(wintypes.HWND(hwnd), 3) if hwnd else None  # GA_ROOTOWNER
        if not (root and user32.IsWindowVisible(wintypes.HWND(root))):
            return False  # an IDE keeps its pseudo console to itself
        out = k32.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)  # read/write, shared, OPEN_EXISTING
        if not out or out == wintypes.HANDLE(-1).value:
            return False
        try:
            text = f"\x1b]11;{background}\x1b\\" if background else "\x1b]111\x1b\\"
            written = wintypes.DWORD()
            return bool(k32.WriteConsoleW(wintypes.HANDLE(out), text, len(text), ctypes.byref(written), None))
        finally:
            k32.CloseHandle(wintypes.HANDLE(out))
    finally:
        k32.FreeConsole()


def tint_sessions(pairs: list[tuple[int, str | None]]) -> None:
    """Tints several sessions' terminals (claude.exe PID, background or None) from a small process of its own: Orbit
    has no console, but attaching to one would make it the console of whatever Orbit starts meanwhile."""
    if not pairs:
        return
    args = [str(v) for pid, background in pairs for v in (pid, background or "-")]
    code = "import sys; sys.path.insert(0, sys.argv[1]); from app.colors import _main; _main(sys.argv[2:])"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pythonw if pythonw.is_file() else sys.executable), "-I", "-c", code,
                      str(Path(__file__).resolve().parent.parent), *args],
                     creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=os.path.dirname(__file__))


def _main(args: list[str]) -> None:
    for pid, background in zip(args[::2], args[1::2]):
        try:
            tint(int(pid), None if background == "-" else background)
        except Exception:
            pass  # a session that ended meanwhile
