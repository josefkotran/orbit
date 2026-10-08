"""Self-improving vocabulary: Claude (through the local Claude Code CLI) reads recent transcripts from the log and
suggests names/terms for the Whisper prompt and fixes for phrases Whisper keeps getting wrong.

The user's own corrections (editing.py: "Nahraď X za Y" by voice, a corrected text in the dictation history, a
dictation said again right after "Smaž to") are the best evidence there is: they're kept in <data>/corrections.json
and go to Claude with the transcripts.

Only transcript text is sent, never audio.
"""
import ast
import json
import logging
import os
import re
import time
from pathlib import Path

from . import claude_cli, config, vocab
from .config import LOG_PATH

log = logging.getLogger(__name__)

LEARN_EVERY = 10  # new transcripts needed before asking Claude again
CORRECTIONS_EVERY = 3  # or this many new corrections of the user's
MAX_TRANSCRIPTS = 60  # sent per run (the newest ones)
MAX_CORRECTIONS = 200  # kept in corrections.json
SENT_CORRECTIONS = 40  # sent per run (the newest ones)
# where a correction comes from (the weight Claude gives it)
BY_VOICE, IN_HISTORY, REDICTATED = "voice", "history", "redictated"

# "Přepis …: 'text'", optionally followed by the voice command it ended with (" + send")
_LINE_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) INFO \S+: Přepis .*?: ('.*'|\".*\")(?: \+ \w+)?$")

SYSTEM_PROMPT = """\
You help tune a Czech speech-to-text setup (Whisper large-v3, running locally).{speaker} The speaker dictates into \
all kinds of apps, often into AI assistants like Claude Code, so expect software terms, product and company names \
and English words mixed into Czech.

You get recent raw transcripts. Find words and names that Whisper most likely MISRECOGNIZED and that a vocabulary \
list would fix: proper nouns, brand, product and company names, technical terms, English words used in Czech. \
Ignore ordinary grammar and punctuation mistakes and colloquial Czech ("teďka", "takovej", "bysme" are fine as they \
are). Only report cases where the context makes you confident what was meant.

Return:
- words: correctly spelled terms to add to Whisper's vocabulary prompt (e.g. "Claude", "CLAUDE.md", "GitHub"). \
Also include rare proper nouns that were recognized correctly but keep coming up. At most 12, most useful first, \
none that are already in the current vocabulary.
- replacements: an exact wrong phrase as it appears in the transcripts and its correct form. Only when the wrong \
phrase can never be a legitimate phrase in normal Czech ("klod MD" -> "CLAUDE.md" is fine, "cloud" -> "Claude" is \
NOT, because cloud is a real word). Keep "wrong" short (1-3 words) so it matches again next time. None that are \
already in the current replacements.

You may also get corrections: the exact phrase Whisper wrote and what the user meant. "corrected" ones the user \
made deliberately (by voice or by editing the text) are the most reliable evidence there is. "said again" ones come \
from a dictation the user deleted and said again at once: likely, but the second take can be wrong too. A correction \
that fixes how a name or term is spelled belongs in words (and, when the wrong phrase can never be right in normal \
Czech, in replacements too). A correction that swaps one ordinary Czech word for another is the user rewording, not \
a recognition error: ignore it.

Empty lists are a perfectly good answer."""

SCHEMA = {
    "type": "object",
    "properties": {
        "words": {"type": "array", "items": {"type": "string"}},
        "replacements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"wrong": {"type": "string"}, "right": {"type": "string"}},
                "required": ["wrong", "right"],
            },
        },
    },
    "required": ["words", "replacements"],
}


def transcripts_since(since: str | None) -> list[tuple[str, str]]:
    """(timestamp, text) of non-empty transcripts in the log (incl. the rotated one) newer than `since`."""
    found = []
    for path in (Path(f"{LOG_PATH}.1"), LOG_PATH):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            m = _LINE_RE.match(line)
            if not m or (since and m.group(1) <= since):
                continue
            try:
                text = ast.literal_eval(m.group(2))
            except (ValueError, SyntaxError):
                continue
            if text.strip():
                found.append((m.group(1), text))
    return found


