"""Global push-to-talk: a low-level keyboard/mouse hook that swallows the chosen key or mouse button."""
import ctypes
import logging
import threading
import time

from pynput import keyboard, mouse
from pynput._util.win32 import SystemHook

log = logging.getLogger(__name__)

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP = 0x207, 0x208, 0x20B, 0x20C
LLKHF_INJECTED, LLMHF_INJECTED = 0x10, 0x01
VK_ESCAPE, VK_LCONTROL = 0x1B, 0xA2
ALTGR_FAKE_CTRL_SCAN = 0x21D  # AltGr on Czech layout also sends a fake Left Ctrl with this scan code

MOUSE_MIDDLE, MOUSE_X1, MOUSE_X2 = 4, 5, 6

_KEY_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "Caps Lock", 0x20: "Mezerník",
    0x21: "Page Up", 0x22: "Page Down", 0x23: "End", 0x24: "Home",
    0x25: "Šipka vlevo", 0x26: "Šipka nahoru", 0x27: "Šipka vpravo", 0x28: "Šipka dolů",
    0x2C: "Print Screen", 0x2D: "Insert", 0x2E: "Delete",
    0x5B: "Levá klávesa Windows", 0x5C: "Pravá klávesa Windows", 0x5D: "Klávesa Menu",
    0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -", 0x6E: "Num ,", 0x6F: "Num /",
    0x90: "Num Lock", 0x91: "Scroll Lock",
    0xA0: "Levý Shift", 0xA1: "Pravý Shift", 0xA2: "Levý Ctrl", 0xA3: "Pravý Ctrl",
    0xA4: "Levý Alt", 0xA5: "Pravý Alt (AltGr)",
    0xAD: "Ztlumit zvuk", 0xAE: "Hlasitost -", 0xAF: "Hlasitost +",
    0xB0: "Další skladba", 0xB1: "Předchozí skladba", 0xB2: "Stop", 0xB3: "Přehrát/Pauza",
}
_KEY_NAMES.update({0x60 + i: f"Num {i}" for i in range(10)})
_KEY_NAMES.update({0x70 + i: f"F{i + 1}" for i in range(24)})
_MOUSE_NAMES = {MOUSE_MIDDLE: "Prostřední tlačítko myši", MOUSE_X1: "Boční tlačítko myši (zpět)",
                MOUSE_X2: "Boční tlačítko myši (vpřed)"}

_user32 = ctypes.WinDLL("user32")


def _suppress():
    """Swallow the current hook event system-wide (what pynput's Listener.suppress_event does)."""
    raise SystemHook.SuppressException()


def binding_name(binding: dict) -> str:
    code = binding.get("code")
    if binding.get("kind") == "mouse":
        return _MOUSE_NAMES.get(code, f"Tlačítko myši {code}")
    if code in _KEY_NAMES:
        return _KEY_NAMES[code]
    if 0x30 <= code <= 0x39 or 0x41 <= code <= 0x5A:
        return chr(code)
    scan = _user32.MapVirtualKeyW(code, 0)
    buf = ctypes.create_unicode_buffer(64)
    if scan and _user32.GetKeyNameTextW(scan << 16, buf, 64):
        return buf.value
    return f"Klávesa 0x{code:02X}"


def in_sentence(key_name: str) -> str:
    """"Pravý Ctrl" → "pravý Ctrl" inside a sentence; one-word names (F9, Pause) stay as they are."""
    return key_name[:1].lower() + key_name[1:] if " " in key_name and key_name[:3] != "Num" else key_name


