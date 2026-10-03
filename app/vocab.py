"""The vocabulary (words Whisper should spell exactly so) and the replacements (fixes for phrases it keeps getting
wrong): cleaning, merging, and moving them to another PC.

Export file (orbit-slovnik.json):
    {"app": "Orbit", "kind": "vocabulary", "version": 1, "vocabulary": "Claude, GitHub",
     "replacements": [["comgit", "Comgate"]]}
Import also takes a plain text file: one word (or phrase) per line, or comma separated; a line "špatně → správně"
is a replacement, as in the settings.

Standard library only (no Qt): used by config.py, learning.py and the settings dialog.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_CHARS = 300  # Whisper keeps only ~224 prompt tokens and drops the start of the prompt first
DEFAULT_NAME = "orbit-slovnik.json"
FILE_KIND = "vocabulary"
FILE_VERSION = 1
MAX_FILE_BYTES = 1_000_000


class VocabError(Exception):
    """A file that isn't a vocabulary Orbit can read; the message is for the user (Czech)."""


def _one_line(text) -> str:
    return " ".join(str(text).split())


def parse_words(vocabulary: str) -> list[str]:
    return [w.strip() for w in re.split(r"[,;\n]", vocabulary) if w.strip()]


def join_words(words: list[str]) -> str:
    return ", ".join(words)


def clean_replacements(items) -> list[list[str]]:
    """Only [wrong, right] pairs of non-empty strings with wrong != right, one per wrong phrase (any letter case).
    A bad entry would break every dictation, an empty "wrong" would garble the text."""
    pairs, seen = [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, (list, tuple)) or len(item) != 2 or not all(isinstance(s, str) for s in item):
            continue
        wrong, right = _one_line(item[0]), _one_line(item[1])
        if not wrong or not right or wrong == right or wrong.lower() in seen:
            continue
        seen.add(wrong.lower())
        pairs.append([wrong, right])
    return pairs


def parse_replacement_lines(text: str) -> list[list[str]]:
    """The settings' "Opravy" field: one fix per line, "špatně → správně" (or ->)."""
    pairs = []
    for line in text.splitlines():
        wrong, sep, right = line.replace("->", "→").partition("→")
        if sep and wrong.strip() and right.strip():
            pairs.append([wrong.strip(), right.strip()])
    return pairs


@dataclass
class Merged:
    vocabulary: str
    replacements: list[list[str]]
    added_words: list[str] = field(default_factory=list)
    left_out: list[str] = field(default_factory=list)  # didn't fit under MAX_CHARS
    added_fixes: list[list[str]] = field(default_factory=list)


def merge(vocabulary: str, replacements: list[list[str]], words: list[str], fixes: list[list[str]],
          replace: bool = False) -> Merged:
    """Adds `words` and `fixes` (or, with `replace`, uses only them). Words already there (any letter case) and fixes
    for a wrong phrase that already has one are skipped; words that would push the vocabulary over MAX_CHARS are
    left out (and listed, so the user can be told)."""
    kept = [] if replace else parse_words(vocabulary)
    known = {w.lower() for w in kept}
    result = Merged(join_words(kept), [] if replace else clean_replacements(replacements))
    for word in words:
        word = _one_line(word).strip(",;")
        if not word or word.lower() in known:
            continue
        known.add(word.lower())
        if len(join_words(kept + [word])) > MAX_CHARS:
            result.left_out.append(word)
            continue
        kept.append(word)
        result.added_words.append(word)
    result.vocabulary = join_words(kept)
    wrongs = {w.lower() for w, _ in result.replacements}
    for wrong, right in clean_replacements(fixes):
        if wrong.lower() not in wrongs:
            wrongs.add(wrong.lower())
            result.replacements.append([wrong, right])
            result.added_fixes.append([wrong, right])
    return result


# --- moving it to another PC ---------------------------------------------------------------

def export(path: str | Path, vocabulary: str, replacements: list[list[str]]) -> None:
    data = {"app": "Orbit", "kind": FILE_KIND, "version": FILE_VERSION, "vocabulary": join_words(parse_words(vocabulary)),
            "replacements": clean_replacements(replacements)}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path: str | Path) -> tuple[list[str], list[list[str]]]:
    """(words, replacements) from an exported file or a plain list of words. Raises VocabError."""
    p = Path(path)
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            raise VocabError("Soubor je moc velký, slovník to nebude.")
        raw = p.read_bytes()
    except OSError as e:
        raise VocabError(f"Soubor nejde přečíst: {e.strerror or e}")
    text = _decode(raw)
    if p.suffix.lower() == ".json" or text.lstrip().startswith("{"):
        return _read_json(text)
    words, fixes = [], []
    for line in text.splitlines():
        if "→" in line or "->" in line:
            fixes += parse_replacement_lines(line)
        else:
            words += parse_words(line)
    if not words and not fixes:
        raise VocabError("V souboru nejsou žádná slova.")
    return words, clean_replacements(fixes)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return raw.decode("mbcs")  # an older Notepad saves in the Windows code page
        except (UnicodeDecodeError, LookupError):
            raise VocabError("Soubor není textový, nebo je v neznámém kódování.")


def _read_json(text: str) -> tuple[list[str], list[list[str]]]:
    try:
        data = json.loads(text)
    except ValueError:
        raise VocabError("Soubor je poškozený (není to platný JSON).")
    if not isinstance(data, dict) or data.get("app") != "Orbit" or data.get("kind") != FILE_KIND:
        raise VocabError("Tohle není slovník z Orbitu. Vyber soubor, který Orbit vyexportoval.")
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        raise VocabError("Slovník je poškozený (chybí verze).")
    if version > FILE_VERSION:
        raise VocabError("Slovník je z novější verze Orbitu. Aktualizuj Orbit a zkus to znovu.")
    vocabulary, replacements = data.get("vocabulary", ""), data.get("replacements", [])
    if isinstance(vocabulary, list) and all(isinstance(w, str) for w in vocabulary):
        vocabulary = join_words(vocabulary)
    if not isinstance(vocabulary, str):
        raise VocabError("Slovník je poškozený (slova nejsou text).")
    if not isinstance(replacements, list):
        raise VocabError("Slovník je poškozený (opravy nejsou seznam).")
    for i, item in enumerate(replacements, 1):
        if not isinstance(item, list) or len(item) != 2 or not all(isinstance(s, str) for s in item):
            raise VocabError(f"Slovník je poškozený (oprava č. {i} nemá tvar [špatně, správně]).")
    return parse_words(vocabulary), clean_replacements(replacements)


def describe(merged: Merged, replaced: bool = False) -> str:
    """What an import did, for the user."""
    parts = []
    if merged.added_words:
        parts.append(plural(len(merged.added_words), "slovo", "slova", "slov"))
    if merged.added_fixes:
        parts.append(plural(len(merged.added_fixes), "oprava", "opravy", "oprav"))
    if replaced:
        text = f"Slovník je nahrazený: {' a '.join(parts) or 'nic v něm není'}."
    else:
        text = f"Přidáno: {' a '.join(parts)}." if parts else "Nic nového, všechno už ve slovníku je."
    if merged.left_out:
        text += (f" Do slovníku se nevešlo (má limit {MAX_CHARS} znaků): {', '.join(merged.left_out)}. "
                 "Uvolni místo a zkus to znovu.")
    return text


def plural(n: int, one: str, few: str, many: str) -> str:
    """'1 slovo', '3 slova', '5 slov'."""
    return f"{n} {one if n == 1 else few if 2 <= n <= 4 else many}"
