"""The second recognizer for the transcript check (check.py): NVIDIA Canary-1B-v2, an ONNX model on the processor,
fully on this PC. Its own transcript of each piece goes to Claude next to Whisper's: where the two differ Claude
takes the one that is real Czech. Measured 24 Oct (WER): FLEURS Whisper 9.3 %, Canary 8.5 %, the check with Canary's
transcript 4.7 % (without it 6.9 %); VoxPopuli (spontaneous speech, 44 speakers) 12.7 %, 9.1 %, 9.4 %. On its own
it's no replacement for Whisper: it has no vocabulary prompt and on Pepa's dictations wrote "SPD" for Speedy and
"nebezpečné" for "zabezpečné", but next to Whisper it gave the check "od Kimiho" (Whisper: "od kým jeho") and "část"
(Whisper: "čas"), and nothing wrong was taken from it.

Model: <data>/models/canary-1b-v2/ (istupakov/canary-1b-v2-onnx at a pinned revision, full precision: 4 GB on
disk, ~4 GB of memory while it runs; downloads.py), licence CC BY 4.0. Runs with onnx-asr (MIT) on onnxruntime, both
optional: without them it isn't offered.

It runs in a process of its own (SecondOpinion -> _worker), like Piper (voice.py): loading 4 GB of ONNX holds the
GIL for seconds, which in Orbit's process would freeze the UI and the system's keyboard and mouse hooks; it's
started at below-normal priority, so a burst of decoding on all cores doesn't stutter anything else.
"""
import base64
import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import time

import numpy as np

from .config import MODELS_DIR
from .paths import ROOT

log = logging.getLogger(__name__)

KEY = "canary-1b-v2"  # downloads.ITEMS
MODEL_DIR = MODELS_DIR / KEY
QUANTIZATION = None  # full precision (see downloads.ITEMS)
MAX_PIECE_S = 40  # longer pieces aren't given to it (it was trained on shorter ones; Whisper's text is checked alone)
WAIT_S = 30  # one piece's transcript, at most (the first one also waits for the model to load)
MAX_DEATHS = 3  # the process ended on its own this often: no more tries in this run
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
_WORKER_CODE = "import sys; sys.path.insert(0, sys.argv[1]); from app.canary import _worker; _worker(*sys.argv[2:])"


def available() -> bool:
    """onnx-asr and onnxruntime are part of this Orbit (an installer built --without-piper has no onnxruntime)."""
    return all(importlib.util.find_spec(name) is not None for name in ("onnx_asr", "onnxruntime"))


def downloaded() -> bool:
    from .downloads import ITEMS
    return ITEMS[KEY].present()


def usable() -> bool:
    return available() and downloaded()


