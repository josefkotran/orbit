"""Puts text into whatever window currently has keyboard focus."""
import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtGui import QGuiApplication

log = logging.getLogger(__name__)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
VK_SHIFT, VK_CONTROL, VK_RETURN, VK_V = 0x10, 0x11, 0x0D, 0x56
RESTORE_DELAY_MS = 700
_RTF = 'application/x-qt-windows-mime;value="Rich Text Format"'
# Keep dictated snippets out of Windows clipboard history (Win+V) and cloud clipboard.
_NO_HISTORY = {
    'application/x-qt-windows-mime;value="ExcludeClipboardContentFromMonitorProcessing"': b"\x00\x00\x00\x00",
    'application/x-qt-windows-mime;value="CanIncludeInClipboardHistory"': b"\x00\x00\x00\x00",
    'application/x-qt-windows-mime;value="CanUploadToCloudClipboard"': b"\x00\x00\x00\x00",
}


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


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> _INPUT:
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = _KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)
    return inp


def _send(events: list[_INPUT]) -> None:
    arr = (_INPUT * len(events))(*events)
    sent = _user32.SendInput(len(events), arr, ctypes.sizeof(_INPUT))
    if sent != len(events):
        log.warning("SendInput odeslal %s/%s událostí (chyba %s) – cílové okno běží asi jako správce",
                    sent, len(events), ctypes.get_last_error())


def type_text(text: str) -> None:
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
    _send(events)


class Inserter:
    """Must be used from the Qt main thread (clipboard access)."""

    def __init__(self):
        self._saved: QMimeData | None = None
        self._ours: str | None = None
        self._restore_timer = QTimer(singleShot=True, interval=RESTORE_DELAY_MS)
        self._restore_timer.timeout.connect(self._restore)

    def insert(self, text: str, mode: str) -> None:
        if mode == "type":
            type_text(text)
        else:
            self._paste(text)

    def _paste(self, text: str) -> None:
        cb = QGuiApplication.clipboard()
        if not self._restore_timer.isActive():  # otherwise the clipboard still holds our previous snippet
            self._saved = self._snapshot()
        md = QMimeData()
        md.setText(text)
        for fmt, data in _NO_HISTORY.items():
            md.setData(fmt, data)
        cb.setMimeData(md)
        self._ours = text
        _send([_key(VK_CONTROL), _key(VK_V), _key(VK_V, flags=KEYEVENTF_KEYUP),
               _key(VK_CONTROL, flags=KEYEVENTF_KEYUP)])
        self._restore_timer.start()

    @staticmethod
    def _snapshot() -> QMimeData | None:
        src = QGuiApplication.clipboard().mimeData()
        if src is None or not src.formats():
            return None
        copy = QMimeData()
        try:
            if src.hasText():
                copy.setText(src.text())
            if src.hasHtml():
                copy.setHtml(src.html())
            if src.hasUrls():
                copy.setUrls(src.urls())
            if src.hasImage():
                copy.setImageData(src.imageData())
            if src.hasFormat(_RTF):
                copy.setData(_RTF, src.data(_RTF))
        except Exception:
            log.exception("Nepodařilo se zálohovat schránku")
        return copy

    def _restore(self) -> None:
        cb = QGuiApplication.clipboard()
        saved, self._saved = self._saved, None
        if cb.text() != self._ours:
            return  # the user copied something new in the meantime – leave it
        if saved is not None:
            cb.setMimeData(saved)
        else:
            cb.clear()
