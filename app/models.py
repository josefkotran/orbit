"""Claude Code's models for Orbit's sessions: which one a new session starts with (the + above the panel, the session
history's "Pokračovat v relaci": claude --model <alias>), and switching a running session to another one (a right
click on it in the panel). Shown by their exact names ("Sonnet 5.5"): which model an alias stands for Claude Code says
itself (refresh_names: its answer to initialize, the SDK's supportedModels), once per its version.

A running session switches through Claude Code's own /model, run in it by the orbit-mozek mod (0.5.0+): Orbit leaves
<data>/sessions/model/<session>.<id>.json ({"session_id", "id", "time", "model", "default"}), the mod answers
<session>.<id>.ack.json when it took it and <session>.<id>.done.json ({"ok", "text", "model"}) when /model is through.
Two things /model does that Orbit undoes (Claude Code 2.1.301, seen in its code and tried on a real session 16 Oct):
- In a session that has answered before it asks in its window whether to switch ("Switch model? … the full history
  gets re-read"). Orbit's PreModelSwitch hook (cc_hook.py, the only one that isn't async) says allow, but only to a
  switch Orbit asked for in that session, to that model, within ASK_FRESH_S: the user chose it in Orbit's menu, whose
  tooltip says what it costs.
- It also saves the model as the default for new sessions (settings.json "model"; /model locally always does). Orbit
  puts the default back as soon as the mod answers (restore_default). Running sessions don't follow that key (tried:
  one kept Opus while the default was Sonnet for 40 s), only sessions started meanwhile would.

No Qt."""
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path

from . import paths
from .config import CACHE_DIR, SESSIONS_DIR

log = logging.getLogger(__name__)

