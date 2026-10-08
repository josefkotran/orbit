"""What Orbit typed last, and the voice commands that act on it: "Smaž to", "Vyber to", "Vlož to znovu" (a dictation
of just that), and in edit mode (Ctrl or Shift held with the dictation key) "Nahraď X za Y".

Deleting what was typed is safe only while the cursor is still right after it: in the same window, and with no key
or click of the user's since (Talon's rule for "scratch that"). The hook (hotkey.PushToTalk.on_input) tells when the
user's last key or click came; Orbit's own keys are injected and never count.

Corrections ("Nahraď X za Y", a corrected text in the history) give exact pairs of what Whisper wrote and what was
meant: learning.py keeps them for the vocabulary.

Standard library only: tested without Qt or Windows.
"""
import difflib
import re
import time
import unicodedata
from dataclasses import dataclass, field

MAX_UNDO = 10  # dictations typed one after another that "Smaž to" can take back one by one
MAX_DELETE_CHARS = 10_000  # more is never deleted key by key
# Claude Code collapses a paste of more than 800 characters or more than 3 lines into one "[Pasted text #1]" chip
# (code.claude.com/docs/en/terminal-config). Backspace then takes the whole chip in one go and the rest would eat the
# text before it, so in a terminal only what can't have been collapsed is deleted key by key.
TERMINAL_MAX_CHARS = 800
TERMINAL_MAX_LINES = 3
MAX_CORRECTION_WORDS = 4  # a change of more words than this is rewording, not a recognition error

DELETE, SELECT, PASTE_AGAIN, REPLACE = "delete", "select", "paste_again", "replace"


@dataclass
class Command:
    kind: str  # DELETE / SELECT / PASTE_AGAIN / REPLACE
    wrong: str = ""  # REPLACE: what to look for (as heard)
    right: str = ""  # REPLACE: what to put there
    candidates: list[tuple[str, str]] = field(default_factory=list)  # REPLACE: every way the words can be split


def _plain(text: str) -> str:
    """Lower case, without punctuation and with single spaces: how a command is recognized."""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


_DELETE_RE = re.compile(r"^(?:smaž|smaš|smažte|smazat|vymaž|vymaš|vymazat|odstraň|odstranit|vyškrtni|vyškrtnout)"
                        r"(?: to| tohle| ten text| poslední diktát| to poslední)$")
_SELECT_RE = re.compile(r"^(?:vyber|vybrat|označ|označit)(?: to| tohle| ten text| poslední diktát| to poslední)$")
_PASTE_RE = re.compile(r"^(?:vlož|vložit|vlož mi)(?: to)? (?:znovu|ještě jednou|ještě jednou znovu|poslední diktát)$")
# "Nahraď comgit za Comgate", "oprav komgit na Comgate", "místo komgit napiš Comgate"
_REPLACE_RE = re.compile(r"^\s*(?:nahraď|nahraďte|nahradit|oprav|opravte|opravit|přepiš|přepsat|změň|změnit)\s+(.+)$",
                         re.IGNORECASE | re.DOTALL)
_INSTEAD_RE = re.compile(r"^\s*místo\s+(.+?)\s+(?:napiš|piš|dej|má být|bude)\s+(.+)$", re.IGNORECASE | re.DOTALL)
_SPLIT_RE = re.compile(r"\s+(?:za|na|slovem|výrazem|textem)\s+", re.IGNORECASE)
_QUOTES = "\"'„“”‚‘’»«"


def _trim(part: str) -> str:
    """One side of "nahraď X za Y" as spoken: without the sentence's punctuation and quotes around it."""
    return part.strip().strip(_QUOTES).strip().rstrip(".!?…,;:").strip().strip(_QUOTES).strip()


