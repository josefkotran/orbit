"""How well Orbit understands the user's own voice. The reference is the user's own correction of a dictation (the
history window, Uložit opravu); measured against it: what Orbit typed, Whisper's text before the transcript check
fixed it, the second recognizer's (Canary's) text, and with --again what today's Whisper (vocabulary, trim) writes
from the kept recording. Word error rate after lower case and without punctuation, like the measurements in CLAUDE.md.

    .venv\\Scripts\\python.exe build\\eval_dictation.py [--again]

Reads the data folder (history.json, recordings\\), writes nothing. --again starts a whisper-server of its own.
"""
import argparse
import re
import sys
import unicodedata
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, history  # noqa: E402
from app.recorder import trim_tail  # noqa: E402
from app.whisper_server import (WhisperServer, apply_replacements, apply_voice_commands, build_prompt,  # noqa: E402
                                clean_text, terminal_command)


def words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]|_", " ", unicodedata.normalize("NFC", text).lower()).split()


def errors(ref: list[str], hyp: list[str]) -> int:
    """Substitutions, deletions and insertions (word-level Levenshtein)."""
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--again", action="store_true", help="transcribe the kept recordings again with today's Whisper")
    args = ap.parse_args()
    cfg = config.load()
    entries = [e for e in history.History().items if e.corrected.strip() and e.kind != history.AGENT and
               not e.instruction]
    if not entries:
        print("V historii zatím není žádný opravený diktát. Oprav pár diktátů v Historii diktátů (Uložit opravu), "
              "nejlépe takových, kde Orbit něco spletl i nespletl, a spusť to znovu.")
        return
    systems = {"Orbit vložil": lambda e: e.text, "před kontrolou přepisu": lambda e: e.unchecked or e.text,
               "druhý rozpoznávač": lambda e: e.second or None}
    again: dict[str, str] = {}
    if args.again:
        server = WhisperServer()
        server.start(cfg["model"])
        try:
            for e in entries:
                wav = config.RECORDINGS_DIR / f"{e.recording}.wav"
                if e.recording and wav.is_file():
                    with wave.open(str(wav)) as w:
                        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16)
                    text = apply_replacements(clean_text(server.transcribe(trim_tail(audio),
                                                                           build_prompt(cfg["vocabulary"]))),
                                              cfg["replacements"])
                    again[e.id] = terminal_command(apply_voice_commands(text))[0] if cfg["voice_commands"] else text
        finally:
            server.stop()
        systems["Whisper teď (bez kontroly)"] = lambda e: again.get(e.id)
    print(f"Opravených diktátů: {len(entries)}, slov v opravách: {sum(len(words(e.corrected)) for e in entries)}")
    for name, pick in systems.items():
        done = [(words(e.corrected), words(pick(e))) for e in entries if pick(e) is not None]
        total = sum(len(r) for r, _ in done)
        if not total:
            print(f"  {name}: nic k porovnání")
            continue
        wrong = sum(errors(r, h) for r, h in done)
        print(f"  {name}: {wrong / total * 100:.1f} % chybných slov ({len(done)} diktátů)")


if __name__ == "__main__":
    main()
