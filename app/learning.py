"""Self-improving vocabulary: Claude (through the local Claude Code CLI) reads recent transcripts from the log and
suggests names/terms for the Whisper prompt and fixes for phrases Whisper keeps getting wrong.

Only transcript text is sent, never audio. The CLI runs headless in safe mode, without tools and without saving
the session, so it can't touch anything and doesn't clutter Pepa's Claude Code history.
"""
import ast
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from .config import LOG_PATH, ROOT

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


class LearningError(Exception):
    pass


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


def _claude_exe() -> str:
    npm = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    exe = npm if npm.exists() else shutil.which("claude.exe") or shutil.which("claude")
    if not exe:
        raise LearningError("Claude Code (claude.exe) nebyl nalezen.")
    return str(exe)


def suggest(transcripts: list[str], vocabulary: list[str], replacements: list[list[str]]) -> dict:
    """Blocking (tens of seconds): asks Claude for new vocabulary words and replacements."""
    known = ", ".join(vocabulary) or "(empty)"
    fixes = "; ".join(f"{w} -> {r}" for w, r in replacements) or "(none)"
    body = "\n".join(f"- {t}" for t in transcripts[-MAX_TRANSCRIPTS:])
    prompt = f"Current vocabulary: {known}\nCurrent replacements: {fixes}\n\nTranscripts:\n{body}"
    cmd = [_claude_exe(), "-p", "--safe-mode", "--model", "sonnet", "--tools", "", "--no-session-persistence",
           "--output-format", "json", "--json-schema", json.dumps(SCHEMA), "--system-prompt", SYSTEM_PROMPT]
    # Without ANTHROPIC_API_KEY the CLI uses the Claude subscription login (Pepa's key has no credit), and without
    # the CLAUDE* variables it doesn't think it runs inside another Claude Code session (when started from one).
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY" and not k.startswith("CLAUDE")}
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=300,
                              cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise LearningError("Claude neodpověděl do 5 minut.")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise LearningError(f"Claude Code skončil s kódem {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
    if result.get("is_error") or not isinstance(result.get("structured_output"), dict):
        raise LearningError(f"Claude Code vrátil chybu: {str(result.get('result'))[:300]}")
    return result["structured_output"]


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