def command(text: str, edit: bool = False) -> Command | None:
    """The command a whole dictation is, or None (it's text). REPLACE only in edit mode: "Oprav to na…" or
    "Nahraď import za…" is just as likely a prompt for Claude Code."""
    plain = _plain(text)
    if _DELETE_RE.match(plain):
        return Command(DELETE)
    if _SELECT_RE.match(plain):
        return Command(SELECT)
    if _PASTE_RE.match(plain):
        return Command(PASTE_AGAIN)
    if not edit:
        return None
    if m := _INSTEAD_RE.match(text):
        wrong, right = _trim(m.group(1)), _trim(m.group(2))
        return Command(REPLACE, wrong, right, [(wrong, right)]) if wrong and right else None
    if m := _REPLACE_RE.match(text):
        rest = m.group(1)
        candidates = []
        for sep in _SPLIT_RE.finditer(rest):  # "nahraď na trh za na trhu": every split, the text decides
            wrong, right = _trim(rest[:sep.start()]), _trim(rest[sep.end():])
            if wrong and right:
                candidates.append((wrong, right))
        if candidates:
            return Command(REPLACE, *candidates[0], candidates)
    return None


# --- finding what was meant in the text ----------------------------------------------------

_WORD_RE = re.compile(r"\w+(?:[-'’.]\w+)*")


def _fold(word: str) -> str:
    """Lower case without diacritics: "Comgit" ~ "komgit" is left to the similarity, "dalsi" = "další" here."""
    decomposed = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def find(text: str, phrase: str, threshold: float = 0.75) -> list[tuple[int, int]]:
    """Where `phrase` (as heard: Whisper may have spelled it the same wrong way again, or right) is in `text`:
    (start, end) spans of whole words, in order. The words that match best, every time they're there (a word
    misheard once is usually misheard the same way each time). [] when nothing is close enough."""
    words = [(m.start(), m.end(), _fold(m.group())) for m in _WORD_RE.finditer(text)]
    target = " ".join(_fold(w) for w in _WORD_RE.findall(phrase))
    if not words or not target:
        return []
    n = len(target.split())
    scored = []  # (score, words as folded, start, end)
    for size in {max(1, n - 1), n, n + 1}:
        for i in range(len(words) - size + 1):
            window = words[i:i + size]
            joined = " ".join(w for _, _, w in window)
            score = 1.0 if joined == target else difflib.SequenceMatcher(None, joined, target).ratio()
            if score >= threshold:
                scored.append((score, joined, window[0][0], window[-1][1]))
    if not scored:
        return []
    best = max(s for s, _, _, _ in scored)
    # of equally good ones the one closest to the cursor (the end, where the user looked); then all like it
    _, chosen, _, _ = max((c for c in scored if c[0] == best), key=lambda c: (c[2], c[2] - c[3]))
    return _disjoint(sorted((a, b) for s, joined, a, b in scored if joined == chosen))


