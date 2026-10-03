import collections
import ctypes
import logging
import math
import threading
from ctypes import wintypes

import numpy as np
import sounddevice as sd

from .whisper_server import SAMPLE_RATE

log = logging.getLogger(__name__)

# Live transcription: a finished part of the speech is cut off at a pause and transcribed while the user keeps
# talking. Tuned on Pepa's recordings (docs in CLAUDE.md): his pauses between sentences are 0.4–1.3 s.
PAUSE_RMS = 150  # a block quieter than this is a pause (the HyperX idles at 1–11, speech is 150–800)
PAUSE_S = 0.5
MIN_PIECE_S = 6.0  # every piece costs ~0.9 s of fixed Whisper time and short ones are less accurate
# Hands-free listening (a click instead of holding, for the voice agent): it ends by itself after the speech.
END_SILENCE_S = 1.4  # quiet this long after speech = done (his pauses between sentences are up to 1.3 s)
NO_SPEECH_S = 6.0  # nothing said this long after the click = give up
SILENCE_RMS = 200  # a recording whose loudest 30 ms stays under this is silence (~ -44 dBFS)
# A noisy mic (an analog one with Windows' +20 dB boost, a loud fan) hisses above PAUSE_RMS: the limits then follow
# its noise floor = the quietest 30 ms block of the last ~3 s. Never below the constants above (tuned on quiet mics):
# the estimate starts at PAUSE_RMS / NOISE_FACTOR and rises at most NOISE_RISE per block (falls at once), so speech
# without a single quiet moment for seconds doesn't pass for noise.
NOISE_BLOCKS = 100
NOISE_FACTOR = 3
NOISE_RISE = 1.02  # per 30 ms block: 50 → 250 in ~2.5 s
VOICE_RMS = 50  # louder than a quiet mic's noise, quieter than speech counts (Recorder.voiced_s: "too quiet")


def _hostapi(name: str) -> int | None:
    return next((i for i, h in enumerate(sd.query_hostapis()) if h["name"] == name), None)


def _mme_devices() -> list[int]:
    """The MME host API's input devices, in PortAudio's order: the first one is always Windows' "Sound Mapper"
    (named in the language of Windows), which records from whatever is the default microphone right now."""
    mme = _hostapi("MME")
    if mme is None:
        return []
    return [i for i in sd.query_hostapis(mme)["devices"] if sd.query_devices(i)["max_input_channels"] > 0]


def _mme_inputs() -> list[tuple[int, str]]:
    """Input devices on the MME host API: one entry per microphone, named like in Windows sound settings."""
    return [(i, sd.query_devices(i)["name"]) for i in _mme_devices()[1:]]


def _mapper() -> int | None:
    """The Sound Mapper (see _mme_devices); None when Windows has no microphone at all."""
    return next(iter(_mme_devices()), None)


class _WaveInCaps(ctypes.Structure):
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT),
                ("szPname", wintypes.WCHAR * 32), ("dwFormats", wintypes.DWORD), ("wChannels", wintypes.WORD),
                ("wReserved1", wintypes.WORD)]


def _windows_inputs() -> list[str] | None:
    """Windows' list of microphones right now (winmm, ~0.3 ms; names cut to 31 characters like MME's), None when
    it can't be read."""
    try:
        winmm = ctypes.windll.winmm
        names = []
        for i in range(winmm.waveInGetNumDevs()):
            caps = _WaveInCaps()
            if winmm.waveInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) != 0:
                return None
            names.append(caps.szPname)
        return names
    except OSError:
        return None


def _devices_changed() -> bool:
    """Has a microphone been plugged in or out since PortAudio read its list? PortAudio maps its device numbers to
    Windows' once, so a stale list opens the wrong microphone (or none)."""
    live = _windows_inputs()
    if live is None:
        return False
    cached = [name for _, name in _mme_inputs()]
    return len(live) != len(cached) or any(not c.startswith(w) for w, c in zip(live, cached))


def _refresh() -> None:
    """PortAudio caches the device list; re-initialize (~30 ms) to see newly plugged microphones.
    Only while no stream is open: Pa_Terminate frees every stream, Piper's playing one too (see Recorder.may_refresh)."""
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        log.exception("Obnovení seznamu zařízení selhalo")


def input_devices(refresh: bool = False) -> list[str]:
    if refresh:
        _refresh()
    return [name for _, name in _mme_inputs()]