SWITCH_DIR = SESSIONS_DIR / "model"
ASK_FRESH_S = 600  # the hook lets Orbit's switch through this long (a busy session runs /model after its turn)
ACK_WAIT_S = 7  # no ack by then: the session has no orbit-mozek 0.5 (started before it, or without mods)
CONFIRM_WAIT_S = 5  # taken, idle and still not through by then: it asks in its window (no Orbit hook there)
# the order of the menus, cheapest last; what each one is for, in the words Claude Code's picker uses
FAMILIES = ("fable", "opus", "sonnet", "haiku")
NAMES = {"fable": "Fable", "opus": "Opus", "sonnet": "Sonnet", "haiku": "Haiku", "mythos": "Mythos"}
ABOUT = {
    "fable": "Nejschopnější, na nejtěžší a dlouhé úkoly. Limity čerpá nejrychleji.",
    "opus": "Silný na většinu práce.",
    "sonnet": "Rychlejší a k limitům šetrnější, na běžnou práci.",
    "haiku": "Nejrychlejší a nejúspornější, na jednoduché věci.",
}
_ALIAS_RE = re.compile(r"(fable|opus|sonnet|haiku)(\[1m\])?", re.IGNORECASE)
_ID_RE = re.compile(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?(\[1m\])?", re.IGNORECASE)


def family(model: str | None) -> str:
    """"opus" for opus, opus[1m], opusplan, claude-opus-5-5[1m], "Opus 5.5 (1M context)"; "" when it isn't known."""
    text = str(model or "").lower()
    if text.strip() == "best":
        return "fable"  # Claude Code's "best" is Fable now
    found = [(text.find(f), f) for f in (*FAMILIES, "mythos") if f in text]
    return min(found)[1] if found else ""


def label(model: str | None) -> str:
    """How Orbit names it: "Opus 5.5" (claude-opus-5-5[1m], "Opus 5.5 (1M context)", and an alias once Claude Code
    said which model it means: name), "Sonnet" (an alias before that), ""."""
    text = str(model or "").strip()
    if not text or text.startswith("<"):  # "<synthetic>": Claude Code's own message, no model answered
        return ""
    if is_alias(text):
        return name(family(text))
    if m := _ID_RE.fullmatch(text):
        called = NAMES.get(m.group(1).lower(), m.group(1).capitalize())
        return f"{called} {m.group(2)}" + (f".{m.group(3)}" if m.group(3) else "")
    if m := re.match(r"(Fable|Opus|Sonnet|Haiku|Mythos)\s+(\d+(?:\.\d+)?)", text, re.IGNORECASE):
        return f"{NAMES.get(m.group(1).lower(), m.group(1))} {m.group(2)}"
    called = NAMES.get(family(text), "")
    return f"{called} (plán)" if called and "plan" in text.lower() else called or text[:40]


def name(family_: str) -> str:
    """The exact name of the model a family's alias stands for now ("Sonnet 5.5"), as Claude Code itself names it
    (refresh_names); only the family's name ("Sonnet") until Orbit has asked."""
    entry = _load_catalog().get(family_)
    return entry["name"] if isinstance(entry, dict) and isinstance(entry.get("name"), str) else NAMES.get(family_, "")


# --- which model each alias stands for (Claude Code's own list, cached per Claude Code version) ---------------------

CATALOG_PATH = CACHE_DIR / "models.json"
_NAME_RE = re.compile(r"(Fable|Opus|Sonnet|Haiku|Mythos) \d{1,2}(?:\.\d{1,2})?")
_catalog: dict | None = None  # family -> {"id": "claude-sonnet-5-5", "name": "Sonnet 5.5"}


def _load_catalog() -> dict:
    global _catalog
    if _catalog is None:
        try:
            record = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            _catalog = record.get("models") if isinstance(record, dict) and isinstance(record.get("models"), dict) \
                else {}
        except (OSError, ValueError):
            _catalog = {}
    return _catalog


def parse_catalog(answer: dict) -> dict:
    """Claude Code's answer to initialize (its "models", what the SDK's supportedModels gives) → family -> {"id",
    "name"}, only the four aliases Orbit offers and only names that look like a model's ("Sonnet 5.5")."""
    found = {}
    for entry in answer.get("models") or []:
        if not isinstance(entry, dict) or entry.get("value") not in FAMILIES:
            continue
        shown, resolved = entry.get("displayName"), entry.get("resolvedModel")
        if isinstance(shown, str) and _NAME_RE.fullmatch(shown) and family(shown) == entry["value"]:
            found[entry["value"]] = {"id": resolved if isinstance(resolved, str) else "", "name": shown}
    return found


def _ask_claude(exe: str, timeout: float = 20) -> dict:
    """Claude Code's answer to initialize (stream-json, like the voice agent's): nothing is sent to a model, no session
    is kept; ~0.8 s."""
    from .claude_setup import environment
    proc = subprocess.Popen([exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                             "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence", "--tools", ""],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=environment(), creationflags=subprocess.CREATE_NO_WINDOW)
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        proc.stdin.write(b'{"type":"control_request","request_id":"orbit-models",'
                         b'"request":{"subtype":"initialize"}}\n')
        proc.stdin.flush()
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            response = event.get("response")
            if event.get("type") == "control_response" and isinstance(response, dict) \
                    and response.get("request_id") == "orbit-models":
                answer = response.get("response")
                return answer if isinstance(answer, dict) else {}
        return {}
    finally:
        timer.cancel()
        proc.kill()


def refresh_names(exe: str, version: str) -> bool:
    """Asks Claude Code which model each alias stands for, once per its version (the answer is kept in Orbit's cache
    folder, the + and the sessions' process read it there). Blocking (a worker thread). True when the names changed."""
    global _catalog
    try:
        record = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        if record.get("version") == version and record.get("exe") == exe and record.get("models"):
            return False
    except (OSError, ValueError, AttributeError):
        pass
    try:
        found = parse_catalog(_ask_claude(exe))
    except (OSError, ValueError) as e:
        log.warning("Názvy modelů od Claude Code nejdou zjistit: %s", e)
        return False
    if not found:
        log.info("Claude Code názvy modelů neřekl")
        return False
    changed = found != _load_catalog()
    try:
        CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CATALOG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"exe": exe, "version": version, "models": found}, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, CATALOG_PATH)
    except OSError as e:
        log.warning("Názvy modelů nejde uložit: %s", e)
    _catalog = found
    log.info("Modely Claude Code %s: %s", version, ", ".join(e["name"] for e in found.values()))
    return changed


_default_cache: tuple[float, str] = (0.0, "")


def default() -> str:
    """Claude Code's default model for new sessions: "model" in the user's settings.json ("opus[1m]"), "" = none
    set there (Claude Code decides). Read again only after the file changed."""
    global _default_cache
    path = paths.claude_dir() / "settings.json"
    try:
        mtime = path.stat().st_mtime
        if mtime != _default_cache[0]:
            settings = json.loads(path.read_text(encoding="utf-8-sig"))
            value = settings.get("model") if isinstance(settings, dict) else None
            _default_cache = (mtime, value if isinstance(value, str) else "")
    except (OSError, ValueError):
        pass  # being written right now (or not there): the last one read stands
    return _default_cache[1]


