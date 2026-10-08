"""Runs whisper.cpp's HTTP server as a child process and talks to it.

whisper\\ holds whisper-server.exe with whatever it needs next to it: one self-contained exe (older builds), or the
exe with ggml-*.dll backends it picks at start (GGML_BACKEND_DL: the Vulkan backend is skipped where Vulkan isn't,
the CPU backend matching the processor is chosen). Whether it runs on the graphics card or only on the processor
comes from what it prints when it starts (WhisperServer.backend).

If the server dies while Orbit runs (a graphics driver reset or update, out of memory, a crash), it's started again
after a growing pause and a transcription it was in the middle of is sent once more; on_event tells the UI. A start
that fails on the graphics card is tried again on the processor (-ng).
"""
import contextlib
import ctypes
import functools
import io
import logging
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import wave
from ctypes import wintypes
from pathlib import Path

import numpy as np
import requests

from .config import DATA_DIR, MODELS_DIR, WHISPER_DIR

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
SERVER_LOG = DATA_DIR / "whisper-server.log"  # not in whisper\: the app folder is read-only once installed
PROMPT = "Dobrý den, tohle je diktovaný text v češtině, se správnou interpunkcí a diakritikou."
START_TIMEOUT_S = 300  # loading a model on the processor from a slow disk takes a while
TIMEOUT_MIN_S = 120  # per request; longer audio (and the processor) gets more, see _timeout
RESTART_DELAYS = (1, 5, 20, 60)  # seconds before each try to bring back a server that died
MAX_DEATHS = 4  # it died this often within DEATHS_WINDOW_S: something is wrong for good, stop trying
DEATHS_WINDOW_S = 600
# Readiness is polled this often (the first FAST_POLL_S, then POLL_S): a model loads in ~2 s, a slow poll adds half
# of its period to the time until the first dictation.
FAST_POLL_S, POLL_S, FAST_POLL_FOR_S = 0.05, 0.2, 5

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


class _ProcessorInfo(ctypes.Structure):  # SYSTEM_LOGICAL_PROCESSOR_INFORMATION
    _fields_ = [("ProcessorMask", ctypes.c_size_t), ("Relationship", ctypes.c_int),
                ("Reserved", ctypes.c_ulonglong * 2)]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE
_kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
_kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_kernel32.GetErrorMode.restype = wintypes.UINT
_kernel32.SetErrorMode.argtypes = [wintypes.UINT]
_kernel32.SetErrorMode.restype = wintypes.UINT
_kernel32.GetLogicalProcessorInformation.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
_kernel32.GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
_kernel32.GetShortPathNameW.restype = wintypes.DWORD
_iphlpapi = ctypes.WinDLL("iphlpapi")
_iphlpapi.GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                                          wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
_iphlpapi.GetExtendedTcpTable.restype = wintypes.DWORD

_job = None
_error_mode_lock = threading.Lock()


def _tie_to_this_process(proc: subprocess.Popen) -> None:
    global _job
    if _job is None:
        _job = _kernel32.CreateJobObjectW(None, None)
        info = _ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _kernel32.SetInformationJobObject(_job, 9, ctypes.byref(info), ctypes.sizeof(info))
    if not _kernel32.AssignProcessToJobObject(_job, int(proc._handle)):
        log.warning("AssignProcessToJobObject selhal: %s", ctypes.get_last_error())


@contextlib.contextmanager
def _quiet_child():
    """The child inherits the error mode: a missing DLL (no Vulkan driver) or a crash ends it quietly instead of with
    a Windows dialog that would keep it hanging until someone clicks it."""
    with _error_mode_lock:
        old = _kernel32.GetErrorMode()
        # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX
        _kernel32.SetErrorMode(old | 0x0001 | 0x0002 | 0x8000)
        try:
            yield
        finally:
            _kernel32.SetErrorMode(old)


# --- what the server says about itself ----------------------------------------------------------

_EXIT_TEXTS = {  # NTSTATUS codes a process ends with when Windows stops it
    0xC0000135: "chybí mu knihovna DLL, nejspíš ovladač grafiky s Vulkanem",
    0xC0000139: "jeho knihovny DLL k sobě nepasují",
    0xC000007B: "jeho knihovny DLL jsou poškozené",
    0xC0000142: "nepodařilo se načíst jeho knihovny DLL",
    0xC000001D: "procesor nezná instrukce, pro které je přeložený",
    0xC0000005: "spadl",
    0xC0000409: "spadl",
    0xC0000374: "spadl",
    0xC00000FD: "spadl",
    0xC0000017: "došla paměť",
    0xC000009A: "došla paměť",
}


