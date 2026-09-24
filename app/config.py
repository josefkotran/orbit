import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
MODELS_DIR = ROOT / "models"
WHISPER_DIR = ROOT / "whisper"
ASSETS_DIR = ROOT / "assets"
LOG_PATH = ROOT / "orbit.log"
RECORDINGS_DIR = ROOT / "recordings"

MODEL_LABELS = {
    "ggml-large-v3.bin": "large-v3 (nejpřesnější, doporučeno)",
    "ggml-large-v3-turbo.bin": "large-v3-turbo (2× rychlejší, o 14 % víc chyb)",
}

DEFAULTS = {
    # Push-to-talk binding: kind "key" (Windows virtual-key code) or "mouse" (4 = middle, 5 = X1, 6 = X2)
    "ptt": {"kind": "key", "code": 0xA3},  # Right Ctrl
    "model": "ggml-large-v3.bin",
    "mic": None,  # None = Windows default input device, otherwise device name
    "vocabulary": "",  # words/names Whisper should spell correctly, comma or newline separated
    "replacements": [],  # [wrong, right] phrase fixes applied to every transcript
    "learn_vocabulary": True,  # let Claude extend vocabulary/replacements from the transcripts in the log
    "learned_until": None,  # log timestamp of the last transcript Claude has seen
    "voice_commands": True,  # "nový řádek" / "nový odstavec"
    "live_transcribe": True,  # transcribe finished parts at pauses while still recording
    "keep_recordings": False,  # save the last recordings to recordings/ (for tuning)
    "insert_mode": "paste",  # "paste" (clipboard + Ctrl+V) or "type" (Unicode keystrokes)
    "trailing_space": True,
    "sounds": True,
    "show_button": True,
    "show_usage": True,  # Claude plan usage panel above the mic button
    "show_sessions": True,  # Claude Code sessions in that panel (needs Orbit's hooks in ~/.claude/settings.json)
    "speak_answers": True,  # read the start of a finished session's answer aloud
    "button_pos": None,
}

log = logging.getLogger(__name__)


def is_first_run() -> bool:
    return not CONFIG_PATH.exists()


def load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))
    except FileNotFoundError:
        pass
    except Exception:
        log.exception("Nelze načíst config.json, používám výchozí nastavení")
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def available_models() -> list[str]:
    return sorted(p.name for p in MODELS_DIR.glob("ggml-*.bin"))