def alias(chosen: str, current_default: str | None = None) -> str:
    """What --model or /model gets for a family: the default itself when it's that family ("opus[1m]" stays so),
    else the family's alias, the newest model of it."""
    current_default = default() if current_default is None else current_default
    return current_default if family(current_default) == chosen and is_alias(current_default) else chosen


def is_alias(model: str) -> bool:
    """One of the aliases Orbit hands to Claude Code (never anything else on a command line or in a request)."""
    return bool(_ALIAS_RE.fullmatch(model or ""))


def launch_model(chosen: str) -> str:
    """--model for a new session when the user picked `chosen` ("" = nothing picked): "" when that's the default
    anyway, so the session starts exactly as one from the Explorer would."""
    if chosen not in FAMILIES or family(default()) == chosen:
        return ""
    return alias(chosen)


# --- switching a running session (the orbit-mozek mod runs /model in it) ---------------------------------------

def ask(session_id: str, model: str, pending: dict | None = None) -> str:
    """Leaves the request for the session's mod; its id. pending: the request of another switch not through yet,
    whose /model may have saved its model as the default already: the default to put back is the one it found."""
    if not re.fullmatch(r"[\w-]{1,128}", session_id) or not is_alias(model):
        raise ValueError(f"neplatná relace nebo model: {session_id!r} {model!r}")
    request_id = secrets.token_hex(6)
    SWITCH_DIR.mkdir(parents=True, exist_ok=True)
    record = {"session_id": session_id, "id": request_id, "time": time.time(), "model": model,
              "default": pending.get("default") if pending and "default" in pending else _settings_model()}
    tmp = SWITCH_DIR / f"{session_id}.{request_id}.tmp"
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp, SWITCH_DIR / f"{session_id}.{request_id}.json")
    return request_id


def _settings_model() -> str | None:
    """settings.json's "model" right now, None when it has none (then it's removed again)."""
    try:
        settings = json.loads((paths.claude_dir() / "settings.json").read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return default() or None
    value = settings.get("model") if isinstance(settings, dict) else None
    return value if isinstance(value, str) else None


def _read(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # not there, or the mod is writing it
    return record if isinstance(record, dict) else None


def request(session_id: str, request_id: str) -> dict | None:
    return _read(SWITCH_DIR / f"{session_id}.{request_id}.json")


def acked(session_id: str, request_id: str) -> bool:
    return (SWITCH_DIR / f"{session_id}.{request_id}.ack.json").exists()


def answer(session_id: str, request_id: str) -> dict | None:
    """The mod's {"ok", "text", "model"} once /model is through, else None."""
    return _read(SWITCH_DIR / f"{session_id}.{request_id}.done.json")


def forget(session_id: str, request_id: str) -> None:
    for suffix in ("json", "ack.json", "done.json"):
        (SWITCH_DIR / f"{session_id}.{request_id}.{suffix}").unlink(missing_ok=True)


def restore_default(record: dict) -> bool:
    """/model saved the session's model as the default for new sessions: back to what it was before Orbit asked.
    Only when it's still the switched-to model (a default the user set meanwhile stays). True if it changed it."""
    from . import claude_settings  # (it imports config's paths too; not needed by the rest of this module)
    model, before = str(record.get("model") or ""), record.get("default")
    if not model or (before is not None and not isinstance(before, str)) or before == model:
        return False
    now = _settings_model()
    if now is None or now.lower() != model.lower():
        return False
    for attempt in range(5):  # Claude Code may hold the file for a moment while it writes it
        try:
            changed = claude_settings.set_default_model(before)
            log.info("Výchozí model pro nové relace vrácen na %s", before or "(žádný)")
            return changed
        except claude_settings.SettingsError as e:
            if attempt == 4:
                log.warning("Výchozí model pro nové relace nejde vrátit: %s", e)
                return False
            time.sleep(0.1)
    return False


def leftovers() -> list[dict]:
    """Requests left behind by an Orbit that ended before the mod answered (restore_default is due once they're
    through): their records, the mod's answer as "done" when there is one."""
    found = []
    try:
        files = list(SWITCH_DIR.glob("*.json"))
    except OSError:
        return found
    for f in files:
        parts = f.name.split(".")
        if len(parts) != 3:
            continue  # .ack / .done
        record = _read(f)
        if record and record.get("session_id") == parts[0] and record.get("id") == parts[1]:
            found.append(dict(record, done=answer(parts[0], parts[1])))
    return found
