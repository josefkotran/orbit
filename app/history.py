"""Dictation history: the last dictations with where they went, so a text that ended up on the clipboard (the window
changed, a window running as administrator) or one from a while ago can be inserted again, copied or corrected, and
"Vlož to znovu" has something to insert. The window is historyview.py.

Stored in <data>/history.json (local only, written atomically, never in git: it's what the user said). With
"keep_history" off nothing is written and the file is deleted; the last dictation is still kept in memory for
"Vlož to znovu". The recording itself (recordings/<stem>.wav) only exists with keep_recordings on. No Qt here."""
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

MAX_ITEMS = 200

# where a dictation's text went
INSERTED = "inserted"  # typed into the window it was meant for
CLIPBOARD = "clipboard"  # that window changed or wouldn't take it: on the clipboard
FAILED = "failed"  # the transcription failed (its recording may still be there)


@dataclass
class Entry:
    id: str
    at: float  # epoch seconds
    text: str  # what was inserted (after the replacements and the voice commands)
    raw: str = ""  # what Whisper wrote
    app: str = ""  # the program it went to ("chrome", "WindowsTerminal")
    outcome: str = INSERTED
    seconds: float = 0.0  # length of the recording
    recording: str = ""  # its file's stem in recordings/ ("" = not kept)
    instruction: str = ""  # an edit by voice: what the user asked for (text is then the result)
    original: str = ""  # an edit by voice: the text before it
    corrected: str = ""  # the user's own correction of the text (the history window)
    key: str = ""  # "send" / "stop": "Odešli" or "Stop" followed it

    @property
    def best(self) -> str:
        """The text to insert again: the user's correction, if there is one."""
        return self.corrected or self.text


def path() -> Path:
    return config.DATA_DIR / "history.json"


class History:
    def __init__(self, persist: bool = True):
        self.persist = persist
        self.items: list[Entry] = self._load() if persist else []  # oldest first

    @staticmethod
    def _load() -> list[Entry]:
        try:
            data = json.loads(path().read_text(encoding="utf-8-sig"))
            known = {f.name for f in fields(Entry)}
            items = [Entry(**{k: v for k, v in item.items() if k in known}) for item in data.get("items", [])
                     if isinstance(item, dict) and isinstance(item.get("id"), str)
                     and isinstance(item.get("text"), str)]
            return items[-MAX_ITEMS:]
        except FileNotFoundError:
            return []
        except Exception:
            log.exception("Historii diktátů nejde načíst, začínám s prázdnou")
            return []

    def save(self) -> None:
        """A temporary file swapped in; nothing at all when the history isn't kept."""
        if not self.persist:
            return
        target = path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name("history.json.tmp")
            tmp.write_text(json.dumps({"version": 1, "items": [asdict(e) for e in self.items]}, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, target)
        except OSError:
            log.exception("Historii diktátů nejde uložit")

    def set_persist(self, persist: bool) -> None:
        """Switched off: the file goes (the user asked for nothing to be kept), the last one stays in memory."""
        if persist == self.persist:
            return
        self.persist = persist
        if persist:
            self.save()
            return
        del self.items[:-1]
        try:
            path().unlink(missing_ok=True)
        except OSError:
            log.exception("Historii diktátů nejde smazat")

    def add(self, text: str, **info) -> Entry:
        entry = Entry(id=uuid.uuid4().hex[:12], at=time.time(), text=text, **info)
        self.items.append(entry)
        del self.items[:-(MAX_ITEMS if self.persist else 1)]
        self.save()
        return entry

    def get(self, entry_id: str) -> Entry | None:
        return next((e for e in self.items if e.id == entry_id), None)

    def last(self) -> Entry | None:
        """The newest one with text (a failed transcription has none)."""
        return next((e for e in reversed(self.items) if e.best.strip()), None)

    def update(self, entry: Entry, **changes) -> None:
        for key, value in changes.items():
            setattr(entry, key, value)
        self.save()

    def remove(self, entry_id: str) -> None:
        self.items = [e for e in self.items if e.id != entry_id]
        self.save()

    def clear(self) -> None:
        self.items = []
        self.save()
