"""Models of Orbit's sessions (app/models.py): what a model is called and which family it is, what --model a new
session gets (none for the default), the requests a running session's mod answers, the default for new sessions put
back after /model saved the session's model there, Orbit's PreModelSwitch hook (cc_hook.py, through a pipe) letting
only Orbit's own switch through, the hook entry being the one Claude Code waits for, and the session overview reading
a session's model from its transcript. Orbit's and Claude Code's folders are temporary ones.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import json
import logging
import os
import shutil
import subprocess
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

from app import claude_settings, config, models, paths, sessions  # noqa: E402

SID = "1ff7f7ae-c37c-43bf-9795-c205fec01d46"


def settings_path() -> Path:
    return paths.claude_dir() / "settings.json"


def write_settings(settings: dict) -> None:
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text(json.dumps(settings), encoding="utf-8")
    time.sleep(0.01)  # a new mtime for models.default's cache


def read_settings() -> dict:
    return json.loads(settings_path().read_text(encoding="utf-8"))


class Names(unittest.TestCase):
    def test_family_and_label(self):
        cases = {
            "claude-opus-5-5[1m]": ("opus", "Opus 5.5"), "claude-sonnet-5-5": ("sonnet", "Sonnet 5.5"),
            "Opus 5.5 (1M context)": ("opus", "Opus 5.5"), "Sonnet 5.5": ("sonnet", "Sonnet 5.5"),
            "claude-haiku-4-5-20251001": ("haiku", "Haiku 4.5"), "claude-fable-5-1": ("fable", "Fable 5.1"),
            "claude-opus-5": ("opus", "Opus 5"), "opus[1m]": ("opus", "Opus"), "haiku": ("haiku", "Haiku"),
            "best": ("fable", "Fable"), "<synthetic>": ("", ""), "": ("", ""),
        }
        for model, (family, label) in cases.items():
            self.assertEqual((models.family(model), models.label(model)), (family, label), model)

    def test_only_orbits_aliases(self):
        for model in ("fable", "opus", "sonnet", "haiku", "opus[1m]", "Sonnet"):
            self.assertTrue(models.is_alias(model), model)
        for model in ("", "claude-opus-5-5", "gpt-4", "haiku & calc", "opus[1m] --x", "opusplan", '"sonnet"'):
            self.assertFalse(models.is_alias(model), model)


class ExactNames(unittest.TestCase):
    """Which model an alias stands for, from Claude Code's answer to initialize (as the SDK's supportedModels):
    asked once per Claude Code version, kept in Orbit's cache folder; until then the family's name."""
    ANSWER = {"models": [
        {"value": "default", "resolvedModel": "claude-sonnet-5-5", "displayName": "Default (recommended)"},
        {"value": "opus", "resolvedModel": "claude-opus-5-5", "displayName": "Opus 5.5"},
        {"value": "fable", "resolvedModel": "claude-fable-5-1", "displayName": "Fable 5.1"},
        {"value": "sonnet", "resolvedModel": "claude-sonnet-5-5", "displayName": "Sonnet 5.5"},
        {"value": "haiku", "resolvedModel": "claude-haiku-5-5", "displayName": "Haiku 5.5"},
        {"value": "claude-opus-4-8", "resolvedModel": "claude-opus-4-8", "displayName": "Opus 4.8"},
        {"value": "sonnet", "displayName": "<b>Sonnet</b> & more"}, "nonsense"]}

    def setUp(self):
        models.CATALOG_PATH.unlink(missing_ok=True)
        models._catalog = None
        self.addCleanup(models.CATALOG_PATH.unlink, True)
        self.addCleanup(setattr, models, "_catalog", None)

    def test_only_the_four_aliases_with_a_models_name(self):
        self.assertEqual(models.parse_catalog(self.ANSWER), {
            "opus": {"id": "claude-opus-5-5", "name": "Opus 5.5"}, "fable": {"id": "claude-fable-5-1", "name": "Fable 5.1"},
            "sonnet": {"id": "claude-sonnet-5-5", "name": "Sonnet 5.5"},
            "haiku": {"id": "claude-haiku-5-5", "name": "Haiku 5.5"}})
        self.assertEqual(models.parse_catalog({}), {})

    def test_asked_once_a_version(self):
        self.assertEqual((models.name("sonnet"), models.label("sonnet")), ("Sonnet", "Sonnet"))  # not asked yet
        asked = []
        with mock.patch.object(models, "_ask_claude", side_effect=lambda exe: asked.append(exe) or self.ANSWER):
            self.assertTrue(models.refresh_names(r"C:\claude.exe", "2.1.301"))
            self.assertFalse(models.refresh_names(r"C:\claude.exe", "2.1.301"))  # the same version: not again
            self.assertEqual(asked, [r"C:\claude.exe"])
            self.assertEqual((models.name("sonnet"), models.label("opus[1m]")), ("Sonnet 5.5", "Opus 5.5"))
            models._catalog = None  # another process (the + opens sessions in one): from the cache folder
            self.assertEqual(models.name("fable"), "Fable 5.1")
            models.refresh_names(r"C:\claude.exe", "2.1.302")  # an update: asked again
            self.assertEqual(len(asked), 2)
        with mock.patch.object(models, "_ask_claude", return_value={}):
            self.assertFalse(models.refresh_names(r"C:\claude.exe", "2.1.303"))  # no answer: the names stay
        self.assertEqual(models.name("haiku"), "Haiku 5.5")


class Launch(unittest.TestCase):
    def tearDown(self):
        settings_path().unlink(missing_ok=True)

    def test_no_model_flag_for_the_default(self):
        write_settings({"model": "opus[1m]"})
        self.assertEqual(models.default(), "opus[1m]")
        self.assertEqual(models.launch_model("opus"), "")  # the session starts as one from the Explorer would
        self.assertEqual(models.launch_model("sonnet"), "sonnet")
        self.assertEqual(models.launch_model(""), "")
        self.assertEqual(models.launch_model("gpt"), "")
        self.assertEqual(models.alias("opus"), "opus[1m]")  # switched to Opus: the default's 1M stays
        self.assertEqual(models.alias("haiku"), "haiku")

    def test_without_a_default(self):
        write_settings({"theme": "dark"})
        self.assertEqual(models.default(), "")
        self.assertEqual(models.launch_model("opus"), "opus")  # nothing to compare with: what was picked
        settings_path().write_text("{ broken", encoding="utf-8")  # being written: the last one read stands
        self.assertEqual(models.default(), "")


class Switching(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(models.SWITCH_DIR, ignore_errors=True)
        self.addCleanup(shutil.rmtree, models.SWITCH_DIR, True)
        self.addCleanup(lambda: settings_path().unlink(missing_ok=True))
        for name in (claude_settings.BACKUP_NAME,):
            self.addCleanup(lambda n=name: (paths.claude_dir() / n).unlink(missing_ok=True))

    def test_a_request_and_its_answers(self):
        write_settings({"model": "opus[1m]", "theme": "dark"})
        request_id = models.ask(SID, "sonnet")
        record = models.request(SID, request_id)
        self.assertEqual({k: record[k] for k in ("session_id", "id", "model", "default")},
                         {"session_id": SID, "id": request_id, "model": "sonnet", "default": "opus[1m]"})
        self.assertFalse(models.acked(SID, request_id))
        self.assertIsNone(models.answer(SID, request_id))
        (models.SWITCH_DIR / f"{SID}.{request_id}.ack.json").write_text("{}", encoding="utf-8")
        (models.SWITCH_DIR / f"{SID}.{request_id}.done.json").write_text(
            json.dumps({"ok": True, "text": "Set model to `Sonnet 5.5`", "model": "claude-sonnet-5-5"}), "utf-8")
        self.assertTrue(models.acked(SID, request_id))
        self.assertEqual(models.answer(SID, request_id)["model"], "claude-sonnet-5-5")
        left = models.leftovers()
        self.assertEqual([(r["id"], r["done"]["ok"]) for r in left], [(request_id, True)])
        models.forget(SID, request_id)
        self.assertEqual(list(models.SWITCH_DIR.iterdir()), [])
        for session_id, model in (("../x", "sonnet"), (SID, "claude-opus-5-5"), (SID, "haiku; calc")):
            with self.assertRaises(ValueError):
                models.ask(session_id, model)

    def test_the_default_goes_back(self):
        """/model saved the session's model as the default for new sessions: back to what it was, the rest of
        settings.json as it was; a default the user set meanwhile stays."""
        write_settings({"model": "opus[1m]", "theme": "dark", "hooks": {"Stop": []}})
        record = models.request(SID, models.ask(SID, "sonnet"))
        self.assertFalse(models.restore_default(record))  # /model hasn't saved anything yet
        write_settings({"model": "sonnet", "theme": "dark", "hooks": {"Stop": []}})  # what /model did
        self.assertTrue(models.restore_default(record))
        self.assertEqual(read_settings(), {"model": "opus[1m]", "theme": "dark", "hooks": {"Stop": []}})
        write_settings({"model": "haiku", "theme": "dark"})  # the user's own choice since
        self.assertFalse(models.restore_default(record))
        self.assertEqual(read_settings()["model"], "haiku")

    def test_two_switches_at_once(self):
        """The second one is asked for after the first one's /model saved Sonnet as the default: both go back to
        the default from before either of them."""
        write_settings({"model": "opus[1m]"})
        first = models.request(SID, models.ask(SID, "sonnet"))
        write_settings({"model": "sonnet"})  # the first session's /model
        second = models.request("other", models.ask("other", "haiku", first))
        self.assertEqual(second["default"], "opus[1m]")
        write_settings({"model": "haiku"})  # the second session's /model
        self.assertFalse(models.restore_default(first))  # not its model any more
        self.assertTrue(models.restore_default(second))
        self.assertEqual(read_settings()["model"], "opus[1m]")

    def test_no_default_before_none_after(self):
        write_settings({"theme": "dark"})
        record = models.request(SID, models.ask(SID, "haiku"))
        self.assertIsNone(record["default"])
        write_settings({"theme": "dark", "model": "haiku"})
        self.assertTrue(models.restore_default(record))
        self.assertEqual(read_settings(), {"theme": "dark"})
        self.assertFalse(models.restore_default({}))


class Hook(unittest.TestCase):
    """cc_hook.py the way Claude Code runs it for PreModelSwitch: allow only for a switch Orbit asked for in this
    session, to this model, lately; no state file, no output otherwise."""

    def setUp(self):
        shutil.rmtree(models.SWITCH_DIR, ignore_errors=True)
        self.addCleanup(shutil.rmtree, models.SWITCH_DIR, True)

    def run_hook(self, **event) -> str:
        data = dict({"session_id": SID, "hook_event_name": "PreModelSwitch", "from_model": "claude-opus-5-5",
                     "to_model": "claude-sonnet-5-5", "requested_model": "sonnet", "source": "command"}, **event)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_ENTRYPOINT"}
        run = subprocess.run([sys.executable, str(ROOT / "app" / "cc_hook.py")], input=json.dumps(data).encode(),
                             capture_output=True, env=env, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        return run.stdout.decode("utf-8").strip()

    def test_only_orbits_own_switch(self):
        self.assertEqual(self.run_hook(), "")  # nothing asked: Claude Code asks the user as always
        request_id = models.ask(SID, "sonnet")
        answer = json.loads(self.run_hook())["hookSpecificOutput"]
        self.assertEqual((answer["hookEventName"], answer["permissionDecision"]), ("PreModelSwitch", "allow"))
        self.assertEqual(self.run_hook(requested_model="haiku"), "")  # another model
        self.assertEqual(self.run_hook(session_id="other-session"), "")  # another session
        path = models.SWITCH_DIR / f"{SID}.{request_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(dict(record, time=time.time() - models.ASK_FRESH_S - 5)), encoding="utf-8")
        self.assertEqual(self.run_hook(), "")  # long ago
        self.assertEqual(sorted(p.name for p in config.SESSIONS_DIR.glob(f"{SID}.*.json")), [])  # no state file


class HookEntry(unittest.TestCase):
    def tearDown(self):
        settings_path().unlink(missing_ok=True)
        (paths.claude_dir() / claude_settings.BACKUP_NAME).unlink(missing_ok=True)

    def test_premodelswitch_is_waited_for_the_rest_isnt(self):
        write_settings({"model": "opus[1m]"})
        self.assertTrue(claude_settings.set_hooks(True))
        hooks = read_settings()["hooks"]
        entry = hooks["PreModelSwitch"][0]["hooks"][0]
        self.assertNotIn("async", entry)
        self.assertTrue(claude_settings.is_our_hook(entry))
        self.assertTrue(hooks["Stop"][0]["hooks"][0]["async"])
        self.assertFalse(claude_settings.set_hooks(True))  # already there: settings.json isn't written again
        self.assertTrue(claude_settings.set_hooks(False))
        self.assertNotIn("hooks", read_settings())
        self.assertEqual(read_settings()["model"], "opus[1m]")


class Transcript(unittest.TestCase):
    """What a session runs on, from its transcript's end: the newest answer, or /model after it; the SessionStart
    hook's model before the first answer."""

    def lines(self, *entries) -> list[bytes]:
        return [json.dumps(e, ensure_ascii=False, separators=(",", ":")).encode() for e in entries]

    @staticmethod
    def answer(model, sidechain=False):
        return {"parentUuid": "x", "isSidechain": sidechain, "message": {"model": model, "role": "assistant",
                                                                        "content": [{"type": "text", "text": "Ahoj"}]},
                "type": "assistant"}

    @staticmethod
    def stdout(text):
        return {"isSidechain": False, "type": "user",
                "message": {"role": "user", "content": f"<local-command-stdout>{text}</local-command-stdout>"}}

    def test_newest_wins(self):
        lines = self.lines(self.answer("claude-haiku-5-5"), self.answer("claude-opus-5-5", sidechain=True))
        self.assertEqual(sessions._model(lines), "claude-haiku-5-5")  # a subagent's answer doesn't count
        lines += self.lines(self.stdout("Set model to `Sonnet 5.5` and saved as your default for new sessions"))
        self.assertEqual(sessions._model(lines), "Sonnet 5.5")
        lines += self.lines(self.answer("claude-sonnet-5-5"), self.answer("<synthetic>"))
        self.assertEqual(sessions._model(lines), "claude-sonnet-5-5")
        typed = {"isSidechain": False, "type": "user", "message": {"role": "user", "content": "Set model to `Haiku`"}}
        self.assertEqual(sessions._model(lines + self.lines(typed)), "claude-sonnet-5-5")  # the user's own words
        self.assertEqual(sessions._model([]), "")

    def test_the_tracker(self):
        transcript = Path(tempfile.mkdtemp(prefix="orbit-model-")) / f"{SID}.jsonl"
        self.addCleanup(shutil.rmtree, transcript.parent, True)
        config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        hook = config.SESSIONS_DIR / f"{SID}.SessionStart.json"
        self.addCleanup(hook.unlink, True)
        hook.write_text(json.dumps({"session_id": SID, "cwd": str(transcript.parent), "model": "claude-opus-5-5[1m]",
                                    "transcript_path": str(transcript), "time": time.time(), "pid": 0}), "utf-8")
        transcript.write_bytes(b"")
        tracker = sessions.SessionTracker()
        tracker.poll()
        s = tracker.sessions[SID]
        self.assertEqual(s.model, "claude-opus-5-5[1m]")  # no answer yet: what it started with
        self.assertIn("Model: Opus 5.5", s.tooltip())
        transcript.write_bytes(b"\n".join(self.lines(self.answer("claude-opus-5-5"),
                                                     self.stdout("Set model to `Haiku 5.5` and saved"))) + b"\n")
        os.utime(transcript, (time.time() + 5, time.time() + 5))
        tracker.poll()
        self.assertEqual(tracker.sessions[SID].model, "Haiku 5.5")
        s.model_switch = "Sonnet"
        self.assertIn("Přepínám model na Sonnet…", s.tooltip())


if __name__ == "__main__":
    unittest.main()
