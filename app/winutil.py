import ctypes
import logging
import os
import re
import sys
import wave
import winreg
import winsound
from pathlib import Path

import numpy as np

from .config import CACHE_DIR, ROOT

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "Orbit"
_mutex = None


def already_running() -> bool:
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\Orbit-single-instance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def set_app_id() -> None:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Orbit")


# --- autostart -----------------------------------------------------------------------------

def _launch_command() -> str:
    """This copy of Orbit, started the way it runs now: the pythonw.exe next to the running interpreter (the dev
    checkout's .venv, the installed runtime\\) and this copy's Orbit.pyw."""
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        exe = exe.with_name("pythonw.exe")
    return f'"{exe}" "{ROOT / "Orbit.pyw"}"'


def _same(a: str | None, b: str) -> bool:
    return a is not None and os.path.normcase(" ".join(a.split())) == os.path.normcase(" ".join(b.split()))


def _same_file(a: str, b: Path) -> bool:
    try:
        if os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(str(b))):
            return True
        return os.path.samefile(a, b)
    except (OSError, ValueError):
        return False


def starts_this_copy(value: str | None, script: Path = ROOT / "Orbit.pyw") -> bool:
    """A Run value that starts this copy's Orbit.pyw, whatever Python, switches or quotes it uses."""
    words = [next(filter(None, m), "") for m in re.findall(r'"([^"]*)"|(\S+)', value or "")]
    return any(_same_file(w, script) for w in words if w)


def _run_names() -> tuple[str, str]:
    """The value's name: "Orbit", or – when another copy of Orbit (a dev checkout, an installed one) already has
    that one – a second name with this copy's folder."""
    return _RUN_NAME, f"{_RUN_NAME} ({ROOT})"


def autostart_plan(values: dict[str, str | None], enabled: bool, command: str, names: tuple[str, str],
                   script: Path = ROOT / "Orbit.pyw") -> tuple[str | None, list[str]]:
    """What set_autostart changes, given the Run key's values under `names`: (the name to write `command` to or None,
    the names to delete). Only values that start this copy are ever changed or deleted."""
    ours = [name for name in names if starts_this_copy(values.get(name), script)]
    if not enabled:
        return None, ours
    if any(_same(values.get(name), command) for name in ours):
        return None, [name for name in ours if not _same(values.get(name), command)]
    if ours:  # this copy, started another way (another Python): brought up to date
        return ours[0], ours[1:]
    free = [name for name in names if values.get(name) is None]
    # both taken by other copies: the second name carries this copy's folder, so it's this copy's place anyway
    return (free[0] if free else names[1]), []


def _run_value(key, name: str) -> str | None:
    try:
        return str(winreg.QueryValueEx(key, name)[0])
    except FileNotFoundError:
        return None


