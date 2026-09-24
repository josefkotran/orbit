import logging
import math
import threading

import numpy as np
import sounddevice as sd

from .whisper_server import SAMPLE_RATE

log = logging.getLogger(__name__)

# Live transcription: a finished part of the speech is cut off at a pause and transcribed while the user keeps
# talking. Tuned on Pepa's recordings (docs in CLAUDE.md): his pauses between sentences are 0.4–1.3 s.
PAUSE_RMS = 150  # a block quieter than this is a pause (the HyperX idles at 1–11, speech is 150–800)
PAUSE_S = 0.5
MIN_PIECE_S = 6.0  # every piece costs ~0.9 s of fixed Whisper time and short ones are less accurate


def _mme_inputs() -> list[tuple[int, str]]:
    """Input devices on the MME host API: one entry per microphone, named like in Windows sound settings."""
    try:
        mme = next(i for i, h in enumerate(sd.query_hostapis()) if h["name"] == "MME")
    except StopIteration:
        mme = None
    result = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0 or (mme is not None and d["hostapi"] != mme):
            continue
        if "Sound Mapper" in d["name"] or "Mapovač" in d["name"]:
            continue
        result.append((i, d["name"]))
    return result


def input_devices(refresh: bool = False) -> list[str]:
    if refresh:
        # PortAudio caches the device list; re-initialize to see newly plugged microphones.
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            log.exception("Obnovení seznamu zařízení selhalo")
    return [name for _, name in _mme_inputs()]


def _find_device(name: str | None) -> int | None:
    if not name:
        return None
    for i, n in _mme_inputs():
        if n == name:
            return i
    log.warning("Mikrofon '%s' nenalezen, používám výchozí", name)
    return None


def is_silent(audio: np.ndarray) -> bool:
    if len(audio) < 0.3 * SAMPLE_RATE:
        return True
    frame = SAMPLE_RATE * 30 // 1000
    frames = audio[: len(audio) // frame * frame].reshape(-1, frame).astype(np.float32)
    return float(np.sqrt((frames ** 2).mean(axis=1)).max()) < 200  # ~ -44 dBFS


class Recorder:
    """Records from the microphone between start() and stop(); the mic is open only while recording
    (or while the settings window shows its live meter).

    Many USB headsets deliver ~0.2 s of pure silence right after the stream opens. on_live is called once
    per recording when real audio starts flowing, so the app can say "speak now" only when it's true.
    """

    def __init__(self, on_live=None, on_piece=None):
        self._on_live = on_live or (lambda: None)
        self._on_piece = on_piece or (lambda: None)  # a piece is ready in pop_pieces()
        self.split = False  # cut the recording at pauses (live transcription)
        self._stream: sd.InputStream | None = None
        self._rate = SAMPLE_RATE
        self._lock = threading.Lock()
        self._recording = False
        self._live = False
        self._monitoring = False
        self._chunks: list[np.ndarray] = []
        self._pieces: list[np.ndarray] = []
        self._quiet_blocks = 0
        self._device_name: str | None = None
        self.level = 0.0  # 0..1, for the UI meters

    @property
    def active(self) -> bool:
        return self._recording

    @property
    def live(self) -> bool:
        return self._recording and self._live

    def configure(self, device_name: str | None) -> None:
        if self._device_name == device_name:
            return
        self._device_name = device_name
        if self._stream is not None and not self._recording:
            self._close()
            if self._monitoring:
                self._open()

    def set_monitor(self, on: bool) -> None:
        """Keep the mic open for a live level meter (settings window) without recording."""
        self._monitoring = on
        if on and self._stream is None:
            try:
                self._open()
            except Exception:
                log.exception("Mikrofon pro ukazatel hlasitosti nejde otevřít")
        elif not on and not self._recording:
            self._close()

    def start(self) -> None:
        if self._stream is None or not self._stream.active:
            self._close()
            self._open()
            already_live = False
        else:
            already_live = True  # stream was running for the meter – audio is flowing already
        with self._lock:
            self._chunks = []
            self._pieces = []
            self._quiet_blocks = 0
            self._live = already_live
            self._recording = True
        if already_live:
            self._on_live()

    def force_live(self) -> None:
        """Fallback for mics that keep sending exact zeros (e.g. muted)."""
        with self._lock:
            fire = self._recording and not self._live
            self._live = True
        if fire:
            self._on_live()

    def stop(self) -> np.ndarray:
        with self._lock:
            self._recording = False
            chunks, self._chunks = self._chunks, []
        if not self._monitoring:
            self._close()
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        return self._to_16k(np.concatenate(chunks))

    def pop_pieces(self) -> list[np.ndarray]:
        """Parts of the recording already cut off at pauses (after stop() it returns the rest of them)."""
        with self._lock:
            pieces, self._pieces = self._pieces, []
        return [self._to_16k(p) for p in pieces]

    def _to_16k(self, audio: np.ndarray) -> np.ndarray:
        if self._rate == SAMPLE_RATE:
            return audio
        n = int(len(audio) * SAMPLE_RATE / self._rate)
        return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.int16)

    def shutdown(self) -> None:
        self._recording = False
        self._monitoring = False
        self._close()

    # ---------------------------------------------------------------------------------------

    def _open(self) -> None:
        device = _find_device(self._device_name)
        try:
            self._open_at(device, SAMPLE_RATE)
        except sd.PortAudioError:
            rate = int(sd.query_devices(device, "input")["default_samplerate"])
            log.info("Zařízení neumí %s Hz, nahrávám v %s Hz", SAMPLE_RATE, rate)
            self._open_at(device, rate)

    def _open_at(self, device: int | None, rate: int) -> None:
        self._rate = rate
        stream = sd.InputStream(device=device, samplerate=rate, channels=1, dtype="int16",
                                blocksize=rate * 30 // 1000, callback=self._callback)
        stream.start()
        self._stream = stream

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        self.level = 0.0
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.exception("Zavření mikrofonu selhalo")

    def _callback(self, indata, frames, time_info, status):
        chunk = indata[:, 0].copy()
        rms = math.sqrt(float(np.mean(chunk.astype(np.float32) ** 2)))
        went_live = cut = False
        with self._lock:
            if self._recording:
                if not self._live and np.any(chunk):  # start-up silence is exact zeros
                    self._live = went_live = True
                if self._live:  # the headset's start-up silence is useless, skip it
                    self._chunks.append(chunk)
                    if self.split:
                        cut = self._cut_at_pause(rms, len(chunk))
        if went_live:
            self._on_live()
        if cut:
            self._on_piece()
        self.level = min(1.0, max(0.0, (20 * math.log10(rms / 32768 + 1e-9) + 50) / 40))

    def _cut_at_pause(self, rms: float, block: int) -> bool:
        """Once a pause is PAUSE_S long and at least MIN_PIECE_S of audio precedes it, move everything up to
        the middle of the pause into a piece. Runs under the lock for every block."""
        self._quiet_blocks = self._quiet_blocks + 1 if rms < PAUSE_RMS else 0
        need = round(PAUSE_S * self._rate / block)
        before = len(self._chunks) - need
        if self._quiet_blocks != need or before * block < MIN_PIECE_S * self._rate:
            return False
        keep = before + need // 2
        self._pieces.append(np.concatenate(self._chunks[:keep]))
        del self._chunks[:keep]
        return True