def _disjoint(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = []
    for a, b in spans:
        if not out or a >= out[-1][1]:
            out.append((a, b))
    return out


def replace(text: str, cmd: Command) -> tuple[str, str, str] | None:
    """(new text, the words as they were in the text, what they became) for "Nahraď X za Y", or None when none of
    its readings matches anything in the text."""
    for wrong, right in cmd.candidates or [(cmd.wrong, cmd.right)]:
        spans = find(text, wrong)
        if not spans:
            continue
        found = text[spans[0][0]:spans[0][1]]
        out, last = [], 0
        for a, b in spans:
            out.append(text[last:a])
            out.append(_match_case(right, text[a:b], text, a))
            last = b
        out.append(text[last:])
        return "".join(out), found, _match_case(right, found, text, spans[0][0])
    return None


def _match_case(new: str, old: str, text: str, at: int) -> str:
    """A word that started a sentence keeps its capital letter ("Komgit funguje" -> "Comgate funguje")."""
    starts_sentence = at == 0 or bool(re.search(r"[.!?…]\s*$|\n\s*$", text[:at]))
    if old[:1].isupper() and new[:1].islower() and starts_sentence:
        return new[:1].upper() + new[1:]
    return new


# --- what a correction says about the recognition ----------------------------------------

def word_changes(old: str, new: str, max_words: int = MAX_CORRECTION_WORDS) -> list[tuple[str, str]]:
    """The small changes between what Whisper wrote and what the user made of it, as (wrong, right) phrases of whole
    words. Changes of punctuation only, longer rewordings and plain additions or deletions aren't recognition errors
    and are left out."""
    a, b = _WORD_RE.findall(old), _WORD_RE.findall(new)
    pairs = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [w.lower() for w in a], [w.lower() for w in b],
                                                      autojunk=False).get_opcodes():
        if op == "equal":
            # a change of letter case only ("claude" -> "Claude") is a spelling the vocabulary should know
            for wa, wb in zip(a[i1:i2], b[j1:j2]):
                if wa != wb:
                    pairs.append((wa, wb))
            continue
        if op != "replace" or i2 - i1 > max_words or j2 - j1 > max_words:
            continue
        pairs.append((" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return [(w, r) for w, r in pairs if w != r]


def similar(a: str, b: str) -> float:
    """How alike two texts are, by words (0..1)."""
    wa, wb = [_fold(w) for w in _WORD_RE.findall(a)], [_fold(w) for w in _WORD_RE.findall(b)]
    if not wa or not wb:
        return 0.0
    return difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio()


# --- keystrokes -----------------------------------------------------------------------------

def keystrokes(text: str) -> int:
    """How many Backspaces (or Shift+Left) cover the text: one per character as an editor counts them; a combining
    mark, a variation selector or what a zero-width joiner glues on belongs to the character before it."""
    count, glued = 0, False
    for ch in text:
        if unicodedata.combining(ch) or ch in "︎️":
            continue
        if ch == "‍":
            glued = True
            continue
        if glued:
            glued = False
            continue
        count += 1
    return count


def terminal_safe(text: str) -> bool:
    """Short enough that Claude Code can't have collapsed it into one chip (see TERMINAL_MAX_CHARS)."""
    return len(text) <= TERMINAL_MAX_CHARS and text.count("\n") < TERMINAL_MAX_LINES


# --- what Orbit typed last --------------------------------------------------------------------

@dataclass
class Typed:
    text: str
    window: int  # where it went (its top-level window)
    at: float  # time.monotonic() when it was typed
    terminal: bool = False  # into a terminal (a console window or Windows Terminal)
    selected: bool = False  # "Vyber to" selected it
    entry: str = ""  # its history entry (history.Entry.id)


class Trail:
    """The dictations typed in a row into one place with nothing of the user's between them: "Smaž to" takes them
    back one by one, the newest first. A key or click of the user's (last_input, set from the hook thread) ends it:
    the cursor may be anywhere then."""

    def __init__(self):
        self.items: list[Typed] = []
        self.last_input = 0.0  # time.monotonic() of the user's last key or click (not Orbit's own)
        self.deleted: Typed | None = None  # what "Smaž to" took last (a dictation right after it may correct it)
        self.deleted_at = 0.0

    def input_seen(self, now: float | None = None) -> None:
        self.last_input = time.monotonic() if now is None else now

    def check(self, window: int, same_window) -> tuple[Typed | None, str]:
        """(the newest typed text, "") while it's safe to act on: the same window in front and no input since.
        Else (None, why): "empty" (nothing typed, or sent with Enter), "input" (a key or click since: the trail is
        over), "window" (another window is in front: it may come back). same_window(a, b): inserter.same_window."""
        if not self.items:
            return None, "empty"
        top = self.items[-1]
        if self.last_input > top.at:
            self.items.clear()
            return None, "input"
        if not same_window(top.window, window):
            return None, "window"
        return top, ""

    def push(self, typed: Typed, same_window) -> None:
        """A new text typed: on top of the ones before it when nothing happened in between, else on its own."""
        if self.items:
            prev = self.items[-1]
            if self.last_input > prev.at or not same_window(prev.window, typed.window):
                self.items.clear()
            elif prev.selected:  # typing replaced the selection
                self.items.pop()
        self.items.append(typed)
        del self.items[:-MAX_UNDO]

    def pop(self) -> Typed | None:
        typed = self.items.pop() if self.items else None
        if typed:
            self.deleted, self.deleted_at = typed, time.monotonic()
        return typed

    def clear(self) -> None:
        self.items.clear()
