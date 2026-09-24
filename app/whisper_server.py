"""Runs whisper.cpp's HTTP server (Vulkan build) as a child process and talks to it."""
import ctypes
import io
import logging
import re
import socket
import subprocess
import threading
import time
import wave
from ctypes import wintypes

import numpy as np
import requests

from .config import MODELS_DIR, WHISPER_DIR

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
PROMPT = "Dobrý den, tohle je diktovaný text v češtině, se správnou interpunkcí a diakritikou."

# Whisper was trained on subtitles, so on silence/noise it likes to "hear" these.
_HALLUCINATION_RE = re.compile(r"\s*\(?titulky\s+(vytvořil|vytvořila|připravil|:).*$", re.IGNORECASE)
_HALLUCINATION_EXACT = {
    "děkuji za pozornost", "díky za pozornost", "děkuji za sledování", "díky za sledování",
    "titulky", "hudba",
}


# --- kill the server together with this app, even if the app crashes -------------------------

class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE
_kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
_kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

_job = None


def _tie_to_this_process(proc: subprocess.Popen) -> None:
    global _job
    if _job is None:
        _job = _kernel32.CreateJobObjectW(None, None)
        info = _ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _kernel32.SetInformationJobObject(_job, 9, ctypes.byref(info), ctypes.sizeof(info))
    if not _kernel32.AssignProcessToJobObject(_job, int(proc._handle)):
        log.warning("AssignProcessToJobObject selhal: %s", ctypes.get_last_error())


# --------------------------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def to_wav(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.astype(np.int16).tobytes())
    return buf.getvalue()


def build_prompt(vocabulary: str) -> str:
    """Whisper treats the prompt as preceding text, so listing words there nudges it to spell them that way."""
    words = [w.strip() for w in re.split(r"[,;\n]", vocabulary) if w.strip()]
    return f"{PROMPT} Často používám: {', '.join(words)}." if words else PROMPT


def clean_text(text: str) -> str:
    text = " ".join(text.split())
    text = _HALLUCINATION_RE.sub("", text).strip()
    if text.lower().strip(" .!?,…-") in _HALLUCINATION_EXACT or text.strip(" .") == PROMPT.strip(" ."):
        return ""
    return text


def apply_replacements(text: str, replacements: list[list[str]]) -> str:
    """Fixes for phrases Whisper keeps getting wrong ("comgit" -> "Comgate"); whole words, any letter case."""
    for wrong, right in replacements:
        text = re.sub(rf"(?<!\w){re.escape(wrong)}(?!\w)", lambda _: right, text, flags=re.IGNORECASE)
    return text


_COMMAND_RE = re.compile(r"\s*\b(nov(?:ý|á)\s+(?:řádek|řádka|odstavec))\b[\s,.;:!?]*", re.IGNORECASE)


# Terminal commands: only as a sentence of their own, so "… tak mu to odešli" stays text.
_SEND_RE = re.compile(r"(?:^|(?<=[.!?…]))\s*(?:odešli|odeslat)\s*[.!?…]*\s*$", re.IGNORECASE)
_STOP_RE = re.compile(r"^\s*(?:stop|zastav)\s*[.!?…]*\s*$", re.IGNORECASE)


def terminal_command(text: str) -> tuple[str, str]:
    """'… Odešli.' at the end -> (text without it, 'send'); a dictation of just 'Stop.' -> ('', 'stop')."""
    if _STOP_RE.match(text):
        return "", "stop"
    if _SEND_RE.search(text):
        return _SEND_RE.sub("", text).rstrip(), "send"
    return text, ""


def apply_voice_commands(text: str) -> str:
    """'nový řádek' -> line break, 'nový odstavec' -> empty line; the next word gets a capital letter."""
    text = _COMMAND_RE.sub(lambda m: "\n\n" if "odstavec" in m.group(1).lower() else "\n", text)
    return re.sub(r"\n(\w)", lambda m: "\n" + m.group(1).upper(), text)


class WhisperServer:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._port = 0
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self.error: str | None = None

    def start(self, model: str) -> None:
        """Blocking: starts the server and waits until the model is loaded."""
        with self._lock:
            self._stop_locked()
            self.error = None
            model_path = MODELS_DIR / model
            if not model_path.exists():
                self.error = f"Model {model} nebyl nalezen ve složce models."
                raise RuntimeError(self.error)
            self._port = _free_port()
            log_file = open(WHISPER_DIR / "server.log", "wb")
            self._proc = subprocess.Popen(
                [str(WHISPER_DIR / "whisper-server.exe"), "-m", str(model_path),
                 "--host", "127.0.0.1", "--port", str(self._port), "-l", "cs"],
                cwd=WHISPER_DIR, stdout=log_file, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            _tie_to_this_process(self._proc)
            log.info("whisper-server spuštěn (pid %s, port %s, model %s)", self._proc.pid, self._port, model)

        deadline = time.time() + 180
        while time.time() < deadline:
            if self._proc.poll() is not None:
                self.error = "Whisper server se nečekaně ukončil (viz whisper/server.log)."
                raise RuntimeError(self.error)
            try:
                if requests.get(f"http://127.0.0.1:{self._port}/health", timeout=1).status_code == 200:
                    self._ready.set()
                    log.info("whisper-server připraven")
                    return
            except requests.RequestException:
                pass
            time.sleep(0.2)
        self.error = "Whisper server nenaběhl včas."
        raise RuntimeError(self.error)

    def wait_ready(self, timeout: float) -> bool:
        return self._ready.wait(timeout)

    def transcribe(self, audio: np.ndarray, prompt: str = PROMPT) -> str:
        deadline = time.time() + 180
        while not self._ready.wait(0.5):
            if self.error or time.time() > deadline:
                raise RuntimeError(self.error or "Whisper server není připraven.")
        r = requests.post(
            f"http://127.0.0.1:{self._port}/inference",
            files={"file": ("audio.wav", to_wav(audio), "audio/wav")},
            data={
                "language": "cs",
                "response_format": "json",
                "temperature": "0",
                "beam_size": "5",
                # Without timestamps Whisper drops whole sentences around pauses and loses everything
                # past the first 30 s window (it came back as "Titulky vytvořil…"). Costs ~3 % speed.
                "no_timestamps": "false",
                "prompt": prompt,
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("text", "")

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        self._ready.clear()
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait(5)
        self._proc = None
