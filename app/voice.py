"""Local Czech voices (Piper) for reading aloud, instead of Windows' Jakub.

Everything runs on this PC: an ONNX model on the CPU, about 0.1 s per sentence once loaded (loading takes ~1.7 s,
done once, right when the voice is chosen). Piper hands over the audio sentence by sentence, so the first one plays
while the rest are still being made. Models: <data>/models/piper/<name>.onnx + .onnx.json from
huggingface.co/rhasspy/piper-voices, downloaded on demand (downloads.py). Piper (piper-tts) is GPL-3.0 and optional:
without it only Jakub is offered.

Piper runs in a process of its own (PiperSpeaker → _worker): loading a voice holds Python's GIL for 1.6–6 s
(onnxruntime), which in Orbit's process froze the UI and every keyboard and mouse hook of the system; a crash in
espeak or onnxruntime there would end Orbit, and its sound card stream is out of the way of Orbit's PortAudio.
"""
import ctypes
import functools
import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import sounddevice as sd

from PySide6.QtCore import QObject, Signal

from .config import MODELS_DIR
from .paths import ROOT

log = logging.getLogger(__name__)

PIPER_DIR = MODELS_DIR / "piper"
JAKUB = "jakub"
VOICES = {  # config value: label in settings
    JAKUB: "Jakub (Windows)",
    "cs_CZ-jirka-medium": "Jirka (Piper, mužský)",
    "cs_CZ-kasandra-medium": "Kasandra (Piper, ženský)",
}
CREDITS = {"cs_CZ-kasandra-medium": "Hlas Kasandra: Ondřej Šimek, licence CC BY 4.0"}  # shown where it's offered
FALLBACK = "cs_CZ-jirka-medium"  # offered for download when Windows has no Czech voice
PREVIEW = "Ahoj, tímhle hlasem ti budu číst hotové odpovědi relací, souhrny artefaktů a odpovědi agenta."
MAX_DEATHS = 3  # the Piper process ended on its own this often: no more tries in this run
# The Piper process: Orbit's folder, model, espeak data come as arguments (sys.argv[1:])
_WORKER_CODE = "import sys; sys.path.insert(0, sys.argv[1]); from app.voice import _worker; _worker(*sys.argv[2:])"


def _ascii_path(path: Path) -> str | None:
    """The path in ASCII letters only: as it is, else its 8.3 form; None when there is none (8.3 names switched off
    on that disk)."""
    if str(path).isascii():
        return str(path)
    buf = ctypes.create_unicode_buffer(1024)
    short = buf.value if ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf)) else ""
    return short if short and short.isascii() else None


@functools.cache
def _espeak_data() -> str | None:
    """Piper's espeak-ng data folder as espeak can open it. Its C code can't open a path with any letter outside
    ASCII (C:\\Users\\Tomáš\\…): it prints an error and ends the whole process (exit 1, no exception). None when
    there is no such path or no Piper at all."""
    spec = importlib.util.find_spec("piper")  # without importing it (onnxruntime)
    if spec is None or not spec.submodule_search_locations:
        return None
    return _ascii_path(Path(next(iter(spec.submodule_search_locations))) / "espeak-ng-data")


@functools.cache
def piper_installed() -> bool:
    """Piper is part of this Orbit and can work here (see _espeak_data)."""
    if importlib.util.find_spec("piper") is None:
        return False
    if _espeak_data() is None:
        log.warning("Piper: cesta k jeho datům má diakritiku a nemá krátké jméno 8.3, hlasy Piperu nenabízím")
        return False
    return True


@functools.cache
def windows_czech() -> bool:
    """Does Windows have a Czech voice (Microsoft Jakub)? Not every Windows does: an English one needs the Czech
    speech pack. Needs the QApplication; asked once."""
    from PySide6.QtTextToSpeech import QTextToSpeech
    return any(v.locale().name() == "cs_CZ" for v in QTextToSpeech("winrt").availableVoices())


def downloaded(key: str) -> bool:
    return (PIPER_DIR / f"{key}.onnx").is_file() and (PIPER_DIR / f"{key}.onnx.json").is_file()


def usable() -> list[str]:
    """The voices that can read here: Jakub if Windows has him, Piper voices if Piper and the model are there."""
    found = [JAKUB] if windows_czech() else []
    if piper_installed():
        found += [key for key in VOICES if key != JAKUB and downloaded(key)]
    return found


def choices() -> list[str]:
    """The voices the settings offer: Jakub always (he may be missing in Windows), Piper voices when Piper is part
    of this Orbit, downloaded or not (the settings offer the download)."""
    return [key for key in VOICES if key == JAKUB or piper_installed()]


def effective(choice: str) -> str | None:
    """The voice to read with: the chosen one if it works here, else another one that does, else None (then
    nothing is read: Czech in an English voice is unintelligible)."""
    if choice != JAKUB and choice in VOICES and piper_installed() and downloaded(choice):
        return choice  # without asking Windows about Jakub: that loads its speech engine and media stack (~25 MB)
    working = usable()
    return choice if choice in working else next(iter(working), None)