def is_bluetooth_handsfree(name: str | None) -> bool:
    """A Bluetooth headset's mic works only in the hands-free (call) profile: while it's open, Windows switches
    the headset from stereo music to mono call sound and the mic records in telephone quality (AirPods Max:
    8 kHz, nothing above 4 kHz). Recognized by the WASAPI twin of the MME device (MME cuts names to 31 chars)
    running at 16 kHz or less; USB and analog mics run at 44.1/48 kHz. None = the Windows default mic."""
    try:
        if not name:
            mme = _hostapi("MME")
            default = sd.query_hostapis(mme)["default_input_device"] if mme is not None else -1
            if default < 0:
                return False
            name = sd.query_devices(default)["name"]
        wasapi = _hostapi("Windows WASAPI")
        for d in sd.query_devices():
            if d["hostapi"] == wasapi and d["max_input_channels"] > 0 and d["name"].startswith(name):
                return d["default_samplerate"] <= 16000
    except Exception:
        log.exception("Zjištění typu mikrofonu selhalo")
    return False


def is_silent(audio: np.ndarray, noise: float = 0.0) -> bool:
    """Too short, or nothing louder than silence (noise: the mic's noise floor, see Recorder.noise)."""
    if len(audio) < 0.3 * SAMPLE_RATE:
        return True
    frame = SAMPLE_RATE * 30 // 1000
    frames = audio[: len(audio) // frame * frame].reshape(-1, frame).astype(np.float32)
    return float(np.sqrt((frames ** 2).mean(axis=1)).max()) < max(SILENCE_RMS, NOISE_FACTOR * noise)


class Recorder:
    """Records from the microphone between start() and stop(); the mic is open only while recording
    (or while the settings window shows its live meter).

    Many USB headsets deliver ~0.2 s of pure silence right after the stream opens. on_live is called once
    per recording when real audio starts flowing, so the app can say "speak now" only when it's true.
    """

    def __init__(self, on_live=None, on_piece=None, on_end=None):
        self._on_live = on_live or (lambda: None)
        self._on_piece = on_piece or (lambda: None)  # a piece is ready in pop_pieces()
        self._on_end = on_end or (lambda: None)  # hands-free: the speech is over (once per recording)
        self.split = False  # cut the recording at pauses (live transcription)
        self.end_on_silence = False  # hands-free: call on_end after the speech
        # called before PortAudio is re-initialized (which frees every stream): False = not now (Piper still plays)
        self.may_refresh = lambda: True
        self._stream: sd.InputStream | None = None
        self._rate = SAMPLE_RATE
        self._lock = threading.Lock()
        self._recording = False
        self._live = False
        self._monitoring = False
        self._chunks: list[np.ndarray] = []
        self._pieces: list[np.ndarray] = []
        self._quiet_blocks = 0
        self._heard = False  # hands-free: speech has started
        self._silent_blocks = 0  # hands-free: quiet blocks since the last loud one
        self._blocks = 0
        self._recent: collections.deque[float] = collections.deque(maxlen=NOISE_BLOCKS)  # block RMS, for noise
        self.noise = 0.0  # the mic's noise floor now (0 = not known yet)
        self.got_signal = False  # anything but exact zeros came in this recording (a muted mic sends only zeros)
        self._voiced = 0  # blocks of this recording clearly above the noise (speech, maybe too quiet)
        self._device_name: str | None = None
        self.level = 0.0  # 0..1, for the UI meters

    @property
    def active(self) -> bool:
        return self._recording

    @property
    def live(self) -> bool:
        return self._recording and self._live

    @property
    def voiced_s(self) -> float:
        """Seconds of the last recording clearly above the mic's noise (blocks are 30 ms)."""
        return self._voiced * 0.03

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
            self._heard, self._silent_blocks, self._blocks = False, 0, 0
            self.end_on_silence = False
            self.got_signal = False
            self._voiced = 0
            self._recent.clear()
            self.noise = 0.0
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

    def _refresh_devices(self) -> bool:
        """Re-reads the device list, unless something still plays through PortAudio (may_refresh). True if it did."""
        try:
            allowed = self.may_refresh()
        except Exception:
            log.exception("Kontrola přehrávání před obnovením zařízení selhala")
            allowed = False
        if not allowed:
            log.info("Seznam mikrofonů teď neobnovuji, ještě se přehrává zvuk")
            return False
        _refresh()
        return True

    def _find(self) -> int | None:
        """The chosen microphone, else the Sound Mapper: it records from the Windows default as it is right now (not
        the one when PortAudio read its list). None = no microphone at all."""
        name = self._device_name
        if name:
            found = next((i for i, n in _mme_inputs() if n == name), None)
            if found is None and self._refresh_devices():  # plugged in (or reconnected over Bluetooth) since
                found = next((i for i, n in _mme_inputs() if n == name), None)
            if found is not None:
                return found
            log.warning("Mikrofon '%s' nenalezen, používám výchozí", name)
        return _mapper()

    def _open(self) -> None:
        if _devices_changed():  # a mic plugged in or out: PortAudio's cached numbers would open another one
            log.info("Mikrofony se změnily, obnovuji jejich seznam")
            self._refresh_devices()
        device = self._find()
        if device is None and self._refresh_devices():
            device = self._find()
        if device is None:
            raise RuntimeError("Windows teď nevidí žádný mikrofon.")
        try:
            self._open_at(device, SAMPLE_RATE)
            return
        except sd.PortAudioError as e:
            log.warning("Mikrofon nejde otevřít (%s)", e)
        if self._refresh_devices():  # unplugged since the list was read: once more with a fresh one
            device = self._find()
            if device is None:
                raise RuntimeError("Windows teď nevidí žádný mikrofon.")
            try:
                self._open_at(device, SAMPLE_RATE)
                return
            except sd.PortAudioError:
                pass
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

    def _quiet_limit(self) -> float:
        """A block under this is quiet (a pause, not speech): PAUSE_RMS, more on a mic that hisses louder."""
        return max(PAUSE_RMS, NOISE_FACTOR * self.noise)

    def _callback(self, indata, frames, time_info, status):
        chunk = indata[:, 0].copy()
        rms = math.sqrt(float(np.mean(chunk.astype(np.float32) ** 2)))
        went_live = cut = ended = False
        with self._lock:
            if self._recording:
                if np.any(chunk):  # start-up silence (and a muted mic) is exact zeros
                    self.got_signal = True
                    if not self._live:
                        self._live = went_live = True
                if self._live:  # the headset's start-up silence is useless, skip it
                    self._chunks.append(chunk)
                    self._recent.append(rms)
                    if len(self._recent) >= 10:
                        start = max(self.noise, PAUSE_RMS / NOISE_FACTOR)
                        self.noise = min(min(self._recent), start * NOISE_RISE)
                    if rms >= max(VOICE_RMS, NOISE_FACTOR * self.noise):
                        self._voiced += 1
                    if self.split:
                        cut = self._cut_at_pause(rms, len(chunk))
                    ended = self._speech_over(rms, len(chunk))
        if went_live:
            self._on_live()
        if cut:
            self._on_piece()
        if ended:
            self._on_end()
        self.level = min(1.0, max(0.0, (20 * math.log10(rms / 32768 + 1e-9) + 50) / 40))

    def _speech_over(self, rms: float, block: int) -> bool:
        """Hands-free: True once, when END_SILENCE_S of quiet follows speech (or nothing was said for NO_SPEECH_S).
        Counted for every block, so switching hands-free on after a short press still sees the speech before."""
        self._blocks += 1
        if rms >= self._quiet_limit():
            self._heard, self._silent_blocks = True, 0
        else:
            self._silent_blocks += 1
        if not self.end_on_silence:
            return False
        seconds = block / self._rate
        if (self._heard and self._silent_blocks * seconds >= END_SILENCE_S) or \
                (not self._heard and self._blocks * seconds >= NO_SPEECH_S):
            self.end_on_silence = False
            return True
        return False

    def _cut_at_pause(self, rms: float, block: int) -> bool:
        """Once a pause is PAUSE_S long and at least MIN_PIECE_S of audio precedes it, move everything up to
        the middle of the pause into a piece. Runs under the lock for every block."""
        self._quiet_blocks = self._quiet_blocks + 1 if rms < self._quiet_limit() else 0
        need = round(PAUSE_S * self._rate / block)
        before = len(self._chunks) - need
        if self._quiet_blocks != need or before * block < MIN_PIECE_S * self._rate:
            return False
        keep = before + need // 2
        self._pieces.append(np.concatenate(self._chunks[:keep]))
        del self._chunks[:keep]
        return True
