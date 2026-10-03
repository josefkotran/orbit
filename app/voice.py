"""Local Czech voices (Piper) for reading aloud, instead of Windows' Jakub.

Everything runs on this PC: an ONNX model on the CPU, about 0.1 s per sentence once loaded (loading takes ~1.7 s,
done once, on the first text). Piper hands over the audio sentence by sentence, so the first one plays while the
rest are still being made. Models: <data>/models/piper/<name>.onnx + .onnx.json from
huggingface.co/rhasspy/piper-voices, downloaded on demand (downloads.py). Piper (piper-tts) is GPL-3.0 and optional:
without it only Jakub is offered.
"""
import functools
import importlib.util
import logging
import threading

import sounddevice as sd

from PySide6.QtCore import QObject, Signal

from .config import MODELS_DIR

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


@functools.cache
def piper_installed() -> bool:
    return importlib.util.find_spec("piper") is not None


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
    working = usable()
    return choice if choice in working else next(iter(working), None)


def missing_text() -> str:
    """What to tell the user when there is no Czech voice to read with."""
    if piper_installed():
        return ("Ve Windows chybí český hlas pro předčítání. Klikni a stáhnu hlas Jirka (63 MB, běží jen u tebe). "
                "Nebo si hlas vyber v nastavení Orbitu.")
    return ("Chybí český hlas pro předčítání. Přidej ho ve Windows: Nastavení › Čas a jazyk › Řeč › Přidat hlasy › "
            "Čeština.")


class PiperSpeaker(QObject):
    """Says one text at a time in a worker thread. `finished` comes when it's done or stopped."""

    finished = Signal()

    def __init__(self, model: str):
        super().__init__()
        self.model = model
        self.speaking = False
        self._voice = None
        self._stop = threading.Event()
        self._lock = threading.Lock()  # a new text waits until the stopped one has let go of the sound card
        threading.Thread(target=self._load, daemon=True).start()  # ready before the first text

    def _load(self) -> None:
        with self._lock:
            if self._voice is None:
                from piper import PiperVoice  # here: onnxruntime takes a moment to import
                self._voice = PiperVoice.load(PIPER_DIR / f"{self.model}.onnx")
                log.info("Předčítání: Piper %s načten", self.model)

    def say(self, text: str) -> None:
        self._stop.clear()
        self.speaking = True
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def stop(self, wait: float = 0) -> None:
        """wait: seconds to wait until the sound card is let go (before PortAudio is re-initialized, which would
        free the stream under the playing thread)."""
        self._stop.set()
        if wait:
            self.release(wait)

    def release(self, wait: float) -> bool:
        """Has it let go of the sound card (no OutputStream of its own) within `wait` seconds? It holds _lock while
        it loads and while it plays."""
        if not self._lock.acquire(timeout=wait):
            return False
        self._lock.release()
        return True

    def _run(self, text: str) -> None:
        try:
            self._load()  # waits if it's still loading
            with self._lock:
                self._play(text)
        except Exception:
            log.exception("Piper: předčítání selhalo")
        finally:
            self.speaking = False
            self.finished.emit()

    def _play(self, text: str) -> None:
        stream = None
        try:
            for chunk in self._voice.synthesize(text):
                if self._stop.is_set():
                    break
                if stream is None:
                    stream = sd.OutputStream(samplerate=chunk.sample_rate, channels=1, dtype="int16")
                    stream.start()
                audio, step = chunk.audio_int16_array, chunk.sample_rate // 10
                for i in range(0, len(audio), step):  # 0.1 s at a time, so stop() is heard at once
                    if self._stop.is_set():
                        break
                    stream.write(audio[i:i + step])
        finally:
            if stream is not None:
                if self._stop.is_set():
                    stream.abort()  # drop what's buffered
                else:
                    stream.stop()  # let the end of the last sentence play out
                stream.close()
