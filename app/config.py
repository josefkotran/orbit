import json
import logging
import os
import shutil
import time

from . import paths, vocab
from .paths import ROOT

# Where things are: see paths.py. The data folder is decided once per run.
DATA_DIR = paths.data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
MODELS_DIR = DATA_DIR / "models"
LOG_PATH = DATA_DIR / "orbit.log"
RECORDINGS_DIR = DATA_DIR / "recordings"
SESSIONS_DIR = DATA_DIR / "sessions"  # cc_hook.py's files
CACHE_DIR = DATA_DIR / "cache"  # generated sounds and icons
WHISPER_DIR = ROOT / "whisper"
ASSETS_DIR = ROOT / "assets"  # static files only: the app folder is read-only once installed

MODEL_LABELS = {  # the doporučeno mark comes from downloads.advise() (it depends on the graphics card)
    "ggml-large-v3.bin": "large-v3 (nejpřesnější)",
    "ggml-large-v3-turbo.bin": "large-v3-turbo (2× rychlejší, o 14 % víc chyb)",
}

DEFAULTS = {
    # Push-to-talk binding: kind "key" (Windows virtual-key code) or "mouse" (4 = middle, 5 = X1, 6 = X2)
    "ptt": {"kind": "key", "code": 0xA3},  # Right Ctrl
    "model": "ggml-large-v3.bin",
    "mic": None,  # None = Windows default input device, otherwise device name
    "name": "",  # the user's first name: the agent's prompt and its messages to sessions ("" = "uživatel")
    "about": "",  # one line about the user (field, company) for Claude when it learns the vocabulary
    "vocabulary": "",  # words/names Whisper should spell correctly, comma or newline separated
    "replacements": [],  # [wrong, right] phrase fixes applied to every transcript
    "learn_vocabulary": False,  # let Claude extend vocabulary/replacements from the transcripts in the log
    "learned_until": None,  # log timestamp of the last transcript Claude has seen
    "voice_commands": True,  # "nový řádek" / "nový odstavec"
    "live_transcribe": True,  # transcribe finished parts at pauses while still recording
    "keep_recordings": False,  # save the last recordings to recordings/ (for tuning)
    "insert_mode": "paste",  # "paste" (clipboard + Ctrl+V) or "type" (Unicode keystrokes)
    "trailing_space": True,
    "sounds": True,
    "show_button": True,
    "show_usage": True,  # Claude plan usage panel above the mic button
    # where the limits come from: "statusline" (Orbit's status line in Claude Code) or "oauth" (the internal usage
    # endpoint with Claude Code's token; not in the settings window, an older config.json gets it: see main)
    "usage_source": "statusline",
    "show_sessions": True,  # Claude Code sessions in that panel (needs Orbit's hooks in Claude Code's settings.json)
    "speak_answers": True,  # read the start of a finished session's answer aloud
    "read_artifacts": False,  # a session published an artifact: Claude sums it up in 7 sentences, read aloud
    "muted": False,  # the speaker button: no beeps, no bubble chimes, nothing read aloud
    "agent": False,  # voice agent for the Claude Code sessions: ask about them, have it write to them
    "agent_ptt": {"kind": "mouse", "code": 5},  # mouse back button: hold = talk, click = listens till you stop
    "agent_model": "sonnet",
    "voice": "jakub",  # reading aloud: "jakub" (Windows) or a Piper model in models/piper (see voice.py)
    "theme": "blue",  # colour of the look: a key of theme.THEMES
    "button_pos": None,
    # Consents: Orbit touches Claude Code's settings.json only after the user said yes (first-run wizard, settings).
    "claude_hooks": False,  # Orbit's hooks (session overview, artifacts); missing in an older config.json: see main
    "claude_statusline": False,  # Orbit's status line in Claude Code (the limits)
    "wizard_pending": False,  # first run: the setup wizard hasn't been finished (it comes back after a crash)
}
NAME_MAX = 40
ABOUT_MAX = 200

log = logging.getLogger(__name__)

problem = ""  # set by load(): what to tell the user when config.json couldn't be read ("" = all fine)
missing: set[str] = set()  # set by load(): keys an existing config.json doesn't have yet (written by an older Orbit)
# set by load(): config.json couldn't be read and not even copied aside (another program holds it locked): save()
# doesn't write over it, or the user's vocabulary and settings would be gone for good
readonly = False
READ_TRIES, READ_PAUSE_S = 30, 0.1  # an antivirus or a backup tool holding it locked: wait up to ~3 s


