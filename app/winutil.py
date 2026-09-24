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


# --- start/stop beeps ----------------------------------------------------------------------

def _write_tones(path, freqs) -> None:
    sr = 44100
    parts = []
    for f in freqs:
        t = np.arange(int(sr * 0.06)) / sr
        env = np.minimum(1.0, np.minimum(t / 0.005, (t[-1] - t) / 0.025))
        parts.append(np.sin(2 * np.pi * f * t) * env)
    audio = (np.concatenate(parts) * 0.2 * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(audio.tobytes())


def play(name: str) -> None:
    """name: 'start' or 'stop'."""
    path = ASSETS_DIR / f"{name}.wav"
    if not path.exists():
        ASSETS_DIR.mkdir(exist_ok=True)
        _write_tones(path, (660, 880) if name == "start" else (880, 587))
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