class PushToTalk:
    """Calls on_press/on_release (from the hook thread) while the bound key/button is held.

    capture(callback) makes the next key or mouse button press become the new binding instead.
    """

    def __init__(self, binding: dict, on_press, on_release):
        self._binding = dict(binding)
        self._on_press = on_press
        self._on_release = on_release
        self._held = False
        self._last_down = 0.0  # when the held key last sent a key-down (Windows repeats them while it's held)
        self._repeats = 0  # repeated key-downs seen in this hold
        self._other_key = False  # another key went down during the hold: the repeating moved to that one
        self._capture_cb = None
        self._swallow_up: tuple[str, int] | None = None  # release of the key that was just captured
        self._lock = threading.Lock()
        self._hook_lock = threading.Lock()
        self._kb = None
        self._ms = None

    # -- public -----------------------------------------------------------------------------

    def start(self) -> None:
        self._kb = keyboard.Listener(win32_event_filter=self._kb_filter)
        self._kb.start()
        self._sync_mouse_hook()

    def stop(self) -> None:
        for listener in (self._kb, self._ms):
            if listener:
                listener.stop()
        self._kb = self._ms = None

    def set_binding(self, binding: dict) -> None:
        with self._lock:
            self._binding = dict(binding)
            self._held = False
        self._sync_mouse_hook()

    def capture(self, callback) -> None:
        """callback(binding | None) is called from the hook thread; None means cancelled (Esc)."""
        with self._lock:
            self._capture_cb = callback
        self._sync_mouse_hook()

    def cancel_capture(self) -> None:
        with self._lock:
            self._capture_cb = None
        self._sync_mouse_hook()

    def released(self) -> bool:
        """Not capturing, and the captured key's release has been swallowed too (safe to stop the hook)."""
        with self._lock:
            return self._capture_cb is None and self._swallow_up is None

    def reset(self) -> None:
        """Forget that the key is held (the recording ended another way): its release then does nothing, the next
        press starts again."""
        with self._lock:
            self._held = False

    def check_stuck(self, after: float = 1.5) -> bool:
        """Was the held key's release missed? The hook never sees it when it happens on Windows' secure desktop (a
        UAC prompt, a locked screen), in a window running as administrator, or when Windows drops a slow hook. A held
        key repeats its key-down every ~30–50 ms, so none for `after` seconds means it's up: on_release is called
        then. Keys only (mouse buttons don't repeat), and only once the repeating was seen in this hold."""
        with self._lock:
            stuck = (self._held and self._binding.get("kind") == "key" and self._repeats > 0 and not self._other_key
                     and time.monotonic() - self._last_down > after)
            if stuck:
                self._held = False
        if stuck:
            log.warning("Puštění klávesy %s se ztratilo, beru ji jako puštěnou", binding_name(self._binding))
            self._on_release()
        return stuck

    # -- hooks ------------------------------------------------------------------------------

    def _sync_mouse_hook(self) -> None:
        # A mouse hook sees every mouse move, so only install it when it is actually needed.
        with self._hook_lock:
            need = self._capture_cb is not None or self._binding.get("kind") == "mouse"
            if need and self._ms is None:
                self._ms = mouse.Listener(win32_event_filter=self._ms_filter)
                self._ms.start()
            elif not need and self._ms is not None:
                self._ms.stop()
                self._ms = None

    def _kb_filter(self, msg, data):
        if data.flags & LLKHF_INJECTED:
            return False
        down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
        vk = data.vkCode
        if vk == VK_LCONTROL and data.scanCode == ALTGR_FAKE_CTRL_SCAN:
            if self._capture_cb or (self._binding.get("kind") == "key" and self._binding.get("code") == 0xA5):
                _suppress()
            return False
        if self._handle(down, "key", vk):
            _suppress()
        return False

    def _ms_filter(self, msg, data):
        if data.flags & LLMHF_INJECTED:
            return False
        if msg in (WM_MBUTTONDOWN, WM_MBUTTONUP):
            code, down = MOUSE_MIDDLE, msg == WM_MBUTTONDOWN
        elif msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            code, down = MOUSE_X1 if (data.mouseData >> 16) == 1 else MOUSE_X2, msg == WM_XBUTTONDOWN
        else:
            return False
        if self._handle(down, "mouse", code):
            _suppress()
        return False

    def _handle(self, down: bool, kind: str, code: int) -> bool:
        """Returns True if the event should be swallowed."""
        with self._lock:
            if self._swallow_up == (kind, code):
                if not down:
                    self._swallow_up = None
                return True

            if self._capture_cb is not None:
                if not down:
                    return False
                cb, self._capture_cb = self._capture_cb, None
                if kind == "key" and code == VK_ESCAPE:
                    new = None
                else:
                    new = {"kind": kind, "code": code}
                    self._binding = dict(new)
                    self._held = False
                self._swallow_up = (kind, code)
                capture_done = (cb, new)
            else:
                capture_done = None
                if self._binding.get("kind") != kind or self._binding.get("code") != code:
                    if down and kind == "key" and self._held:
                        self._other_key = True  # Windows repeats only the newest key: the held one goes quiet
                    return False
                fire = None
                if down and not self._held:
                    self._held, fire = True, self._on_press
                    self._last_down, self._repeats, self._other_key = time.monotonic(), 0, False
                elif down:
                    self._last_down, self._repeats = time.monotonic(), self._repeats + 1
                elif not down and self._held:
                    self._held, fire = False, self._on_release

        if capture_done:
            cb, new = capture_done
            threading.Thread(target=self._sync_mouse_hook, daemon=True).start()
            cb(new)
        elif fire:
            fire()
        return True
