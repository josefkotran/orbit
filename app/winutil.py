import ctypes
import wave
import winreg
import winsound

import numpy as np

from .config import ASSETS_DIR, ROOT

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
    return f'"{ROOT / ".venv" / "Scripts" / "pythonw.exe"}" "{ROOT / "Orbit.pyw"}"'


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_NAME)
            return True
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, _RUN_NAME)
            except FileNotFoundError:
                pass


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


def play(name: str) -> None:
    """name: a key of _SOUNDS. The .wav is generated on first use (delete it to regenerate)."""
    path = ASSETS_DIR / f"{name}.wav"
    if not path.exists():
        ASSETS_DIR.mkdir(exist_ok=True)
        audio = (_SOUNDS[name]() * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_SR)
            w.writeframes(audio.tobytes())
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


# --- notifications ----------------------------------------------------------------------------

def accepts_notifications() -> bool:
    """False during a full-screen game or presentation (Windows keeps notifications quiet then too)."""
    state = ctypes.c_int()
    if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return True
    return state.value == 5  # QUNS_ACCEPTS_NOTIFICATIONS