def exit_text(code: int | None) -> str:
    """Why a process ended, in Czech ("chybí mu knihovna DLL…, kód 0xC0000135", "kód 1")."""
    if code is None:
        return "běží"
    code &= 0xFFFFFFFF
    text = _EXIT_TEXTS.get(code)
    number = f"0x{code:08X}" if code >= 0x80000000 else str(code)
    return f"{text}, kód {number}" if text else f"kód {number}"


_USING_RE = re.compile(r"whisper_backend_init_gpu: using (\D+?)(\d*) backend")


def parse_backend(text: str) -> tuple[str, str]:
    """From the server's start-up output: ("gpu", the card's name), ("cpu", "") or ("", "") when it doesn't say."""
    m = _USING_RE.search(text)
    if m:
        kind, index = m.group(1), m.group(2) or "0"
        device = ""
        if kind.lower() == "vulkan":  # "ggml_vulkan: 0 = AMD Radeon RX 9070 XT (AMD proprietary driver) | uma: 0 …"
            found = re.search(rf"ggml_vulkan: {index} = ([^|\r\n]+)", text)
            device = re.sub(r"\s*\([^)]*\)\s*$", "", found.group(1).strip()) if found else ""
        return "gpu", device or f"{kind}{m.group(2)}"
    if "no GPU found" in text or re.search(r"use gpu\s*=\s*0", text):
        return "cpu", ""
    return "", ""


def _read_log(head: bool) -> str:
    """The start (head) or the end of the server's output."""
    try:
        with open(SERVER_LOG, "rb") as f:
            if not head:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 4096))
            return f.read(65536).decode("utf-8", "replace")
    except OSError:
        return ""


def _log_tail(lines: int = 8) -> str:
    return " | ".join([line.strip() for line in _read_log(head=False).splitlines() if line.strip()][-lines:])