def system_prompt(name: str = "", about: str = "") -> str:
    """Who speaks: the name and the "O mně" line from the settings, nothing when they're empty."""
    speaker = f" The speaker's name is {name}." if name else ""
    if about:
        speaker += f' About the speaker, in their own words: "{about}".'
    return SYSTEM_PROMPT.replace("{speaker}", speaker)


def suggest(transcripts: list[str], vocabulary: list[str], replacements: list[list[str]], name: str = "",
            about: str = "", corrections: list[dict] = ()) -> dict:
    """Blocking (tens of seconds): asks Claude for new vocabulary words and replacements."""
    known = ", ".join(vocabulary) or "(empty)"
    fixes = "; ".join(f"{w} -> {r}" for w, r in replacements) or "(none)"
    body = "\n".join(f"- {t}" for t in transcripts[-MAX_TRANSCRIPTS:]) or "(none new)"
    prompt = f"Current vocabulary: {known}\nCurrent replacements: {fixes}\n\nTranscripts:\n{body}"
    if corrections:
        lines = []
        for c in list(corrections)[-SENT_CORRECTIONS:]:
            how = "said again" if c.get("source") == REDICTATED else "corrected"
            context = f' (in: "{c["context"]}")' if c.get("context") else ""
            lines.append(f'- {how}: "{c["wrong"]}" -> "{c["right"]}"{context}')
        prompt += "\n\nCorrections:\n" + "\n".join(lines)
    return claude_cli.ask(prompt, system_prompt(name, about), SCHEMA)


def merge(vocabulary: str, replacements: list[list[str]], suggestion: dict) -> tuple[str, list[list[str]], list[str],
                                                                                        list[list[str]]]:
    """Returns (vocabulary, replacements, added words, added replacements); keeps the vocabulary short enough
    for Whisper's prompt."""
    words = [str(w) for w in suggestion.get("words", [])]
    fixes = []
    for item in suggestion.get("replacements", []):
        if isinstance(item, dict):
            wrong, right = " ".join(str(item.get("wrong", "")).split()), " ".join(str(item.get("right", "")).split())
            if wrong.lower() != right.lower():  # only real fixes, not a change of letter case
                fixes.append([wrong, right])
    merged = vocab.merge(vocabulary, replacements, words, fixes)
    for word in merged.left_out:
        log.info("Slovník je plný, nepřidávám %r", word)
    return merged.vocabulary, merged.replacements, merged.added_words, merged.added_fixes


# --- the user's own corrections --------------------------------------------------------------

def corrections_path() -> Path:
    return config.DATA_DIR / "corrections.json"


def stamp(now: float | None = None) -> str:
    """A time in the log's own format ("2026-10-08 14:03:12,345"), so it compares with learned_until."""
    now = time.time() if now is None else now
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + f",{int(now * 1000) % 1000:03d}"


def load_corrections() -> list[dict]:
    try:
        data = json.loads(corrections_path().read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return []
    except Exception:
        log.exception("Opravy pro učení slovníku nejde načíst")
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    return [c for c in items if isinstance(c, dict) and isinstance(c.get("wrong"), str)
            and isinstance(c.get("right"), str) and isinstance(c.get("at"), str)]


def add_correction(wrong: str, right: str, context: str = "", source: str = BY_VOICE) -> dict | None:
    """Keeps one (what Whisper wrote, what was meant) for the next learning run; None when it's no correction."""
    wrong, right = " ".join(wrong.split()), " ".join(right.split())
    if not wrong or not right or wrong == right:
        return None
    item = {"at": stamp(), "wrong": wrong[:100], "right": right[:100], "context": " ".join(context.split())[:200],
            "source": source}
    items = load_corrections() + [item]
    target = corrections_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name("corrections.json.tmp")
        tmp.write_text(json.dumps({"version": 1, "items": items[-MAX_CORRECTIONS:]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        log.exception("Opravu pro učení slovníku nejde uložit")
        return None
    log.info("Oprava pro učení slovníku (%s): %d → %d znaků", source, len(wrong), len(right))
    return item


def corrections_since(since: str | None) -> list[dict]:
    return [c for c in load_corrections() if not since or c["at"] > since]
