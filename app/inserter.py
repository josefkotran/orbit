"""Puts text into whatever window currently has keyboard focus (and takes it back: editing.py)."""
import ctypes
import json
import logging
import time
from ctypes import wintypes

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtGui import QGuiApplication

log = logging.getLogger(__name__)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004
VK_BACK, VK_SHIFT, VK_CONTROL, VK_RETURN, VK_ESCAPE, VK_V = 0x08, 0x10, 0x11, 0x0D, 0x1B, 0x56
VK_LEFT, VK_INSERT = 0x25, 0x2D
# Ctrl, Shift, Alt (each side) and both Windows keys: held, they'd turn Orbit's Backspace into Ctrl+Backspace (a whole
# word) or its Left into a selection
_MODIFIERS = (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C)
RESTORE_DELAY_MS = 700
COPY_WAIT_MS = 600  # how long a program may take to put its selection on the clipboard (Ctrl+Insert)
KEYS_UP_WAIT_S = 3.0  # how long Orbit waits for the user to let go of Ctrl/Shift before it types
SNAPSHOT_MAX_BYTES = 20 * 2 ** 20  # a clipboard format bigger than this isn't backed up
SNAPSHOT_MAX_S = 0.5  # backing up stops after this long (some programs render every format only when asked)
# Remote desktops and virtual machines fetch the clipboard only when their own Ctrl+V gets there: restoring the old
# content after RESTORE_DELAY_MS could paste that instead (mstsc, RemoteApp, VMware, Citrix)
_REMOTE_CLASSES = {"TscShellContainerClass", "RAIL_WINDOW", "VMUIFrame", "Transparent Windows Client"}
# Keep dictated snippets out of Windows clipboard history (Win+V) and cloud clipboard.
_NO_HISTORY = {
    'application/x-qt-windows-mime;value="ExcludeClipboardContentFromMonitorProcessing"': b"\x00\x00\x00\x00",
    'application/x-qt-windows-mime;value="CanIncludeInClipboardHistory"': b"\x00\x00\x00\x00",
    'application/x-qt-windows-mime;value="CanUploadToCloudClipboard"': b"\x00\x00\x00\x00",
}
# Markers a password manager may put next to a password, often without any data: kept in the backup even when empty
_MARKERS = set(_NO_HISTORY) | {'application/x-qt-windows-mime;value="Clipboard Viewer Ignore"'}
# Terminals: Ctrl+C there stops the program (or clears Claude Code's prompt), and Claude Code collapses long input
_TERMINAL_CLASSES = {"CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass", "mintty", "VirtualConsoleClass", "PuTTY",
                     "org.wezfurlong.wezterm", "Alacritty", "TMobaXterm", "TabbyWindowClass"}
# The taskbar, the desktop, the Start menu: not a place to type into
_SHELL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "NotifyIconOverflowWindow",
                  "TopLevelWindowForOverflowXamlIsland", "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow"}
# Editors that copy the whole line when nothing is selected: what Ctrl+Insert gives there needn't be a selection
# (VS Code says so on the clipboard, see _VSCODE_DATA; JetBrains IDEs don't)
_COPIES_LINE = {"idea64", "pycharm64", "webstorm64", "phpstorm64", "rider64", "clion64", "goland64", "rubymine64",
                "datagrip64", "studio64", "fleet"}
_VSCODE_DATA = 'application/x-qt-windows-mime;value="vscode-editor-data"'


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
_user32.SendInput.restype = wintypes.UINT
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
_user32.WindowFromPoint.argtypes = [wintypes.POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
_advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                          ctypes.POINTER(wintypes.DWORD)]


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> _INPUT:
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = _KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)
    return inp


def _send(events: list[_INPUT]) -> bool:
    """False when Windows didn't take all of them (it doesn't always say so for a window running as administrator)."""
    arr = (_INPUT * len(events))(*events)
    sent = _user32.SendInput(len(events), arr, ctypes.sizeof(_INPUT))
    if sent != len(events):
        log.warning("SendInput odeslal %s/%s událostí (chyba %s) – cílové okno běží asi jako správce",
                    sent, len(events), ctypes.get_last_error())
        return False
    return True


def foreground() -> int:
    """The window in front now (0 = none, e.g. in the middle of switching)."""
    return int(_user32.GetForegroundWindow() or 0)


