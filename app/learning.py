"""Self-improving vocabulary: Claude (through the local Claude Code CLI) reads recent transcripts from the log and
suggests names/terms for the Whisper prompt and fixes for phrases Whisper keeps getting wrong.

Only transcript text is sent, never audio.
"""
import ast
import logging
import re
from pathlib import Path

from . import claude_cli
from .config import LOG_PATH

log = logging.getLogger(__name__)

LEARN_EVERY = 10  # new transcripts needed before asking Claude again
MAX_TRANSCRIPTS = 60  # sent per run (the newest ones)
VOCABULARY_MAX_CHARS = 300  # Whisper keeps only ~224 prompt tokens and drops the start of the prompt first

_LINE_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) INFO \S+: Přepis .*?: ('.*'|\".*\")$")

SYSTEM_PROMPT = """\
You help tune a Czech speech-to-text setup (Whisper large-v3, running locally). The speaker is Josef, who works for \
HHW Hommel Hercules (professional tools) and M-tex (home textiles e-shop). He mostly dictates into Claude Code \
(an AI coding assistant), so he talks about software, e-shops, orders, products, Claude and AI tools, \
often mixing in English words.

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


def parse_words(vocabulary: str) -> list[str]:
    return [w.strip() for w in re.split(r"[,;\n]", vocabulary) if w.strip()]


def suggest(transcripts: list[str], vocabulary: list[str], replacements: list[list[str]]) -> dict:
    """Blocking (tens of seconds): asks Claude for new vocabulary words and replacements."""
    known = ", ".join(vocabulary) or "(empty)"
    fixes = "; ".join(f"{w} -> {r}" for w, r in replacements) or "(none)"
    body = "\n".join(f"- {t}" for t in transcripts[-MAX_TRANSCRIPTS:])
    prompt = f"Current vocabulary: {known}\nCurrent replacements: {fixes}\n\nTranscripts:\n{body}"
    return claude_cli.ask(prompt, SYSTEM_PROMPT, SCHEMA)


def merge(vocabulary: str, replacements: list[list[str]], suggestion: dict) -> tuple[str, list[list[str]], list[str],
                                                                                        list[list[str]]]:
    """Returns (vocabulary, replacements, added words, added replacements); keeps the vocabulary short enough
    for Whisper's prompt."""
    words = parse_words(vocabulary)
    known = {w.lower() for w in words}
    added_words = []
    for word in suggestion.get("words", []):
        word = " ".join(str(word).split()).strip(",;")
        if not word or word.lower() in known:
            continue
        if len(", ".join(words + [word])) > VOCABULARY_MAX_CHARS:
            log.info("Slovník je plný, nepřidávám %r", word)
            continue
        words.append(word)
        known.add(word.lower())
        added_words.append(word)
    wrongs = {w.lower() for w, _ in replacements}
    added_fixes = []
    for item in suggestion.get("replacements", []):
        wrong, right = " ".join(str(item.get("wrong", "")).split()), " ".join(str(item.get("right", "")).split())
        if not wrong or not right or wrong.lower() == right.lower() or wrong.lower() in wrongs:
            continue
        added_fixes.append([wrong, right])
        wrongs.add(wrong.lower())
    return ", ".join(words), replacements + added_fixes, added_words, added_fixes