def missing_text() -> str:
    """What to tell the user when there is no Czech voice to read with."""
    if piper_installed():
        return ("Ve Windows chybí český hlas pro předčítání. Klikni a stáhnu hlas Jirka (63 MB, běží jen u tebe). "
                "Nebo si hlas vyber v nastavení Orbitu.")
    return ("Chybí český hlas pro předčítání. Přidej ho ve Windows: Nastavení › Čas a jazyk › Řeč › Přidat hlasy › "
            "Čeština.")


_current: "PiperSpeaker | None" = None  # one Piper process at a time


class PiperSpeaker(QObject):
    """Says one text at a time, in the Piper process (_worker). `finished` comes once per say(), when it's done
    or stopped."""

    finished = Signal()

    def __init__(self, model: str):
        global _current
        super().__init__()
        self.model = model
        self.speaking = False
        self._lock = threading.Lock()  # the process, its stdin and the count of texts not done yet
        self._proc: subprocess.Popen | None = None
        self._pending = 0
        self._deaths = 0
        if _current is not None:
            _current.close()
        _current = self
        with self._lock:
            self._spawn()  # loads the voice right away, so the first text doesn't wait for it

    def _spawn(self) -> None:
        """Starts the Piper process (under _lock). Python without the user's environment variables (-I), with
        Orbit's folder on its path: the same pythonw that runs Orbit (the venv's or runtime\\)."""
        from .whisper_server import _tie_to_this_process
        args = [sys.executable, "-I", "-c", _WORKER_CODE, str(ROOT), str(PIPER_DIR / f"{self.model}.onnx"),
                _espeak_data() or ""]
        env = dict(os.environ)
        env.setdefault("OPENBLAS_NUM_THREADS", "1")  # numpy: no idle thread per processor (see Orbit.pyw)
        try:
            proc = subprocess.Popen(args, cwd=str(ROOT), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            log.exception("Piper: proces nejde spustit")
            self._deaths = MAX_DEATHS
            return
        _tie_to_this_process(proc)  # it ends with Orbit, even when Orbit crashes (and on stdin's end anyway)
        self._proc = proc
        threading.Thread(target=self._read, args=(proc,), daemon=True).start()

    def _write(self, line: str) -> bool:
        """Under _lock."""
        try:
            self._proc.stdin.write(line.encode("ascii") + b"\n")
            self._proc.stdin.flush()
            return True
        except (OSError, AttributeError, ValueError):  # it has just ended (the reader notices), or isn't there
            return False

    def say(self, text: str) -> None:
        with self._lock:
            if self._proc is None and self._deaths < MAX_DEATHS:
                self._spawn()
            sent = self._proc is not None and self._write("say " + json.dumps(text))
            if sent:
                self._pending += 1
                self.speaking = True
        if not sent:
            log.warning("Piper: nečtu, jeho proces neběží")
            self.finished.emit()  # what waits for this text goes on

    def stop(self, wait: float = 0) -> None:
        """Silence now, and what's queued is dropped (each still ends with `finished`). wait: kept for the callers;
        the sound card is the Piper process's own, Orbit's PortAudio can re-initialize any time."""
        with self._lock:
            if self._proc is not None and self._pending:
                self._write("stop")

    def release(self, wait: float) -> bool:
        """Is the sound card free for PortAudio in Orbit's process to re-initialize? Always: Piper plays in its own
        process, which re-reads the devices itself before each text (_fresh_output)."""
        return True

    def close(self) -> None:
        """Ends the Piper process (another voice was chosen). What was being said counts as finished."""
        with self._lock:
            proc, self._proc = self._proc, None
            pending, self._pending = self._pending, 0
            self.speaking = False
            if proc is not None:
                try:
                    proc.stdin.close()  # it ends on that, also in the middle of a text
                except OSError:
                    pass
                kill = threading.Timer(10, lambda: proc.poll() is None and proc.kill())
                kill.daemon = True  # never keeps Orbit alive after Ukončit
                kill.start()
        for _ in range(pending):
            self.finished.emit()

    def _read(self, proc: subprocess.Popen) -> None:
        """The Piper process's lines, until it ends."""
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line == "done":
                with self._lock:
                    if proc is not self._proc:
                        continue
                    self._pending = max(0, self._pending - 1)
                    self.speaking = self._pending > 0
                self.finished.emit()
            elif line.startswith("loaded "):
                log.info("Předčítání: Piper %s načten (%s s)", self.model, line.split()[1])
            elif line.startswith("error "):
                try:
                    why = json.loads(line[6:])
                except ValueError:
                    why = line[6:]
                log.warning("Piper: předčítání selhalo: %s", why)
            elif line:
                log.info("Piper: %s", line[:300])  # its own error output (a traceback, espeak)
        code = proc.wait()
        proc.stdout.close()
        with self._lock:
            if proc is not self._proc:  # closed by Orbit
                return
            self._proc = None
            try:
                proc.stdin.close()
            except OSError:
                pass
            self._deaths += 1
            pending, self._pending = self._pending, 0
            self.speaking = False
        from .whisper_server import exit_text
        log.warning("Piper: proces skončil (%s)%s", exit_text(code),
                    "" if self._deaths < MAX_DEATHS else ", znovu už ho nespouštím")
        for _ in range(pending):
            self.finished.emit()


# --- the Piper process ----------------------------------------------------------------------

def _load_voice(model: str, espeak: str):
    import onnxruntime
    from piper import PiperVoice
    from piper.config import PiperConfig

    options = onnxruntime.SessionOptions()
    # Without the memory arena it keeps a few MB after a long text instead of ~530 MB; without spinning its threads
    # don't burn a core between sentences and for a second after. ~1.5× slower, still ~9× faster than real time.
    options.enable_cpu_mem_arena = False
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) // 2))
    with open(f"{model}.json", encoding="utf-8") as f:
        config = PiperConfig.from_dict(json.load(f))
    session = onnxruntime.InferenceSession(model, sess_options=options, providers=["CPUExecutionProvider"])
    return PiperVoice(session=session, config=config, espeak_data_dir=Path(espeak))


