"""Past Claude Code sessions (app/pastsessions.py, the session history under the clock above the panel): a session is
named the way Claude Code's /resume names it (/rename, then its own title, then the first prompt), its first and newest
prompt are what the user wrote (not tool results, notes, notifications or messages from other sessions), headless
runs, subagents, empty sessions and ones that went on elsewhere are left out, and a transcript that only grew gets
just its end read again. Transcripts are written to a temporary Claude Code folder.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import pastsessions  # noqa: E402

FOLDER = r"C:\Users\jana\m-tex"
IDS = [f"{n:08x}-0000-4000-8000-000000000000" for n in range(1, 20)]


def user(text, cwd=FOLDER, **extra) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}, "cwd": cwd, "entrypoint": "cli",
            "timestamp": "2026-10-08T12:00:00.000Z", "gitBranch": "master", "isSidechain": False, **extra}


def assistant(text="Hotovo.") -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
            "cwd": FOLDER, "timestamp": "2026-10-08T12:01:00.000Z", "gitBranch": "master", "isSidechain": False}


class Transcripts(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="orbit-test-past-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        patch = mock.patch.object(pastsessions.paths, "claude_dir", return_value=self.dir)
        patch.start()
        self.addCleanup(patch.stop)
        self.project = self.dir / "projects" / "C--Users-jana-m-tex"
        self.project.mkdir(parents=True)

    def write(self, session_id: str, entries: list, age: float = 0.0, mode: str = "w") -> Path:
        path = self.project / f"{session_id}.jsonl"
        with open(path, mode, encoding="utf-8") as f:
            for entry in entries:
                # compact like Claude Code's own lines ("type":"user"), which the reading looks for
                line = entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False,
                                                                        separators=(",", ":"))
                f.write(line + "\n")
        when = time.time() - age
        os.utime(path, (when, when))
        return path

    def scan(self) -> dict:
        return {p.id: p for p in pastsessions.Index().scan()}

    def test_named_like_claude_codes_picker(self):
        self.write(IDS[0], [user("Uprav ceník"), assistant(), {"type": "ai-title", "aiTitle": "Ceník  Profodu"},
                            {"type": "custom-title", "customTitle": "Moje jméno"}])
        self.write(IDS[1], [user("Uprav ceník"), assistant(), {"type": "ai-title", "aiTitle": "Starý název"},
                            {"type": "ai-title", "aiTitle": "Ceník Profodu"}])
        self.write(IDS[2], [user("Oprav   objednávku\n82"), assistant()])
        self.write(IDS[3], [user("<command-message>loop</command-message>\n<command-name>/loop</command-name>\n"
                                 "<command-args>5m zkontroluj frontu</command-args>"), assistant()])
        found = self.scan()
        self.assertEqual(found[IDS[0]].name, "Moje jméno")  # /rename wins
        self.assertEqual(found[IDS[1]].name, "Ceník Profodu")  # the newest of Claude Code's titles
        self.assertEqual(found[IDS[2]].name, "Oprav objednávku 82")  # no title yet: the first prompt
        self.assertEqual(found[IDS[3]].first, "/loop 5m zkontroluj frontu")
        self.assertEqual(found[IDS[0]].folder, "m-tex")
        self.assertEqual(found[IDS[0]].branch, "master")

    def test_prompts_are_what_the_user_wrote(self):
        self.write(IDS[0], [
            {"type": "permission-mode", "permissionMode": "bypassPermissions", "sessionId": IDS[0]},
            {"type": "attachment", "cwd": FOLDER, "entrypoint": "cli", "attachment": {"content": "x" * 600_000}},
            user("<local-command-caveat>Caveat: …</local-command-caveat>"),
            user("Kontext, který si Claude Code přidal sám", isMeta=True),
            user([{"type": "text", "text": "Podívej se na ten screenshot"}, {"type": "image", "source": {}}]),
            assistant(),
            user([{"type": "tool_result", "tool_use_id": "t1", "content": "výsledek"}]),
            {"type": "last-prompt", "lastPrompt": "Podívej se na ten screenshot"},
            user("Teď to commitni", origin={"kind": "human"}, turnPosition={"promptIndex": 2}),
            assistant(),
            user("<task-notification>hotovo</task-notification>", origin={"kind": "task-notification"}),
            user("Ohlášení od jiné relace", origin={"kind": "peer"}),
            user("This session is being continued…", isCompactSummary=True),
            # Claude Code puts its notes at the end again when the session is left: an old prompt can come back
            {"type": "last-prompt", "lastPrompt": "Podívej se na ten screenshot"},
        ])
        past = self.scan()[IDS[0]]
        self.assertEqual(past.first, "Podívej se na ten screenshot")  # after a 600 kB line: a few blocks in
        self.assertEqual(past.last, "Teď to commitni")
        self.assertEqual(past.prompts, 2)
        self.assertEqual(past.cwd, FOLDER)

    def test_left_out(self):
        self.write(IDS[0], [user("Odpověz jen jedním slovem", entrypoint="sdk-cli"), assistant()])  # headless
        self.write(IDS[1], [user("Úkol podagenta", isSidechain=True), assistant()])
        self.write(IDS[2], [{"type": "permission-mode", "permissionMode": "default"},
                            {"type": "attachment", "cwd": FOLDER, "attachment": {}}])  # nothing said in it
        self.write(IDS[3], [user("Začátek"), assistant(), {"type": "continued-in", "continuedInSessionId": IDS[4]}])
        self.write(IDS[4], [user("Pokračování"), assistant()])
        self.write(IDS[5], [user("Začátek"), assistant(), {"type": "continued-in", "continuedInSessionId": IDS[9]}])
        self.write("ne-relace", [user("Něco"), assistant()])
        (self.project / IDS[6]).mkdir()  # a session's folder of subagents, not a transcript
        self.write(IDS[7], ["{nedopsaný řádek", user("Funguje i tak"), assistant()])
        self.assertEqual(set(self.scan()), {IDS[4], IDS[5], IDS[7]})  # IDS[9] isn't there: IDS[5] stays

    def test_newest_first(self):
        self.write(IDS[0], [user("Starší"), assistant()], age=7200)
        self.write(IDS[1], [user("Novější"), assistant()], age=60)
        self.write(IDS[2], [user("Nejstarší"), assistant()], age=86400)
        self.assertEqual([p.id for p in pastsessions.Index().scan()], [IDS[1], IDS[0], IDS[2]])

    def test_grown_transcript_gets_only_its_end_read(self):
        index = pastsessions.Index()
        self.write(IDS[0], [user("Uprav ceník"), assistant()], age=60)
        with mock.patch.object(pastsessions, "_read_head", wraps=pastsessions._read_head) as head:
            self.assertEqual(index.scan()[0].name, "Uprav ceník")
            self.assertEqual(index.scan()[0].name, "Uprav ceník")  # unchanged: not read at all
            self.assertEqual(head.call_count, 1)
            self.write(IDS[0], [user("A teď PDF"), assistant(), {"type": "ai-title", "aiTitle": "Ceník a PDF"}],
                       mode="a")
            past = index.scan()[0]
            self.assertEqual(head.call_count, 1)  # it only grew: its start is known
            self.assertEqual((past.name, past.first, past.last), ("Ceník a PDF", "Uprav ceník", "A teď PDF"))
            self.write(IDS[0], [user("Úplně jiná"), assistant()])  # rewritten, shorter
            self.assertEqual(index.scan()[0].first, "Úplně jiná")
            self.assertEqual(head.call_count, 2)
        self.assertIs(index.get(IDS[0]), index.scan()[0])
        (self.project / f"{IDS[0]}.jsonl").unlink()
        self.assertEqual(index.scan(), [])
        self.assertIsNone(index.get(IDS[0]))

    def test_kept_days(self):
        settings = self.dir / "settings.json"
        self.assertEqual(pastsessions.kept_days(), 30)  # no settings.json
        settings.write_text('{"cleanupPeriodDays": 14}', encoding="utf-8")
        self.assertEqual(pastsessions.kept_days(), 14)
        for bad in ('{"cleanupPeriodDays": "14"}', '{"cleanupPeriodDays": 0}', "[]", "{nečitelný"):
            settings.write_text(bad, encoding="utf-8")
            self.assertEqual(pastsessions.kept_days(), 30, bad)


class Search(unittest.TestCase):
    def test_every_word_anywhere_without_diacritics(self):
        past = pastsessions.Past(IDS[0], "", FOLDER, title="Ceník Profodu", first="Uprav ceník pro velkoobchod",
                                 last="Commitni to", branch="master")
        for query in ("cenik", "PROFOD velko", "m-tex", "commitni cenik", "master", IDS[0][:8]):
            self.assertTrue(pastsessions.matches(past, pastsessions.fold(query)), query)
        for query in ("faktura", "cenik faktura"):
            self.assertFalse(pastsessions.matches(past, pastsessions.fold(query)), query)

    def test_when(self):
        now = time.time()
        self.assertTrue(pastsessions.when(now).startswith("dnes "))
        self.assertTrue(pastsessions.when(now - 86400).startswith("včera "))
        self.assertRegex(pastsessions.when(now - 5 * 86400), r"^\d{1,2}\. \d{1,2}\. ")
        self.assertRegex(pastsessions.when(now - 400 * 86400), r"^\d{1,2}\. \d{1,2}\. \d{4} ")


if __name__ == "__main__":
    unittest.main()