class SecondOpinion:
    """transcribe() from any thread (one at a time is fine: the process does one piece after another)."""

    def __init__(self, worker_code: str = _WORKER_CODE, model_dir=MODEL_DIR):
        self._code, self._dir = worker_code, model_dir
        self._lock = threading.Lock()  # the process, its stdin, the waiting answers
        self._proc: subprocess.Popen | None = None
        self._waiting: dict[int, list] = {}  # request id -> [threading.Event, answer]
        self._next = 0
        self._deaths = 0
        self.loaded_s: float | None = None  # how long the model took to load (once it has)

    def start(self) -> None:
        """Loads the model right away, so the first dictation doesn't wait for it."""
        with self._lock:
            if self._proc is None and self._deaths < MAX_DEATHS:
                self._spawn()

    def _spawn(self) -> None:
        """Under _lock. The same pythonw that runs Orbit, without the user's environment variables (-I)."""
        from .whisper_server import _tie_to_this_process
        threads = max(1, min(8, (os.cpu_count() or 2) // 2))  # the physical cores (Whisper is on the graphics card)
        env = dict(os.environ)
        env.setdefault("OPENBLAS_NUM_THREADS", "1")  # numpy: no idle thread per processor (see Orbit.pyw)
        try:
            proc = subprocess.Popen([sys.executable, "-I", "-c", self._code, str(ROOT), str(self._dir), str(threads)],
                                    cwd=str(ROOT), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS)
        except OSError:
            log.exception("Druhý rozpoznávač: proces nejde spustit")
            self._deaths = MAX_DEATHS
            return
        _tie_to_this_process(proc)  # it ends with Orbit, even when Orbit crashes (and on stdin's end anyway)
        self._proc = proc
        threading.Thread(target=self._read, args=(proc,), daemon=True).start()

    def transcribe(self, audio: np.ndarray, timeout: float = WAIT_S) -> str | None:
        """Blocking: Canary's text of 16 kHz int16 audio; None when it's not running, failed or took too long."""
        if len(audio) > MAX_PIECE_S * 16000:
            return None
        pcm = base64.b64encode(np.ascontiguousarray(audio, dtype=np.int16).tobytes()).decode("ascii")
        with self._lock:
            if self._proc is None and self._deaths < MAX_DEATHS:
                self._spawn()
            if self._proc is None:
                return None
            self._next += 1
            number, slot = self._next, [threading.Event(), None]
            self._waiting[number] = slot
            try:
                self._proc.stdin.write(json.dumps({"id": number, "pcm": pcm}).encode("ascii") + b"\n")
                self._proc.stdin.flush()
            except (OSError, ValueError):  # it has just ended (the reader notices)
                self._waiting.pop(number, None)
                return None
        got = slot[0].wait(timeout)
        with self._lock:
            self._waiting.pop(number, None)
        if not got:
            log.warning("Druhý rozpoznávač neodpověděl do %d s", timeout)
        return slot[1] if got else None

    def close(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
            waiting, self._waiting = self._waiting, {}
        for slot in waiting.values():
            slot[0].set()
        if proc is not None:
            try:
                proc.stdin.close()  # it ends on that
            except OSError:
                pass
            kill = threading.Timer(10, lambda: proc.poll() is None and proc.kill())
            kill.daemon = True  # never keeps Orbit alive after Ukončit
            kill.start()

    def _read(self, proc: subprocess.Popen) -> None:
        """The process's lines, until it ends."""
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("{"):
                try:
                    answer = json.loads(line)
                except ValueError:
                    continue
                with self._lock:
                    slot = self._waiting.get(answer.get("id"))
                if slot is None:
                    continue
                if "error" in answer:
                    log.warning("Druhý rozpoznávač: %s", answer["error"])
                else:
                    slot[1] = str(answer.get("text", ""))
                slot[0].set()
            elif line.startswith("loaded "):
                self.loaded_s = float(line.split()[1])
                log.info("Druhý rozpoznávač Canary načten (%s s)", line.split()[1])
            elif line.startswith("error "):
                log.warning("Druhý rozpoznávač: %s", line[6:300])
            elif line:
                log.info("Druhý rozpoznávač: %s", line[:300])  # its own error output (a traceback)
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
            waiting, self._waiting = self._waiting, {}
        for slot in waiting.values():
            slot[0].set()
        from .whisper_server import exit_text
        log.warning("Druhý rozpoznávač: proces skončil (%s)%s", exit_text(code),
                    "" if self._deaths < MAX_DEATHS else ", znovu už ho nespouštím")


# --- the Canary process -------------------------------------------------------------------------

def _load(model_dir: str, threads: int):
    import onnx_asr
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = threads
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")  # no busy cores between dictations
    return onnx_asr.load_model("nemo-conformer-aed", model_dir, quantization=QUANTIZATION, sess_options=options,
                               providers=["CPUExecutionProvider"])


def _worker(model_dir: str, threads: str = "4") -> None:
    """The Canary process (SecondOpinion). In (stdin): {"id", "pcm": base64 of 16 kHz int16} per line, end of input =
    Orbit is gone. Out (stdout): "loaded <seconds>", then {"id", "text"} or {"id", "error"} per piece."""
    from .voice import _stdin_lines  # never a blocking read of stdin (see there)

    out = threading.Lock()

    def send(line: str) -> None:
        with out:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    try:
        t0 = time.perf_counter()
        model = _load(model_dir, int(threads))
        send(f"loaded {time.perf_counter() - t0:.1f}")
    except Exception as e:
        send("error " + json.dumps(f"model nejde načíst: {type(e).__name__}: {e}"))
        os._exit(1)
    for line in _stdin_lines():  # (JSON with only ASCII both ways: a piped stdout here isn't UTF-8)
        request = None
        try:
            request = json.loads(line)
            audio = np.frombuffer(base64.b64decode(request["pcm"]), dtype=np.int16).astype(np.float32) / 32768
            text = model.recognize(audio, sample_rate=16000, language="cs") if len(audio) else ""
            send(json.dumps({"id": request.get("id"), "text": text}))
        except Exception as e:
            send(json.dumps({"id": request.get("id") if isinstance(request, dict) else None,
                             "error": f"{type(e).__name__}: {e}"}))
    os._exit(0)