@functools.cache
def _cores() -> int:
    """Physical processor cores. On the processor whisper.cpp is much faster with all of them than with its default
    4 (8 cores: 13 s → 8 s for 10 s of speech, turbo)."""
    cores = 0
    try:
        size = wintypes.DWORD(0)
        _kernel32.GetLogicalProcessorInformation(None, ctypes.byref(size))
        items = (_ProcessorInfo * (size.value // ctypes.sizeof(_ProcessorInfo) or 1))()
        if _kernel32.GetLogicalProcessorInformation(items, ctypes.byref(size)):
            cores = sum(1 for item in items if item.Relationship == 0)  # RelationProcessorCore
    except OSError:
        pass
    return max(1, min(cores or (os.cpu_count() or 8) // 2, 16))


def _gpu_here() -> bool:
    """A graphics card with Vulkan (the same rule the model advice uses); without one the server runs on the
    processor."""
    try:
        from . import downloads
        return bool(downloads.gpus()) and downloads.vulkan()
    except Exception:
        return True


# --------------------------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _TcpRow(ctypes.Structure):  # MIB_TCPROW_OWNER_PID
    _fields_ = [("state", wintypes.DWORD), ("local_addr", wintypes.DWORD), ("local_port", wintypes.DWORD),
                ("remote_addr", wintypes.DWORD), ("remote_port", wintypes.DWORD), ("pid", wintypes.DWORD)]


class _Tcp6Row(ctypes.Structure):  # MIB_TCP6ROW_OWNER_PID
    _fields_ = [("local_addr", ctypes.c_ubyte * 16), ("local_scope", wintypes.DWORD), ("local_port", wintypes.DWORD),
                ("remote_addr", ctypes.c_ubyte * 16), ("remote_scope", wintypes.DWORD),
                ("remote_port", wintypes.DWORD), ("state", wintypes.DWORD), ("pid", wintypes.DWORD)]


def _listeners(port: int) -> set[int] | None:
    """The processes listening on this TCP port (~0.1 ms), None when Windows can't say. The port Orbit picks is
    free only until the server binds it, a few seconds later, and Windows hands ports out in order: another user's
    program on this PC could take it first, answer /health, get the dictated audio and send back text to be typed
    (with "Odešli." an Enter). The audio goes only to a port its own server listens on."""
    pids = set()
    for family, row in ((2, _TcpRow), (23, _Tcp6Row)):  # AF_INET, AF_INET6 (a dual-stack socket takes IPv4 too)
        size, buf = wintypes.DWORD(16384), None
        for _ in range(4):
            buf = ctypes.create_string_buffer(size.value)
            # TCP_TABLE_OWNER_PID_LISTENER = 3
            result = _iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, family, 3, 0)
            if result != 122:  # ERROR_INSUFFICIENT_BUFFER: the table grew, size is the new one
                break
        if result:
            if family == 2:
                return None
            continue  # no IPv6 on this PC
        count = wintypes.DWORD.from_buffer(buf).value
        for item in (row * count).from_buffer(buf, ctypes.sizeof(wintypes.DWORD)):
            if socket.ntohs(item.local_port & 0xFFFF) == port:
                pids.add(item.pid)
    return pids


def _short_path(path: Path) -> str:
    buf = ctypes.create_unicode_buffer(1024)
    return buf.value if _kernel32.GetShortPathNameW(str(path), buf, len(buf)) else ""


def _model_arg(model: Path, cwd: Path) -> str:
    """The model's path for whisper-server's -m. It gets its arguments in the ANSI code page, where a folder with
    Cyrillic letters (or Czech ones on Western Windows: C:\\Users\\Jiří) turns into '?' and the model can't be
    opened. Then the path relative to its folder (the user's folder is the part both share), else the 8.3 one."""
    candidates = [str(model)]
    with contextlib.suppress(ValueError):  # on another drive
        candidates.append(os.path.relpath(model, cwd))
    candidates.append(_short_path(model))
    for candidate in candidates:
        try:
            if candidate:
                candidate.encode("mbcs")  # strict: no best-fit 'r' for 'ř'
                return candidate
        except UnicodeEncodeError:
            continue
    log.warning("Cesta k modelu nejde zapsat v kódové stránce Windows, whisper-server ji nejspíš neotevře")
    return str(model)


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


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")  # Unicode category Cc


def clean_text(text: str) -> str:
    # control characters never belong to dictated text (Esc and the like would act in a terminal)
    text = " ".join(_CONTROL_RE.sub(" ", text).split())
    text = _HALLUCINATION_RE.sub("", text).strip()
    if text.lower().strip(" .!?,…-") in _HALLUCINATION_EXACT or text.strip(" .") == PROMPT.strip(" ."):
        return ""
    return text


def apply_replacements(text: str, replacements: list[list[str]]) -> str:
    """Fixes for phrases Whisper keeps getting wrong ("comgit" -> "Comgate"); whole words, any letter case.
    A malformed entry is skipped (an empty "wrong" would insert `right` between every two characters)."""
    for item in replacements:
        if not (isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(s, str) for s in item)
                and item[0].strip()):
            continue
        wrong, right = item
        text = re.sub(rf"(?<!\w){re.escape(wrong.strip())}(?!\w)", lambda _: right, text, flags=re.IGNORECASE)
    return text


# "Odstavec" alone too, but only as a phrase of its own between punctuation ("Ahoj Andrej, odstavec, přeposílám"):
# "přepiš ten odstavec" stays text.
_COMMAND_RE = re.compile(r"\s*\bnov(?:ý|á)\s+(?:řádek|řádka|odstavec)\b[\s,.;:!?]*"
                         r"|(?:^|(?<=[,.;:!?…]))\s*odstavec\s*(?:[,.;:!?…][\s,.;:!?…]*|$)", re.IGNORECASE)


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
    """'nový řádek' -> line break, 'nový odstavec' (or 'odstavec' alone) -> empty line; the next word gets a capital
    letter."""
    text = _COMMAND_RE.sub(lambda m: "\n\n" if "odstavec" in m.group(0).lower() else "\n", text)
    return re.sub(r"\n(\w)", lambda m: "\n" + m.group(1).upper(), text)


class _EarlyExit(RuntimeError):
    """The server ended before it was ready (the text is for the user)."""

    def __init__(self, text: str, port_taken: bool = False):
        super().__init__(text)
        self.port_taken = port_taken


class WhisperServer:
    """on_event(kind, text) comes from worker threads: "backend" (a start finished: "gpu" or "cpu"), "restarting"
    (it died, a new one is on the way), "restarted", "failed" (it keeps dying: text says so, start() tries again)."""

    def __init__(self, on_event=None):
        self._proc: subprocess.Popen | None = None
        self._port = 0
        self._prefix = ""  # a secret first part of every route: a web page can't use (or kill) the server
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._epoch = 0  # +1 with every start() and stop(): a recovery of an older server gives up
        self._model = ""
        self._no_gpu = False  # the graphics card failed: the processor only (-ng) until the next start()
        self._recovering = False  # a dead server is being brought back: transcribe() waits for it
        self._deaths: list[float] = []
        self.error: str | None = None
        self.backend = ""  # "gpu" / "cpu" / "" (not known)
        self.device = ""  # the graphics card it runs on
        self.on_event = on_event or (lambda kind, text: None)
        # 127.0.0.1 only, never through a proxy from the environment or Windows' settings: the audio stays here
        self._http = requests.Session()
        self._http.trust_env = False

    def start(self, model: str) -> None:
        """Blocking: (re)starts the server with the model and waits until it's loaded. Raises RuntimeError (Czech
        text, also in .error). Returns quietly when another start() or a stop() came meanwhile."""
        with self._lock:
            self._epoch += 1
            epoch = self._epoch
            self._model, self._no_gpu, self._recovering = model, False, False
            self._deaths.clear()
        self._start(epoch)

    def _start(self, epoch: int, fallback: bool = True) -> None:
        """On the graphics card if it works, else on the processor with all its cores. fallback=False (bringing
        back a server that died, all but the last try): the card or nothing, so a driver reset or update that isn't
        over yet doesn't leave Whisper on the processor for the rest of the run."""
        cpu = self._no_gpu or not _gpu_here()
        for attempt in range(4):
            try:
                started = self._launch(epoch, cpu)
            except _EarlyExit as e:
                if epoch != self._epoch:
                    return
                if e.port_taken and attempt < 3:
                    continue  # the free port was taken in the meantime: another one
                if self._no_gpu or not fallback:
                    raise
                log.warning("whisper-server s grafikou nenaběhl, zkouším ho jen na procesoru")
                self._no_gpu = cpu = True
                continue
            if started is None:
                return
            proc, backend, device = started
            if backend == "cpu" and not cpu:  # the card didn't work out after all: the processor with all its cores
                if not fallback:
                    with self._lock:
                        if self._proc is proc:
                            self._stop_locked()
                    raise RuntimeError("whisper-server zatím nevidí grafickou kartu")
                log.info("whisper-server běží jen na procesoru, spouštím ho znovu se všemi jádry")
                cpu = True
                continue
            with self._lock:
                if epoch != self._epoch or self._proc is not proc:
                    return
                self.backend, self.device = backend, device
                self._ready.set()
            threading.Thread(target=self._watch, args=(proc, epoch), daemon=True).start()
            log.info("whisper-server připraven (%s)", f"grafika {device}" if backend == "gpu" else
                     f"jen procesor, {_cores()} vláken" if backend == "cpu" else "zařízení neuvedl")
            self.on_event("backend", backend)
            return
        raise RuntimeError(self.error or "Whisper server se nepodařilo spustit.")

    def _launch(self, epoch: int, cpu: bool) -> tuple[subprocess.Popen, str, str] | None:
        """One server process, waited for until /health answers: (process, backend, device). None when a newer
        start or a stop took over."""
        exe = WHISPER_DIR / "whisper-server.exe"
        with self._lock:
            if epoch != self._epoch:
                return None
            self._stop_locked()
            self.error = None
            model_path = MODELS_DIR / self._model
            if not model_path.is_file():
                self.error = f"Model {self._model} nebyl nalezen ve složce {MODELS_DIR}."
                raise RuntimeError(self.error)
            if not exe.is_file():
                self.error = f"Chybí {exe} (nesmazal ho antivirus?). Přeinstaluj prosím Orbit."
                raise RuntimeError(self.error)
            port, prefix = _free_port(), "/" + secrets.token_urlsafe(16)
            args = [str(exe), "-m", _model_arg(model_path, WHISPER_DIR), "--host", "127.0.0.1", "--port", str(port),
                    "-l", "cs", "--request-path", prefix]
            if cpu:
                args += ["-t", str(_cores())]
            else:
                # On the graphics card one thread: whisper.cpp starts and joins its threads twice per decoded token,
                # which under CPU load (a build, a render) made a dictation ~1.5× slower (25.5 s of speech: 17.9 s
                # with 4 threads, 10.2 s with one); on an idle PC one thread costs ~4 %. Same text either way.
                args += ["-t", "1"]
            if self._no_gpu:
                args.append("-ng")
            SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(SERVER_LOG, "wb") as log_file, _quiet_child():  # the child keeps its own handle
                proc = self._proc = subprocess.Popen(args, cwd=WHISPER_DIR, stdout=log_file, stderr=subprocess.STDOUT,
                                                     creationflags=subprocess.CREATE_NO_WINDOW)
            self._port, self._prefix = port, prefix
            _tie_to_this_process(proc)
            log.info("whisper-server spuštěn (pid %s, port %s, model %s%s%s)", proc.pid, port, self._model,
                     f", {_cores()} vláken" if cpu else "", ", bez grafiky" if self._no_gpu else "")

        started = time.time()
        deadline = started + START_TIMEOUT_S
        while time.time() < deadline:
            dead = proc.poll() is not None
            if self._proc is not proc:  # another start (a new model, a finished download) took over: not an error
                log.info("whisper-server pid %s nahrazen novějším startem", proc.pid)
                return None
            if dead:
                tail = _log_tail()
                why = exit_text(proc.returncode)
                log.warning("whisper-server skončil během startu (%s). Konec jeho výpisu: %s", why, tail)
                self.error = f"Whisper server se ukončil ({why}). Podrobnosti jsou v {SERVER_LOG}."
                raise _EarlyExit(self.error, port_taken="couldn't bind" in tail)
            owners = _listeners(port)
            if owners and owners != {proc.pid}:
                # another program listens on the port picked for this server: not a word goes to it, not even /health
                log.warning("Port %s pro whisper-server obsadil jiný proces (pid %s), zkouším jiný port", port,
                            ", ".join(map(str, sorted(owners - {proc.pid}))))
                with self._lock:
                    if self._proc is proc:
                        self._stop_locked()
                self.error = "Port pro rozpoznávání řeči obsadil jiný program."
                raise _EarlyExit(self.error, port_taken=True)
            if owners is None or owners:  # None: Windows doesn't say who listens, /health decides as before
                try:
                    if self._http.get(f"http://127.0.0.1:{port}{prefix}/health", timeout=1).status_code == 200:
                        return (proc, *parse_backend(_read_log(head=True)))
                except requests.RequestException:
                    pass
            time.sleep(FAST_POLL_S if time.time() - started < FAST_POLL_FOR_S else POLL_S)
        with self._lock:
            if self._proc is proc:
                self._stop_locked()
        self.error = "Whisper server nenaběhl včas."
        raise RuntimeError(self.error)

    def _watch(self, proc: subprocess.Popen, epoch: int) -> None:
        """Waits for the ready server to end. Ending on its own (not stop() or a newer start) = it died: bring it
        back. Whatever goes wrong on the way ends with "failed": a dead thread would leave dictation waiting for a
        server nobody starts."""
        try:
            code = proc.wait()
            with self._lock:
                if self._proc is not proc:
                    return
                self._proc = None
                self._ready.clear()
                self._recovering = True
            log.warning("whisper-server (pid %s) nečekaně skončil (%s). Konec jeho výpisu: %s", proc.pid,
                        exit_text(code), _log_tail())
            self._recover(epoch)
        except Exception:
            log.exception("Obnova whisper-serveru selhala")
            self._give_up(epoch, "Rozpoznávání řeči se nepodařilo znovu spustit. Až podržíš klávesu, zkusím to "
                          "znovu.")

    def _recover(self, epoch: int) -> None:
        now = time.time()
        self._deaths = [t for t in self._deaths if now - t < DEATHS_WINDOW_S] + [now]
        if len(self._deaths) >= MAX_DEATHS:
            self._give_up(epoch, "Rozpoznávání řeči opakovaně padá. Až podržíš klávesu, zkusím ho spustit znovu. "
                          "Když to nepomůže, aktualizuj ovladač grafiky nebo restartuj počítač.")
            return
        self.on_event("restarting", "")
        for i, delay in enumerate(RESTART_DELAYS):
            time.sleep(delay)
            if epoch != self._epoch:
                return
            try:
                # the processor only on the last try: a driver reset or update takes longer than the first ones
                self._start(epoch, fallback=i == len(RESTART_DELAYS) - 1)
            except Exception as e:  # also OSError: no memory to start it (after 0xC0000017), an antivirus
                log.warning("Nový start whisper-serveru selhal: %s", e, exc_info=not isinstance(e, RuntimeError))
                continue
            with self._lock:
                if epoch != self._epoch or not self._ready.is_set():
                    return
                self._recovering = False
            log.info("whisper-server znovu běží")
            self.on_event("restarted", "")
            return
        self._give_up(epoch, f"Rozpoznávání řeči se nepodařilo znovu spustit. {self.error or ''}".strip())

    def _give_up(self, epoch: int, text: str) -> None:
        with self._lock:
            if epoch != self._epoch:
                return
            self._recovering = False
            self.error = text
        log.warning("whisper-server: vzdávám to (%s)", text)
        self.on_event("failed", text)

    def wait_ready(self, timeout: float) -> bool:
        return self._ready.wait(timeout)

    def _wait_ready(self) -> tuple[int, str, subprocess.Popen | None]:
        deadline = time.time() + START_TIMEOUT_S
        while not self._ready.wait(0.5):
            if (self.error and not self._recovering) or time.time() > deadline:
                raise RuntimeError(self.error or "Rozpoznávání řeči není připravené.")
        with self._lock:
            return self._port, self._prefix, self._proc

    def _timeout(self, seconds: float) -> int:
        """Seconds a request may take: far more than it ever does on a graphics card, a lot more on the processor
        (large-v3 there takes longer than the audio itself)."""
        per_s, base = (20, 60) if self.backend == "cpu" else (4, 30)
        return int(max(TIMEOUT_MIN_S, base + per_s * seconds))

    def _lost(self, proc: subprocess.Popen | None) -> bool:
        """After a failed connection: has that server ended (then the watchdog brings a new one)?"""
        for _ in range(20):
            if proc is None or proc.poll() is not None:
                with self._lock:
                    if proc is not None and self._proc is proc:
                        self._ready.clear()  # not ready, even before the watchdog gets to it
                return True
            time.sleep(0.05)
        return False

    def transcribe(self, audio: np.ndarray, prompt: str = PROMPT) -> str:
        """Blocking. If the server dies meanwhile, waits for the new one and sends the audio once more. Raises
        RuntimeError with a Czech text."""
        wav, seconds = to_wav(audio), len(audio) / SAMPLE_RATE
        for attempt in range(2):
            port, prefix, proc = self._wait_ready()
            timeout = self._timeout(seconds)
            owners = _listeners(port)
            if owners and proc is not None and owners != {proc.pid}:  # see _listeners
                log.warning("Na portu whisper-serveru poslouchá jiný proces, zvuk tam neposílám")
                if proc.poll() is None:
                    proc.kill()  # the watchdog starts a new one, on another port
                if attempt == 0 and self._lost(proc):
                    continue
                raise RuntimeError("Rozpoznávání řeči neodpovídá.")
            try:
                r = self._http.post(
                    f"http://127.0.0.1:{port}{prefix}/inference",
                    files={"file": ("audio.wav", wav, "audio/wav")},
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
                    timeout=timeout,
                )
            except requests.ConnectionError as e:
                if attempt == 0 and self._lost(proc):
                    log.warning("whisper-server během přepisu skončil, přepis zopakuji s novým")
                    continue
                raise RuntimeError("Rozpoznávání řeči neodpovídá.") from e
            except requests.Timeout as e:
                # it would go on working on this and hold up every next request: a fresh one instead (the watchdog)
                log.warning("Přepis %.1f s zvuku nestihl %d s, restartuji whisper-server", seconds, timeout)
                if proc is not None and proc.poll() is None:
                    proc.kill()
                raise RuntimeError(f"Přepis nestihl doběhnout do {timeout} s.") from e
            if r.status_code != 200:
                raise RuntimeError(f"Rozpoznávání řeči vrátilo chybu {r.status_code}.")
            try:
                return str(r.json().get("text", ""))
            except (ValueError, AttributeError) as e:
                raise RuntimeError("Rozpoznávání řeči vrátilo odpověď, které nerozumím.") from e
        raise RuntimeError("Rozpoznávání řeči neodpovídá.")

    def stop(self) -> None:
        with self._lock:
            self._epoch += 1
            self._recovering = False
            self._stop_locked()
            self.error = "Whisper server je zastavený."  # a transcribe() still waiting gives up now (start() clears it)

    def _stop_locked(self) -> None:
        self._ready.clear()
        proc, self._proc = self._proc, None  # first: a start still waiting for it sees it's superseded, not dead
        if proc and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:  # stuck in the graphics driver (a reset): the job object ends it later
                log.warning("whisper-server (pid %s) se po zabití neukončil do 5 s", proc.pid)