def autostart_enabled() -> bool:
    """Only this copy's own entry counts, not another copy's."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            return any(starts_this_copy(_run_value(key, name)) for name in _run_names())
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Adds or removes this copy's entry; another copy's entry is never changed. True if it changed anything."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        if not enabled:
            return False
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE)
    with key:
        names = _run_names()
        write, delete = autostart_plan({name: _run_value(key, name) for name in names}, enabled, _launch_command(),
                                       names)
        if write:
            winreg.SetValueEx(key, write, 0, winreg.REG_SZ, _launch_command())
        for name in delete:
            winreg.DeleteValue(key, name)
        return bool(write or delete)


# --- sounds: start/stop beeps, session chimes ------------------------------------------------

_SR = 44100


def _tones(freqs) -> np.ndarray:
    parts = []
    for f in freqs:
        t = np.arange(int(_SR * 0.06)) / _SR
        env = np.minimum(1.0, np.minimum(t / 0.005, (t[-1] - t) / 0.025))
        parts.append(np.sin(2 * np.pi * f * t) * env)
    return np.concatenate(parts) * 0.2


def _chime(notes) -> np.ndarray:
    """Soft mallet notes (a bit like a kalimba) in a small room; notes = ((start s, Hz, gain), ...)."""
    t = np.arange(int(_SR * 0.9)) / _SR
    attack = np.minimum(1.0, t / 0.004)
    dry = np.zeros(int(_SR * max(s for s, _, _ in notes)) + len(t))
    for start, f, gain in notes:
        # overtones die away faster than the fundamental: mellow, not beepy
        tone = sum(a * np.sin(2 * np.pi * f * k * t) * np.exp(-t / tau)
                   for k, a, tau in ((1, 1.0, 0.28), (2, 0.25, 0.12), (3, 0.08, 0.06), (4.2, 0.05, 0.02)))
        i = int(_SR * start)
        dry[i:i + len(t)] += gain * attack * tone
    n = int(_SR * 0.3)  # room: a short, dark, decaying noise tail
    ir = np.random.default_rng(1).standard_normal(n) * np.exp(-np.arange(n) / (_SR * 0.07))
    ir = np.convolve(ir, np.ones(12) / 12, mode="same")
    wet = np.fft.irfft(np.fft.rfft(dry, len(dry) + n) * np.fft.rfft(ir, len(dry) + n))[:len(dry)]
    out = dry + 0.3 * wet * np.sqrt(np.mean(dry ** 2) / np.mean(wet ** 2))
    out[-2205:] *= np.linspace(1, 0, 2205)
    return out / np.abs(out).max() * 0.3


_SOUNDS = {
    "start": lambda: _tones((660, 880)),
    "stop": lambda: _tones((880, 587)),
    "done": lambda: _chime(((0, 783.99, 0.8), (0.13, 1046.5, 1.0))),  # G5 → C6, resolves: finished
    "waiting": lambda: _chime(((0, 1046.5, 0.9), (0.14, 1046.5, 1.0))),  # C6 C6, a knock: your turn
    "error": lambda: _chime(((0, 1046.5, 1.0), (0.13, 783.99, 0.8))),  # C6 → G5, falls: something went wrong
    "info": lambda: _chime(((0, 880.0, 1.0),)),  # A5
}


_failed: set[str] = set()


def sound_path(name: str) -> Path:
    """name: a key of _SOUNDS. The .wav is generated into the cache folder on first use (delete it to regenerate)."""
    path = CACHE_DIR / f"{name}.wav"
    if not path.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        audio = (_SOUNDS[name]() * 32767).astype(np.int16)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_SR)
            w.writeframes(audio.tobytes())
        os.replace(tmp, path)
    return path


def play(name: str) -> None:
    """Never raises: a sound must never cost a dictation."""
    try:
        winsound.PlaySound(str(sound_path(name)), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        if name not in _failed:  # once per sound, it would fail on every beep
            _failed.add(name)
            log.exception("Zvuk %s nejde přehrát", name)


def on_user_desktop() -> bool:
    """False while Windows shows its secure desktop (the lock screen, a UAC prompt, Ctrl+Alt+Del): keys pressed and
    let go there never reach Orbit's hooks."""
    user32 = ctypes.windll.user32
    user32.OpenInputDesktop.restype = ctypes.c_void_p
    user32.GetUserObjectInformationW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
                                                 ctypes.c_void_p]
    user32.CloseDesktop.argtypes = [ctypes.c_void_p]
    desk = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS; the secure desktop: access denied
    if not desk:
        return False
    try:
        name = ctypes.create_unicode_buffer(64)
        if not user32.GetUserObjectInformationW(desk, 2, name, ctypes.sizeof(name), None):  # UOI_NAME
            return True
        return name.value.lower() == "default"
    finally:
        user32.CloseDesktop(desk)


# --- notifications ----------------------------------------------------------------------------

def accepts_notifications() -> bool:
    """False during a full-screen game or presentation (Windows keeps notifications quiet then too)."""
    state = ctypes.c_int()
    if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return True
    return state.value == 5  # QUNS_ACCEPTS_NOTIFICATIONS