def is_first_run() -> bool:
    return not CONFIG_PATH.exists()


def clean_name(name) -> str:
    """One line, no colon (it ends the message prefix "<name> (hlasem přes Orbit):")."""
    return " ".join(str(name or "").replace(":", " ").split())[:NAME_MAX]


def clean_about(about) -> str:
    return " ".join(str(about or "").split())[:ABOUT_MAX]


def _valid(key: str, value) -> bool:
    """Does a stored value have the shape the code expects? A wrong one (a hand edit, another version) is dropped
    instead of crashing the start or breaking every dictation."""
    if key in ("ptt", "agent_ptt"):
        return isinstance(value, dict) and value.get("kind") in ("key", "mouse") and type(value.get("code")) is int
    if key == "button_pos":
        return value is None or (isinstance(value, list) and len(value) == 2 and all(type(v) is int for v in value))
    if key in ("mic", "learned_until"):
        return value is None or isinstance(value, str)
    if key == "model":
        return isinstance(value, str) and bool(value)
    if key == "usage_source":
        return value in ("statusline", "oauth")
    return isinstance(value, type(DEFAULTS[key]))


def _read() -> dict | None:
    """config.json's content; None when there is none. Raises when it can't be read or isn't a JSON object."""
    for attempt in range(READ_TRIES):
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            break
        except FileNotFoundError:
            return None
        except PermissionError:  # an antivirus or a backup tool has it open for a moment
            if attempt == READ_TRIES - 1:
                raise
            time.sleep(READ_PAUSE_S)
    if not isinstance(data, dict):
        raise ValueError("config.json neobsahuje objekt")
    return data


def load() -> dict:
    global problem, missing, readonly
    problem, missing, readonly = "", set(), False
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        stored = _read()
    except Exception:
        log.exception("Nelze načíst config.json, používám výchozí nastavení")
        # keep a copy: the next save writes the defaults over it (a copy, not a rename: config.json in the app folder
        # is what makes it the data folder, see paths.py)
        backup = CONFIG_PATH.with_name(f"config.json.bad-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            shutil.copy2(CONFIG_PATH, backup)
            problem = f"Nastavení se nedalo načíst, platí výchozí. Původní soubor je tady: {backup}"
        except OSError:
            readonly = True
            log.warning("config.json nejde ani zkopírovat, do restartu Orbitu ho nepřepíšu")
            problem = ("Nastavení se nedalo načíst ani zálohovat (nejspíš ho drží jiný program), platí výchozí. Aby "
                       "se tvoje nastavení nepřepsalo, změny se teď neuloží. Restartuj prosím Orbit.")
        return cfg
    if stored is not None:
        missing = set(DEFAULTS) - set(stored)
    for key, value in (stored or {}).items():
        if key in DEFAULTS and not _valid(key, value):
            log.warning("config.json: neplatná hodnota %s = %r, používám výchozí", key, value)
            continue
        cfg[key] = value
    replacements = vocab.clean_replacements(cfg["replacements"])
    if replacements != cfg["replacements"]:
        log.warning("config.json: vynechávám neplatné nebo zdvojené opravy (%d → %d)", len(cfg["replacements"]),
                    len(replacements))
        cfg["replacements"] = replacements
    cfg["name"], cfg["about"] = clean_name(cfg["name"]), clean_about(cfg["about"])
    return cfg


def save(cfg: dict) -> None:
    """Writes a temporary file and swaps it in, so a crash or a power cut never leaves a half-written config.json.
    Not at all when load() couldn't read it nor keep a copy (readonly)."""
    if readonly:
        log.warning("config.json neukládám: při startu nešel načíst ani zkopírovat")
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_name("config.json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            os.replace(tmp, CONFIG_PATH)
            return
        except PermissionError:  # an antivirus or a backup tool has it open for a moment
            if attempt == 9:
                raise
            time.sleep(0.05)


def available_models() -> list[str]:
    return sorted(p.name for p in MODELS_DIR.glob("ggml-*.bin"))


def model_present(name: str) -> bool:
    return bool(name) and (MODELS_DIR / name).is_file()