def _fresh_output() -> None:
    """PortAudio reads the sound devices, and which one is the Windows default, once when it starts. Without this the
    Piper process would play for Orbit's whole run on the speakers that were the default at Orbit's start: a headset
    plugged in later stays silent, and once that device is gone the MME numbers shift (another device, or every
    text fails). So it starts again before each text (~30 ms), while this process has no stream open (its only one
    is closed between texts); the same as Recorder's refresh does in Orbit's process."""
    try:
        sd._terminate()
    except sd.PortAudioError:
        pass  # not running: the last start failed
    sd._initialize()


def _play(voice, text: str, stopped) -> None:
    stream = None
    try:
        for chunk in voice.synthesize(text):
            if stopped():
                break
            if stream is None:
                _fresh_output()
                stream = sd.OutputStream(samplerate=chunk.sample_rate, channels=1, dtype="int16")
                stream.start()
            audio, step = chunk.audio_int16_array, chunk.sample_rate // 10
            for i in range(0, len(audio), step):  # 0.1 s at a time, so stop is heard at once
                if stopped():
                    break
                stream.write(audio[i:i + step])
    finally:
        if stream is not None:
            if stopped():
                stream.abort()  # drop what's buffered
            else:
                stream.stop()  # let the end of the last sentence play out
            stream.close()


def _stdin_lines():
    """stdin's lines, until Orbit closes it or ends. Never a blocking read: while one thread waits in ReadFile on
    the stdin pipe, a DLL with its own C runtime loading in another thread (numpy's, at import) hangs for good in
    GetFileType(stdin). So it peeks at the pipe and reads only what's there."""
    import msvcrt
    import time
    from ctypes import wintypes

    peek = ctypes.windll.kernel32.PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    fd = sys.stdin.fileno()
    handle, ready, rest = msvcrt.get_osfhandle(fd), wintypes.DWORD(), b""
    while True:
        if not peek(handle, None, 0, None, ctypes.byref(ready), None):
            return  # the other end is closed
        if not ready.value:
            time.sleep(0.02)
            continue
        data = os.read(fd, ready.value)
        if not data:
            return
        *lines, rest = (rest + data).split(b"\n")
        for line in lines:
            yield line.decode("ascii", "replace")


def _worker(model: str, espeak: str) -> None:
    """The Piper process (PiperSpeaker): loads the voice, then says the texts that come, one after another.
    In (stdin): "say <JSON text>", "stop" (everything said so far), end of input = Orbit is gone. Out (stdout):
    "loaded <seconds>", "done" (once per say, also when stopped), "error <JSON text>"."""
    import queue
    import time

    out = threading.Lock()

    def send(line: str) -> None:
        with out:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    texts: queue.Queue = queue.Queue()
    stopped_upto = [0]  # the says numbered up to this one are stopped

    def run() -> None:
        try:
            t0 = time.perf_counter()
            voice = _load_voice(model, espeak)
            send(f"loaded {time.perf_counter() - t0:.1f}")
        except Exception as e:
            send("error " + json.dumps(f"hlas nejde načíst: {type(e).__name__}: {e}"))
            os._exit(1)
        while True:
            number, text = texts.get()
            try:
                if number > stopped_upto[0]:
                    _play(voice, text, lambda: number <= stopped_upto[0])
            except Exception as e:
                send("error " + json.dumps(f"{type(e).__name__}: {e}"))
            send("done")

    threading.Thread(target=run, daemon=True).start()
    number = 0
    for line in _stdin_lines():
        command, _, arg = line.strip().partition(" ")
        if command == "say":
            number += 1
            texts.put((number, json.loads(arg)))
        elif command == "stop":
            stopped_upto[0] = number
    os._exit(0)  # Orbit closed the pipe or ended: not a word more