def own_window(hwnd: int) -> bool:
    """A window of Orbit itself (its menu, its hidden tray window)."""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return bool(hwnd) and pid.value == _kernel32.GetCurrentProcessId()


def same_window(a: int, b: int) -> bool:
    """The same top-level window (a dialog it owns counts as the same)."""
    if not a or not b:
        return a == b
    root = lambda h: int(_user32.GetAncestor(wintypes.HWND(h), 3) or h)  # GA_ROOTOWNER
    return root(a) == root(b)


def _elevated(process: int) -> bool | None:
    """Is the process's token elevated? None when it can't be told (the token can't be opened)."""
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(process, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
        return None
    try:
        value, size = wintypes.DWORD(), wintypes.DWORD()
        if not _advapi32.GetTokenInformation(token, 20, ctypes.byref(value), ctypes.sizeof(value),
                                             ctypes.byref(size)):  # TokenElevation
            return None
        return bool(value.value)
    finally:
        _kernel32.CloseHandle(token)


def runs_as_admin(hwnd: int) -> bool:
    """Does the window belong to a program running as administrator while Orbit doesn't? Windows then silently
    drops the keys Orbit sends there (UIPI)."""
    if not hwnd or _elevated(_kernel32.GetCurrentProcess()):
        return False
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    process = _kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:  # not even that: a system process (also above Orbit)
        return ctypes.get_last_error() == 5
    try:
        elevated = _elevated(process)
        # its token can't be opened: from a normal program that means an elevated one
        return elevated if elevated is not None else ctypes.get_last_error() == 5
    finally:
        _kernel32.CloseHandle(process)


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(wintypes.HWND(hwnd), buf, 64)
    return buf.value


def is_terminal(hwnd: int) -> bool:
    """Windows Terminal, the classic console and the usual other terminals (not one inside an IDE)."""
    return bool(hwnd) and _class_name(hwnd) in _TERMINAL_CLASSES


def is_shell(hwnd: int) -> bool:
    """No window, or the taskbar, the desktop, the Start menu: nowhere to type (what a tray menu leaves in front)."""
    return not hwnd or _class_name(hwnd) in _SHELL_CLASSES


def app_name(hwnd: int) -> str:
    """The program a window belongs to, its file name without .exe ("chrome", "WindowsTerminal"); "" when unknown."""
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    process = _kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        if not _kernel32.QueryFullProcessImageNameW(process, 0, buf, ctypes.byref(size)):
            return ""
        name = buf.value.rsplit("\\", 1)[-1]
        return name[:-4] if name.lower().endswith(".exe") else name
    finally:
        _kernel32.CloseHandle(process)


def own_point(x: int, y: int) -> bool:
    """Is the window under this screen point Orbit's own (its button, a bubble)? Called from the hook thread."""
    hwnd = _user32.WindowFromPoint(wintypes.POINT(x, y))
    return bool(hwnd) and own_window(int(_user32.GetAncestor(hwnd, 2) or hwnd))  # GA_ROOT


def _down(vk: int) -> bool:
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def keys_held(exclude: int = 0) -> bool:
    """Is the user holding Ctrl, Shift, Alt or a Windows key (other than `exclude`, the dictation key itself)?"""
    return any(_down(vk) for vk in _MODIFIERS if vk != exclude)


def edit_held(exclude: int = 0) -> bool:
    """Ctrl or Shift held (other than `exclude`): the dictation is an instruction for editing text, not text."""
    return any(_down(vk) for vk in (0xA0, 0xA1, 0xA2, 0xA3) if vk != exclude)


def delete_back(count: int) -> bool:
    """Backspace `count` times: what Orbit typed last, when the cursor is still right after it."""
    return _send([_key(VK_BACK), _key(VK_BACK, flags=KEYEVENTF_KEYUP)] * count) if count > 0 else True


def select_back(count: int) -> bool:
    """Shift+Left `count` times: selects what Orbit typed last. The arrow as the extended key (the arrow block, not
    the number pad: Shift with a number-pad arrow and Num Lock on would let go of Shift instead)."""
    if count <= 0:
        return True
    left = [_key(VK_LEFT, flags=KEYEVENTF_EXTENDEDKEY), _key(VK_LEFT, flags=KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP)]
    return _send([_key(VK_SHIFT), *left * count, _key(VK_SHIFT, flags=KEYEVENTF_KEYUP)])


def type_text(text: str) -> bool:
    events = []
    for ch in text:
        if ch == "\n":  # Shift+Enter: a line break even in chat apps where plain Enter sends the message
            events += [_key(VK_SHIFT), _key(VK_RETURN), _key(VK_RETURN, flags=KEYEVENTF_KEYUP),
                       _key(VK_SHIFT, flags=KEYEVENTF_KEYUP)]
            continue
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):  # characters outside the BMP are two UTF-16 units
            unit = int.from_bytes(data[i:i + 2], "little")
            events += [_key(scan=unit, flags=KEYEVENTF_UNICODE),
                       _key(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    return _send(events)


class Inserter:
    """Must be used from the Qt main thread (clipboard access)."""

    def __init__(self):
        self._saved: QMimeData | None = None
        self._ours: str | None = None
        self._restore_timer = QTimer(singleShot=True, interval=RESTORE_DELAY_MS)
        self._restore_timer.timeout.connect(self._restore)
        self._polls: list[QTimer] = []  # running copy_selection / when_keys_up checks (kept alive here)

    def _poll(self, check, interval: int) -> None:
        """check() every `interval` ms until it returns True."""
        timer = QTimer(interval=interval)

        def tick():
            if check():
                timer.stop()
                self._polls.remove(timer)
        timer.timeout.connect(tick)
        self._polls.append(timer)
        timer.start()

    def when_keys_up(self, done, exclude: int = 0, timeout: float = KEYS_UP_WAIT_S) -> None:
        """done(True) once the user lets go of Ctrl, Shift, Alt and the Windows keys (Orbit's Backspace with Ctrl
        held would delete whole words), done(False) when they're still held after `timeout` seconds."""
        if not keys_held(exclude):
            done(True)
            return
        until = time.monotonic() + timeout

        def check():
            held = keys_held(exclude)
            if held and time.monotonic() < until:
                return False
            done(not held)
            return True
        self._poll(check, 40)

    def copy_selection(self, done) -> None:
        """What's selected in the window in front: copied with Ctrl+Insert (copy in every Windows program, and unlike
        Ctrl+C never an interrupt), then the clipboard is put back as it was. done(text) on the main thread;
        done(None) when nothing is selected, and in a terminal or an editor that copies a whole line when nothing is
        (they're not even asked)."""
        window = foreground()
        if not window or own_window(window) or is_terminal(window) or app_name(window).lower() in _COPIES_LINE:
            done(None)
            return
        if self._restore_timer.isActive():  # the clipboard still holds Orbit's last pasted text: the user's first
            self._restore_timer.stop()
            self._restore()
        saved = self._snapshot()
        before = _user32.GetClipboardSequenceNumber()
        ext = KEYEVENTF_EXTENDEDKEY
        if not _send([_key(VK_CONTROL), _key(VK_INSERT, flags=ext), _key(VK_INSERT, flags=ext | KEYEVENTF_KEYUP),
                      _key(VK_CONTROL, flags=KEYEVENTF_KEYUP)]):
            done(None)
            return
        until, changed = time.monotonic() + COPY_WAIT_MS / 1000, []

        def check():
            if _user32.GetClipboardSequenceNumber() != before:
                if not changed:  # one more tick: the program may still be adding its formats
                    changed.append(True)
                    return False
                text = self._copied()
                self._put_back(saved)
                done(text)
                return True
            if time.monotonic() < until:
                return False
            done(None)  # nothing selected: the clipboard didn't change
            return True
        self._poll(check, 30)

    @staticmethod
    def _copied() -> str | None:
        md = QGuiApplication.clipboard().mimeData()
        if md is None or not md.hasText():
            return None
        if md.hasFormat(_VSCODE_DATA):  # VS Code copies the whole line when nothing is selected, and says so
            try:
                if json.loads(bytes(md.data(_VSCODE_DATA)).decode("utf-8", "replace")).get("isFromEmptySelection"):
                    return None
            except (ValueError, AttributeError):
                pass
        text = md.text().replace("\r\n", "\n")
        return text if text.strip() else None

    @staticmethod
    def _put_back(saved: QMimeData | None) -> None:
        """The clipboard as it was. It was there before, so Windows' history and cloud clipboard had their chance:
        putting it back mustn't add it again, above all a password a password manager marked as "not in history"."""
        cb = QGuiApplication.clipboard()
        if saved is not None:
            for fmt, data in _NO_HISTORY.items():
                saved.setData(fmt, data)
            cb.setMimeData(saved)
        else:
            cb.clear()

    def insert(self, text: str, mode: str) -> bool:
        """False when Windows didn't take the keys: the text is left on the clipboard then."""
        if mode == "type":
            ok = type_text(text)
        else:
            ok = self._paste(text)
        if not ok:
            self.to_clipboard(text)
        return ok

    def to_clipboard(self, text: str) -> None:
        """The text on the clipboard for the user's own Ctrl+V (what was there before isn't brought back)."""
        self._restore_timer.stop()
        self._saved, self._ours = None, None
        md = QMimeData()
        md.setText(text)
        for fmt, data in _NO_HISTORY.items():
            md.setData(fmt, data)
        QGuiApplication.clipboard().setMimeData(md)

    def press(self, key: str, after_text: str = "", on_skipped=None) -> None:
        """'send' = Enter, 'stop' = Esc. After inserted text Enter waits a moment: terminals paste asynchronously
        and Claude Code treats a key arriving in the same burst as typed text as part of a paste. Only into the
        window that is in front now: if another one (another chat, terminal, session) comes forward meanwhile, the
        key isn't sent and on_skipped() is called."""
        vk = VK_RETURN if key == "send" else VK_ESCAPE
        delay = min(1500, 300 + len(after_text)) if after_text else 0
        window = foreground()

        def send():
            if window and not same_window(window, foreground()):
                log.info("%s neposílám, okno se mezitím změnilo", "Enter" if vk == VK_RETURN else "Esc")
                if on_skipped:
                    on_skipped()
                return
            _send([_key(vk), _key(vk, flags=KEYEVENTF_KEYUP)])

        QTimer.singleShot(delay, send)

    def _paste(self, text: str) -> bool:
        cb = QGuiApplication.clipboard()
        if not self._restore_timer.isActive():  # otherwise the clipboard still holds our previous snippet
            self._saved = self._snapshot()
        md = QMimeData()
        md.setText(text)
        for fmt, data in _NO_HISTORY.items():
            md.setData(fmt, data)
        cb.setMimeData(md)
        if cb.text() != text:
            # another program holds the clipboard open (a clipboard manager, rdpclip): Ctrl+V would paste what was
            # there before, maybe a password. Typed instead.
            log.warning("Schránka nejde nastavit, text píšu po znacích")
            if not self._restore_timer.isActive():
                self._saved = None  # the clipboard didn't change: nothing to bring back
            return type_text(text)
        self._ours = text
        ok = _send([_key(VK_CONTROL), _key(VK_V), _key(VK_V, flags=KEYEVENTF_KEYUP),
                    _key(VK_CONTROL, flags=KEYEVENTF_KEYUP)])
        if _class_name(foreground()) in _REMOTE_CLASSES:
            self._saved = None  # it may fetch it only later: the text stays on the clipboard
            self._restore_timer.stop()
        else:
            self._restore_timer.start()
        return ok

    @staticmethod
    def _snapshot() -> QMimeData | None:
        """A copy of every clipboard format (Excel's cells, Office objects, files cut in Explorer), within limits."""
        src = QGuiApplication.clipboard().mimeData()
        if src is None or not src.formats():
            return None
        copy = QMimeData()
        start = time.monotonic()
        try:
            if src.hasText():
                copy.setText(src.text())
            if src.hasImage():
                copy.setImageData(src.imageData())
            for fmt in src.formats():
                if time.monotonic() - start > SNAPSHOT_MAX_S:
                    log.info("Záloha schránky trvá moc dlouho, zbytek formátů vynechávám")
                    break
                if fmt in ("text/plain", "application/x-qt-image") or copy.hasFormat(fmt):
                    continue
                data = src.data(fmt)
                if 0 < data.size() <= SNAPSHOT_MAX_BYTES or (fmt in _MARKERS and data.size() == 0):
                    copy.setData(fmt, data)
        except Exception:
            log.exception("Nepodařilo se zálohovat schránku")
        return copy

    def _restore(self) -> None:
        saved, self._saved = self._saved, None
        if QGuiApplication.clipboard().text() != self._ours:
            return  # the user copied something new in the meantime – leave it
        self._put_back(saved)
