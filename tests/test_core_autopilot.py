"""The Autopilot (app/autopilot.py) and its phone calls (app/bland.py), with Bland and the session's mod replaced: a
session on autopilot gets round 1 through the mod's folder, its report goes to the call once its turn is over, what the
user said starts the next round right away, and the next call waits for the interval; a call nobody picks up is tried
again an interval later, never at night; a session without the new mod, a refused key and a session that ended stop
it; "AUTOPILOT: KONEC" switches it off; a restart of Orbit picks it up where it was. Bland's answers are read the way
its API gives them (outcome, transcript), phone numbers come out as E.164 and the key is kept encrypted.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import autopilot, bland  # noqa: E402

SID = "3f1c2a9e-0000-4000-8000-000000000001"
NOON = datetime(2026, 10, 13, 12, 0).timestamp()


class Pool:
    """Runs a request right away (a thread pool's results, without threads)."""

    def submit(self, fn, *args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as e:
            future.set_exception(e)
        return future

    def shutdown(self, **_):
        pass


class Bland:
    """What the Autopilot asks Bland, and Bland's answers as its API gives them."""

    def __init__(self):
        self.calls: list[dict] = []
        self.answer: dict = {"completed": False, "status": "started"}
        self.refuse = ""

    def start_call(self, key, phone, task, first, voice="", summary=""):
        if self.refuse:
            raise bland.BlandError(self.refuse)
        self.calls.append({"key": key, "phone": phone, "task": task, "first": first, "summary": summary})
        return f"call-{len(self.calls)}"

    def details(self, key, call_id):
        return self.answer

    outcome = staticmethod(bland.outcome)
    transcript = staticmethod(bland.transcript)

    def account(self, key):
        return {"status": "active", "billing": {"current_balance": 12.5}}


def answered(*lines: tuple[str, str], summary: str = "") -> dict:
    return {"completed": True, "status": "completed", "answered_by": "human", "call_length": 2.4, "price": 0.31,
            "summary": summary, "transcripts": [{"id": i, "user": who, "text": text}
                                                for i, (who, text) in enumerate(lines)]}


class Autopilot(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="orbit-test-autopilot-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.now = NOON
        self.cfg = {"phone": "+420602123456", "key": "sk-test", "voice": "", "name": "Pepa", "quiet": True}
        self.bland = Bland()
        self.session = SimpleNamespace(id=SID, name="Ceník Profodu", folder="m-tex", state="done", since=NOON - 600,
                                       message="", background=[])

    def pilot(self) -> autopilot.Autopilot:
        return autopilot.Autopilot(lambda: self.cfg, path=self.dir / "autopilot.json", prompt_dir=self.dir / "prompt",
                                   caller=self.bland, clock=lambda: self.now, pool=Pool())

    def requests(self) -> list[dict]:
        return [json.loads(f.read_text(encoding="utf-8")) for f in sorted((self.dir / "prompt").glob("*.json"))
                if not f.name.endswith(".done.json")]

    def mod_takes(self, ok: bool = True, text: str = "started") -> dict:
        """The session's mod: finds the prompt and answers next to it."""
        [request] = self.requests()
        (self.dir / "prompt" / f"{SID}.{request['id']}.done.json").write_text(json.dumps({"ok": ok, "text": text}),
                                                                             encoding="utf-8")
        return request

    def turn(self, message: str, after: float = 300) -> None:
        """The session works on the prompt, then its Stop."""
        self.now += after
        self.session.state, self.session.since, self.session.message = "done", self.now, message

    def tick(self, ap, seconds: float = 1) -> list:
        self.now += seconds
        ap.tick({SID: self.session})
        return ap.drain_events()

    def test_round_report_call_answer_next_round(self):
        ap = self.pilot()
        self.assertEqual(ap.start(self.session, "Dodělej import ceníku Profodu", 3600), "")
        request = self.mod_takes()
        self.assertEqual(request["session_id"], SID)
        self.assertIn("Cíl: Dodělej import ceníku Profodu", request["text"])
        self.assertIn("## Hlášení pro telefon", request["text"])
        self.tick(ap)
        p = ap.pilots[SID]
        self.assertEqual((p.stage, p.round), ("working", 1))
        self.assertEqual(self.requests(), [])  # Orbit removed the request and the answer
        self.tick(ap, 60)
        self.assertEqual(self.bland.calls, [])  # the session's turn isn't over yet: no call

        self.turn("Opravil jsem import.\n\n## Hlášení pro telefon\nCo jsem udělal: **import** ceníku, viz "
                  "`app/import.py`.\nNávrhy, jak dál: 1) přidat slevy 2) nic\nOtázka: Mám přidat slevy?")
        self.tick(ap)
        [call] = self.bland.calls  # the first call: right away
        self.assertEqual((call["phone"], call["key"]), ("+420602123456", "sk-test"))
        self.assertIn("Co jsem udělal: import ceníku", call["task"])  # the report, without Markdown and code
        self.assertNotIn("Opravil jsem import", call["task"])  # only the part for the phone
        self.assertNotIn("app/import.py", call["task"])
        self.assertIn("Ceník Profodu", call["first"])
        self.assertEqual(ap.pilots[SID].stage, "calling")
        self.tick(ap, 10)  # still running
        self.assertEqual(ap.pilots[SID].stage, "calling")

        self.bland.answer = answered(("assistant", "Ahoj, tady Orbit."), ("user", "Jo, přidej slevy, dvacet procent."),
                                     summary="Uživatel chce slevy 20 %.")
        events = self.tick(ap, 10)
        self.assertEqual([e[0] for e in events], ["done"])
        p = ap.pilots[SID]
        self.assertEqual((p.stage, p.round), ("sending", 2))
        self.assertEqual(p.calls[-1].result, "answered")
        self.assertEqual(p.calls[-1].price, 0.31)
        [request] = self.requests()  # the answer is the next round's prompt, right after the call
        self.assertIn("Pepa: Jo, přidej slevy, dvacet procent.", request["text"])
        self.assertIn("Shrnutí hovoru: Uživatel chce slevy 20 %.", request["text"])
        self.assertIn(autopilot.END_MARK, request["text"])
        call_at = self.now

        self.mod_takes()
        self.tick(ap)
        self.turn("## Hlášení pro telefon\nCo jsem udělal: slevy.", after=600)
        events = self.tick(ap)
        p = ap.pilots[SID]
        self.assertEqual(p.stage, "waiting")  # 10 minutes after the last call: it waits for the hour
        self.assertAlmostEqual(p.next_call, call_at + 3600, delta=1)
        self.assertEqual(len(self.bland.calls), 1)
        self.assertIn("zavolám ti v", events[0][3])
        self.assertEqual(p.label(), autopilot.clock_text(p.next_call))
        self.now = p.next_call
        self.tick(ap, 0)
        self.assertEqual(len(self.bland.calls), 2)

    def test_nobody_answers_it_waits_and_never_calls_at_night(self):
        ap = self.pilot()
        self.now = datetime(2026, 10, 13, 21, 30).timestamp()
        ap.start(self.session, "", 3600)
        self.assertIn("Pokračuj v tom, na čem", self.requests()[0]["text"])  # no goal: what it works on
        self.mod_takes()
        self.tick(ap)
        self.turn("## Hlášení pro telefon\nCo jsem udělal: nic moc.", after=60)
        self.tick(ap)
        self.bland.answer = {"completed": True, "status": "no-answer", "answered_by": "no-answer", "transcripts": []}
        events = self.tick(ap, 10)
        p = ap.pilots[SID]
        self.assertEqual(p.stage, "waiting")  # the session waits for the user (Pepa's choice)
        self.assertEqual(p.calls[-1].result, "unanswered")
        morning = datetime(2026, 10, 14, 7, 0).timestamp()
        self.assertEqual(p.next_call, morning)  # 22:31 + an hour is night: 7:00
        self.assertEqual(events[0][0], "waiting")
        self.assertEqual(self.requests(), [])  # nothing sent to the session
        self.cfg["quiet"] = False
        self.assertEqual(ap._when(morning - 3600 * 5), morning - 3600 * 5)

        ap.call_now(SID)  # "Zavolat teď": now, night or not
        self.cfg["quiet"] = True
        self.tick(ap)
        self.assertEqual(len(self.bland.calls), 2)

    def test_a_voicemail_or_silence_is_no_answer(self):
        self.assertEqual(bland.outcome({"completed": True, "status": "completed", "answered_by": "voicemail"}),
                         "unanswered")
        self.assertEqual(bland.outcome(answered(("assistant", "Ahoj"), ("user", "  "))), "unanswered")
        self.assertEqual(bland.outcome({"completed": True, "status": "completed",
                                        "concatenated_transcript": "assistant: Ahoj\nuser: Jo, dělej."}), "answered")
        self.assertIsNone(bland.outcome({"completed": False, "status": "started", "queue_status": "started"}))
        self.assertEqual(bland.outcome({"completed": False, "queue_status": "call_error"}), "failed")
        self.assertEqual(bland.transcript({"concatenated_transcript": "assistant: Ahoj\nuser: Jo."}, "Jana"),
                         "Orbit: Ahoj\nJana: Jo.")

    def test_idle_a_moment_before_the_stop_waits_for_the_report(self):
        ap = self.pilot()
        ap.start(self.session, "cíl", 3600)
        self.mod_takes()
        self.tick(ap)
        self.now += 300  # Claude Code's list says idle, its Stop hook (async) isn't here yet: no answer so far
        self.session.state, self.session.since, self.session.message = "idle", self.now - 299, ""
        self.tick(ap)
        self.assertEqual(ap.pilots[SID].stage, "working")
        self.assertEqual(self.bland.calls, [])
        self.turn("## Hlášení pro telefon\nCo jsem udělal: kniha rizik.", after=0)
        self.tick(ap)
        [call] = self.bland.calls
        self.assertIn("Co jsem udělal: kniha rizik.", call["task"])

        ap.stop(SID)
        self.now += 60
        ap.start(self.session, "cíl", 3600)
        self.mod_takes()
        self.tick(ap)
        self.session.state, self.session.since, self.session.message = "idle", self.now, ""  # Esc: no Stop at all
        self.tick(ap)
        self.assertEqual(ap.pilots[SID].stage, "working")
        self.tick(ap, autopilot.STOP_WAIT_S)  # it goes on without a report
        self.assertEqual(ap.pilots[SID].report, "")
        self.assertEqual(len(self.bland.calls), 2)
        self.assertIn("bez hlášení", self.bland.calls[-1]["task"])

    def test_a_session_without_the_new_mod_stands_until_it_has_it(self):
        ap = self.pilot()
        ap.start(self.session, "cíl", 3600)
        self.tick(ap, 3)
        self.assertEqual(ap.pilots[SID].stage, "sending")
        events = self.tick(ap, 6)  # nobody took the prompt
        p = ap.pilots[SID]
        self.assertEqual((p.stage, p.resume), ("paused", "send"))
        self.assertIn("orbit-mozek 0.4", p.note)
        self.assertEqual(events[0][0], "error")
        self.assertEqual(self.requests(), [])
        ap.call_now(SID)  # "Pokračovat": the same prompt once more
        [request] = self.requests()
        self.assertIn("Cíl: cíl", request["text"])
        self.mod_takes(ok=False, text="blocked by a hook")
        self.tick(ap)
        self.assertIn("blocked by a hook", ap.pilots[SID].note)

    def test_a_refused_key_stands_and_tells(self):
        ap = self.pilot()
        ap.start(self.session, "cíl", 3600)
        self.mod_takes()
        self.tick(ap)
        self.turn("## Hlášení pro telefon\nCo jsem udělal: x.")
        self.bland.refuse = "Bland AI klíč nepřijal."
        events = self.tick(ap)
        p = ap.pilots[SID]
        self.assertEqual((p.stage, p.resume), ("paused", "call"))
        self.assertIn("klíč nepřijal", events[-1][3])
        self.bland.refuse = ""
        ap.call_now(SID)
        self.tick(ap)
        self.assertEqual(len(self.bland.calls), 1)

    def test_the_end_said_on_the_phone_and_a_session_that_ended(self):
        ap = self.pilot()
        ap.start(self.session, "cíl", 3600)
        self.mod_takes()
        self.tick(ap)
        self.turn(autopilot.END_MARK)
        events = self.tick(ap)
        self.assertEqual(ap.pilots, {})
        self.assertEqual(events[0][0], "done")
        self.assertEqual(self.bland.calls, [])

        ap.start(self.session, "cíl", 3600)
        self.now += 1
        events = ap.tick({}) or ap.drain_events()  # the session isn't running any more
        self.assertEqual(ap.pilots, {})
        self.assertIn("Relace skončila", events[0][3])
        self.assertEqual(self.requests(), [])

    def test_a_restart_of_orbit_goes_on_where_it_was(self):
        ap = self.pilot()
        ap.start(self.session, "cíl", 1800)
        self.mod_takes()
        self.tick(ap)
        self.turn("## Hlášení pro telefon\nCo jsem udělal: x.")
        self.tick(ap)
        self.assertEqual(ap.pilots[SID].calls[-1].id, "call-1")
        again = self.pilot()  # Orbit restarted mid-call
        p = again.pilots[SID]
        self.assertEqual((p.stage, p.interval_s, p.calls[-1].id), ("calling", 1800, "call-1"))
        self.bland.answer = answered(("user", "Pokračuj."))
        self.tick(again, 10)
        self.assertEqual(again.pilots[SID].stage, "sending")
        self.assertEqual(len(self.bland.calls), 1)  # asked about the same call, not called twice

        third = self.pilot()  # restarted before the mod took the prompt: a new request
        [request] = self.requests()
        self.assertEqual(request["id"], third.pilots[SID].request)
        self.assertIn("Pepa: Pokračuj.", request["text"])

    def test_not_without_a_phone_and_a_key_and_a_test_call(self):
        ap = self.pilot()
        self.cfg["key"] = ""
        self.assertIn("klíč Bland AI", ap.start(self.session, "cíl"))
        self.assertEqual(ap.pilots, {})
        self.cfg["key"] = "sk-test"
        self.assertEqual(ap.test_call(), "")
        ap.check_account("sk-test")
        events = self.tick(ap)
        self.assertEqual([e[0] for e in events], ["test", "account"])
        self.assertEqual(events[1][3], "12.5")
        self.assertIn("zkušební hovor", self.bland.calls[0]["first"])


class Phone(unittest.TestCase):
    def test_the_report_is_for_the_ear(self):
        text = autopilot.report_text("Dlouhý popis práce.\n\n## Hlášení pro telefon\nCo jsem udělal: upravil "
                                     "C:\\Users\\a\\import.py a `Comgate`, viz [web](https://x.cz) a https://y.cz.\n"
                                     "```py\nprint(1)\n```\nStav: **hotovo**")
        self.assertEqual(text, "Co jsem udělal: upravil a Comgate, viz web a odkaz.\nStav: hotovo")
        self.assertEqual(autopilot.report_text("Bez nadpisu: jen tohle."), "Bez nadpisu: jen tohle.")
        self.assertTrue(autopilot.report_text("slovo " * 2000).endswith("…"))

    def test_numbers_as_bland_takes_them(self):
        self.assertEqual(bland.normalize_phone("602 123 456"), "+420602123456")
        self.assertEqual(bland.normalize_phone("+420 602-123-456"), "+420602123456")
        self.assertEqual(bland.normalize_phone("00421 905 123 456"), "+421905123456")
        for bad in ("", "602", "abc", "+0123456789", "12345678901234567"):
            self.assertIsNone(bland.normalize_phone(bad), bad)
        self.assertEqual(bland.masked("+420602123456"), "…456")

    def test_the_key_is_kept_encrypted_for_this_windows_account(self):
        stored = bland.protect("sk-abc123")
        self.assertTrue(stored.startswith("dpapi:"))
        self.assertNotIn("sk-abc123", stored)
        self.assertEqual(bland.unprotect(stored), "sk-abc123")
        self.assertEqual(bland.unprotect("dpapi:bm90IGEgYmxvYg=="), "")  # not ours: no key, no crash
        self.assertEqual((bland.protect(""), bland.unprotect("")), ("", ""))

    def test_errors_in_czech(self):
        answer = SimpleNamespace(status_code=401, json=lambda: {"status": "error", "message": "Invalid key"})
        with mock.patch.object(bland.requests, "request", return_value=answer):
            with self.assertRaisesRegex(bland.BlandError, "klíč nepřijal"):
                bland.account("x")
        answer = SimpleNamespace(status_code=400, json=lambda: {  # the free credit, a number outside the US
            "status": "error", "message": "International calling requires a completed purchase. Adding a card by "
                                          "itself does not enable it"})
        with mock.patch.object(bland.requests, "request", return_value=answer):
            with self.assertRaisesRegex(bland.BlandError, "až po zaplaceném nákupu kreditu"):
                bland.start_call("k", "+420602123456", "úkol", "Ahoj")
        answer = SimpleNamespace(status_code=200, json=lambda: {"status": "success", "call_id": "abc-123"})
        with mock.patch.object(bland.requests, "request", return_value=answer) as request:
            self.assertEqual(bland.start_call("k", "+420602123456", "úkol", "Ahoj", voice="", summary_prompt="s"),
                             "abc-123")
        payload = request.call_args.kwargs["json"]
        self.assertEqual((payload["language"], payload["record"], payload["voicemail"]),
                         ("cs", False, {"action": "hangup"}))
        self.assertNotIn("voice", payload)
        self.assertEqual(request.call_args.kwargs["headers"]["authorization"], "k")


if __name__ == "__main__":
    unittest.main()
