"""Autopilot (Pepa, 13 Oct 2026): a running Claude Code session works on its own, a round at a time, and after each
round Orbit calls the user's phone (Bland AI, bland.py): what the session did, what it proposes, what it wants to know.
What the user says on the call is the next round's prompt, which starts right after the call; calls come at most once
per the chosen interval (the session waits for the next one in between), never at night unless asked, and a call
nobody picks up is tried again an interval later (the session waits for the user: Pepa's choice).

How the session gets its prompts: the mod orbit-mozek (0.4.0+) in it looks into <data>/sessions/prompt/ every 2 s and
submits <session>.<id>.json as the user's own words ($.prompt.submit), answering <session>.<id>.done.json. A round is
over when the session's Stop comes after the prompt (the hooks, sessions.py); its last answer is the report, of which
the part under "Hlášení pro telefon" (the prompt asks for it) goes to the call.

Kept in <data>/autopilot.json, so an Orbit restart neither forgets a session on autopilot nor a call in progress.
No Qt here: main.py calls tick() with the tracked sessions every second and shows the events as bubbles."""
import json
import logging
import os
import re
import secrets
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path

from . import bland
from .config import DATA_DIR, SESSIONS_DIR

log = logging.getLogger(__name__)

STATE_PATH = DATA_DIR / "autopilot.json"
PROMPT_DIR = SESSIONS_DIR / "prompt"
ACK_WAIT_S = 7.0  # the session's mod looks every 2 s: no answer by then = it runs without orbit-mozek 0.4
STOP_WAIT_S = 15.0  # Claude Code says "idle" a moment before its Stop hook (async) brings the answer: waited for
POLL_CALL_S = 8.0  # Bland is asked about a running call this often
CALL_GIVE_UP_S = 20 * 60  # still running by Bland's word after this long: taken as failed
INTERVALS = {1800: "30 min", 3600: "1 h", 7200: "2 h", 10800: "3 h"}
DEFAULT_INTERVAL = 3600
QUIET_FROM, QUIET_TO = 22, 7  # no calls between these hours (the "quiet" setting): moved to the morning
REPORT_HEAD = "Hlášení pro telefon"
END_MARK = "AUTOPILOT: KONEC"
REPORT_MAX = 3500  # characters of the report Bland's agent gets
TRANSCRIPT_MAX = 12000
GOAL_MAX = 4000
KEEP_CALLS = 20
_SESSION_ID = re.compile(r"^[\w-]{1,128}$")

STAGES = {"sending": "předávám zadání", "working": "pracuje", "waiting": "čeká na hovor", "calling": "volá",
          "paused": "stojí"}
RESULTS = {"answered": "proběhl", "unanswered": "nikdo to nezvedl", "failed": "nepovedl se", "": "probíhá"}

SUMMARY_PROMPT = ("Napiš česky jednou až třemi větami, co uživatel v hovoru chce, aby relace dělala dál. Když chce "
                  "autopilota ukončit, napiš to jako první větu.")


def clock_text(when: float) -> str:
    """15:05 today, otherwise with the day: 14. 10. 7:00."""
    t = datetime.fromtimestamp(when)
    day = "" if t.date() == datetime.now().date() else f"{t.day}. {t.month}. "
    return f"{day}{t.hour}:{t.minute:02d}"


@dataclass
class Call:
    at: float
    round: int
    id: str = ""  # Bland's call id
    result: str = ""  # "" while it runs; answered / unanswered / failed
    summary: str = ""  # Bland's summary: what the user wants next
    transcript: str = ""
    minutes: float = 0.0
    price: float = 0.0  # USD
    error: str = ""


@dataclass
class Pilot:
    session_id: str
    title: str
    folder: str
    goal: str
    interval_s: int = DEFAULT_INTERVAL
    started: float = 0.0
    round: int = 1
    stage: str = "sending"  # see STAGES
    request: str = ""  # the prompt handed to the session's mod, until it answers
    text: str = ""  # that prompt (sent again when the user resumes after the mod didn't take it)
    sent_at: float = 0.0
    report: str = ""  # the last round's report
    next_call: float = 0.0
    last_call: float = 0.0
    resume: str = ""  # paused: what "Pokračovat" does, "send" (the prompt again) or "call"
    note: str = ""  # why it stands, or what the session waits for
    calls: list = field(default_factory=list)  # Call, newest last

    def label(self) -> str:
        """Next to the session's name in the panel, after a phone."""
        if self.stage == "waiting":
            return clock_text(self.next_call)
        if self.stage == "calling":
            return "volá"
        if self.stage == "paused":
            return "stojí"
        return f"kolo {self.round}"

    def describe(self) -> str:
        """For the session's tooltip and the Autopilot window."""
        every = INTERVALS.get(self.interval_s, f"{self.interval_s // 60} min")
        if self.stage == "waiting":
            text = f"Autopilot: kolo {self.round} je hotové, zavolám v {clock_text(self.next_call)}."
        elif self.stage == "calling":
            text = f"Autopilot: volám ti kvůli kolu {self.round}."
        elif self.stage == "paused":
            text = f"Autopilot stojí: {self.note}" if self.note else "Autopilot stojí."
        elif self.stage == "sending":
            text = f"Autopilot: předávám relaci zadání kola {self.round}…"
        else:
            text = f"Autopilot: pracuje na kole {self.round}" + (f" ({self.note})." if self.note else ".")
        return f"{text} Volám nejvýš jednou za {every}."


def report_text(message: str) -> str:
    """What of the session's last answer is said on the phone: the part from "Hlášení pro telefon" (the whole answer
    without it), as plain sentences: no code, no links, no Markdown marks."""
    at = message.find(REPORT_HEAD)
    text = message[at:].split("\n", 1)[1] if at >= 0 and "\n" in message[at:] else message
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+?(?=[.,;:!?)]?(?:\s|$))", "odkaz", text)
    # paths aren't for the ear: `app/import.py`, C:\x\y.txt (a word in backticks stays: `Comgate`)
    text = re.sub(r"`([^`\n]*)`", lambda m: "" if re.search(r"[\\/]|\.\w{1,5}$", m.group(1)) else m.group(1), text)
    text = re.sub(r"(?<![\w/\\])(?:[A-Za-z]:[\\/])?(?:[\w.-]+[\\/])+[\w.-]+\.\w{1,5}\b", "", text)
    text = re.sub(r"[`*_#>|]+", "", text)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    text = "\n".join(" ".join(line.split()) for line in text.splitlines())
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text if len(text) <= REPORT_MAX else text[:REPORT_MAX].rsplit(" ", 1)[0] + "…"


_REPORT_FORMAT = f"""Na konci tahu napiš hlášení přesně v tomhle tvaru, česky a stručně, jako bys to říkal do telefonu \
(bez kódu, cest k souborům a odkazů, nejvýš 12 vět):
## {REPORT_HEAD}
Co jsem udělal: …
Stav: pokračuju / hotovo / potřebuju rozhodnutí
Návrhy, jak dál: 1) … 2) … (2–3 možnosti řešení, u každé jedna věta proč; první je tvoje doporučení)
Otázka: … (co potřebuješ od uživatele vědět)"""


def first_prompt(goal: str) -> str:
    goal = goal.strip() or "Pokračuj v tom, na čem v téhle relaci pracuješ."
    return f"""[Autopilot Orbitu] Pouštím tě na autopilota: pracuj sám, po kolech. Tohle je kolo 1.

Cíl: {goal}

Udělej k cíli podstatný kus práce a o drobnostech se rozhoduj sám, rozumně. Jsem mimo počítač: po každém kole mi \
Orbit zavolá na telefon, přečte mi tvoje hlášení a moji odpověď ti pošle jako další zadání. Nic ode mě v okně relace \
nechtěj a na odpověď v tomhle tahu nečekej.

{_REPORT_FORMAT}"""


def next_prompt(pilot: Pilot, call: Call, name: str) -> str:
    goal = pilot.goal.strip() or "pokračovat v tom, na čem v téhle relaci pracuješ"
    summary = f"\nShrnutí hovoru: {call.summary}\n" if call.summary else ""
    return f"""[Autopilot Orbitu] Kolo {pilot.round}. Cíl: {goal}

Na tvoje minulé hlášení přišla po telefonu moje odpověď. Přepis hovoru („{name}“ jsem já, „Orbit“ hlasový asistent, \
který mi volal; přepis může mít chyby z rozpoznávání řeči):
<<<
{call.transcript or "(prázdný)"}
>>>
{summary}
Pokračuj podle toho, co v hovoru zaznělo ode mě. Když z něj plyne, že má autopilot skončit, už nic nedělej a odpověz \
jen: {END_MARK}

Jinak pracuj dál jako v minulých kolech. {_REPORT_FORMAT}"""


def call_task(pilot: Pilot, name: str) -> str:
    """What Bland's voice agent is told to do on the call."""
    who = name or "uživatel"
    return f"""Jsi Orbit, hlasový asistent. Voláš z počítače člověku jménem {who}, protože jeho relace Claude Code \
„{pilot.title}“ (složka {pilot.folder}) běží na autopilotu a dokončila kolo {pilot.round}. Mluv česky, tykej, \
přirozeně a stručně jako kolega. Nepoužívej tvary, ze kterých je poznat rod.

Postup:
1. V první větě už jsi řekl, o kterou relaci jde; neopakuj to.
2. Shrň nejvýš třemi větami, co se udělalo.
3. Řekni návrhy, jak pokračovat, i doporučení relace.
4. Řekni otázku relace a zeptej se, co má dělat dál. Poslouchej. Když něčemu nerozumíš, doptej se. Na otázky \
odpovídej jen z hlášení níže; co v něm není, nevíš: řekni, že to relace zjistí v dalším kole.
5. Nakonec jednou větou zopakuj, co relaci předáš, a rozluč se. Když chce autopilota ukončit, potvrď, že ho ukončíš.
Hovor ať je co nejkratší. Nic neslibuj, nic neobjednávej, nikdy neříkej ani nechtěj hesla, kódy ani čísla karet.

Hlášení relace:
{pilot.report or "Relace kolo dokončila bez hlášení."}"""


def first_sentence(pilot: Pilot) -> str:
    title = pilot.title if len(pilot.title) <= 60 else pilot.title[:59].rsplit(" ", 1)[0] + "…"
    return f"Ahoj, tady Orbit. Volám kvůli relaci {title}, má hotové kolo {pilot.round}."


class Autopilot:
    def __init__(self, settings, path: Path = STATE_PATH, prompt_dir: Path = PROMPT_DIR, caller=bland,
                 clock=time.time, pool=None):
        """settings: () -> {"phone", "key", "voice", "name", "quiet"} as they are now; caller: bland (or a fake)."""
        self.settings, self.path, self.prompt_dir, self.caller, self.clock = settings, path, prompt_dir, caller, clock
        self.pilots: dict[str, Pilot] = {}
        self.events: list[tuple[str, str, str, str]] = []  # (bubble kind, session id, title, text), for main
        self._pool = pool or ThreadPoolExecutor(max_workers=2, thread_name_prefix="autopilot")
        self._jobs: dict[str, tuple[str, Future]] = {}  # session id -> (start / details, Bland's request)
        self._polled: dict[str, float] = {}  # session id -> when Bland was last asked about its call
        self._quiet: dict[str, float] = {}  # session id -> since when its turn looks over without an answer
        self._other: list[tuple[str, Future]] = []  # a test call, the account check
        self._saved = self._snapshot()  # nothing on the Autopilot yet: no file written for it
        self.load()

    # -- keeping it --------------------------------------------------------------------------------------------

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            log.exception("Autopilot: %s nejde přečíst", self.path.name)
            return
        names = {f.name for f in fields(Pilot)}
        call_names = {f.name for f in fields(Call)}
        for raw in data.get("pilots", []) if isinstance(data, dict) else []:
            try:
                pilot = Pilot(**{k: v for k, v in raw.items() if k in names})
                pilot.calls = [Call(**{k: v for k, v in c.items() if k in call_names}) for c in pilot.calls]
            except (TypeError, AttributeError):
                continue
            if _SESSION_ID.match(pilot.session_id) and pilot.stage in STAGES:
                self.pilots[pilot.session_id] = pilot
        self._saved = self._snapshot()
        for pilot in self.pilots.values():  # what the last run left half done
            if pilot.stage == "calling" and not (pilot.calls and pilot.calls[-1].id):
                pilot.stage, pilot.next_call = "waiting", self.clock()  # Bland's answer never came: call again
            elif pilot.stage == "sending" and pilot.request and not \
                    (self.prompt_dir / f"{pilot.session_id}.{pilot.request}.done.json").exists():
                self._remove_request(pilot)  # the mod leaves a request older than a minute alone: a new one
                self._send(pilot, pilot.text)

    def _snapshot(self) -> str:
        return json.dumps({"pilots": [asdict(p) for p in self.pilots.values()]}, ensure_ascii=False, indent=1)

    def save(self) -> None:
        snapshot = self._snapshot()
        if snapshot == self._saved:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(snapshot, encoding="utf-8")
            os.replace(tmp, self.path)
            self._saved = snapshot
        except OSError:
            log.exception("Autopilot: stav nejde uložit")

    # -- what the user does ------------------------------------------------------------------------------------

    def start(self, session, goal: str, interval_s: int = DEFAULT_INTERVAL) -> str:
        """The session on autopilot: round 1 goes to it now. "" = started, otherwise why not (for the window)."""
        cfg = self.settings()
        if not cfg.get("phone") or not cfg.get("key"):
            return "Nejdřív nahoře vyplň svoje telefonní číslo a klíč Bland AI."
        if not _SESSION_ID.match(session.id):
            return "Tuhle relaci neznám."
        if session.id in self.pilots:
            return "Tahle relace už na autopilotu je."
        pilot = Pilot(session.id, session.name, session.folder, goal.strip()[:GOAL_MAX],
                      interval_s if interval_s in INTERVALS else DEFAULT_INTERVAL, started=self.clock())
        self.pilots[session.id] = pilot
        self._send(pilot, first_prompt(pilot.goal))
        log.info("Autopilot: relace ve složce %s, interval %s, cíl %d znaků", pilot.folder,
                 INTERVALS[pilot.interval_s], len(pilot.goal))
        self.save()
        return ""

    def stop(self, session_id: str, why: str = "") -> None:
        pilot = self.pilots.pop(session_id, None)
        if pilot is None:
            return
        if pilot.request:
            self._remove_request(pilot)
        self._jobs.pop(session_id, None)  # (a running request finishes in its thread, its result is dropped)
        self._quiet.pop(session_id, None)
        log.info("Autopilot ve složce %s vypnutý%s", pilot.folder, f": {why}" if why else "")
        self.save()

    def call_now(self, session_id: str) -> None:
        """The next call right away (no interval, no night), or, when it stands, what it stood at once more."""
        pilot = self.pilots.get(session_id)
        if pilot is None or session_id in self._jobs:
            return
        if pilot.stage == "paused" and pilot.resume == "send":
            self._send(pilot, pilot.text)
        elif pilot.stage in ("waiting", "paused"):
            pilot.stage, pilot.next_call, pilot.note, pilot.resume = "waiting", self.clock(), "", ""
        self.save()

    def test_call(self) -> str:
        """A short call that only says the Autopilot works. "" = Bland is calling, otherwise why not."""
        cfg = self.settings()
        if not cfg.get("phone") or not cfg.get("key"):
            return "Vyplň telefonní číslo a klíč Bland AI."
        task = ("Jsi Orbit, hlasový asistent. Tohle je zkušební hovor z Autopilota Orbitu. Mluv česky a tykej. Řekni, "
                "že Autopilot funguje a že po každém kole práce relace Claude Code takhle zavolá s hlášením. Zeptej "
                "se, jestli je tě dobře slyšet a rozumět, krátce odpověz a rozluč se. Hovor ať trvá do minuty.")
        self._other.append(("test", self._pool.submit(
            self.caller.start_call, cfg["key"], cfg["phone"], task, "Ahoj, tady Orbit. Tohle je zkušební hovor.",
            cfg.get("voice", ""))))
        return ""

    def check_account(self, key: str) -> None:
        """Does the key work, and how much credit is left: an "account" event."""
        self._other.append(("account", self._pool.submit(self.caller.account, key)))

    # -- every second ------------------------------------------------------------------------------------------

    def tick(self, sessions: dict) -> None:
        """Moves each session on autopilot on (sessions: the tracker's, by id)."""
        now = self.clock()
        self._collect(now)
        for sid, pilot in list(self.pilots.items()):
            s = sessions.get(sid)
            if s is None:
                self.stop(sid, "relace skončila")
                self.events.append(("info", sid, pilot.title, "Relace skončila, autopilot je vypnutý."))
                continue
            pilot.title = s.name or pilot.title
            # one stage after another: a round that ends now is called about now
            if pilot.stage == "sending":
                self._ack(pilot, now)
            if pilot.stage == "working":
                self._round_over(pilot, s, now)
            if sid not in self.pilots:
                continue  # it ended
            if pilot.stage == "waiting" and now >= pilot.next_call and sid not in self._jobs:
                self._call(pilot, now)
            elif pilot.stage == "calling" and sid not in self._jobs and pilot.calls and pilot.calls[-1].id \
                    and now - self._polled.get(sid, 0) >= POLL_CALL_S:
                self._ask_about_call(pilot, now)
        self._collect(now)  # what came back quickly (a refused call) is told now, not in a second
        self.save()

    def drain_events(self) -> list[tuple[str, str, str, str]]:
        """(kind, session id, title, text): a bubble for "info", "done", "waiting", "error"; for the window "test",
        "account" (the credit, "" = not known) and their "-error"s."""
        events, self.events = self.events, []
        return events

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # -- the session's side ------------------------------------------------------------------------------------

    def _send(self, pilot: Pilot, text: str) -> None:
        """Hands the session its prompt through its mod: the answer comes in _ack."""
        pilot.request, pilot.text, pilot.sent_at = secrets.token_hex(4), text, self.clock()
        pilot.stage, pilot.note, pilot.resume = "sending", "", ""
        try:
            self.prompt_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.prompt_dir / f"{pilot.session_id}.{pilot.request}.tmp"
            tmp.write_text(json.dumps({"session_id": pilot.session_id, "id": pilot.request, "time": pilot.sent_at,
                                       "text": text}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.prompt_dir / f"{pilot.session_id}.{pilot.request}.json")
        except OSError:
            log.exception("Autopilot: zadání pro relaci nejde zapsat")
            pilot.request = ""
            self._pause(pilot, "zadání pro relaci nejde zapsat do datové složky.", "send")

    def _remove_request(self, pilot: Pilot) -> None:
        for suffix in ("json", "done.json"):
            try:
                (self.prompt_dir / f"{pilot.session_id}.{pilot.request}.{suffix}").unlink(missing_ok=True)
            except OSError:
                pass
        pilot.request = ""

    def _ack(self, pilot: Pilot, now: float) -> None:
        answer = self.prompt_dir / f"{pilot.session_id}.{pilot.request}.done.json"
        try:
            reply = json.loads(answer.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if now - pilot.sent_at < ACK_WAIT_S:
                return
            reply = None
        except (OSError, ValueError):
            return  # being written
        self._remove_request(pilot)
        if reply is None:
            log.info("Autopilot: relace ve složce %s zadání nepřevzala (bez modu orbit-mozek 0.4)", pilot.folder)
            self._pause(pilot, "relace zadání nepřevzala. Potřebuje mod orbit-mozek 0.4 nebo novější: v jejím okně "
                               "napiš /reload-plugins (nebo ji restartuj) a klikni na Pokračovat.", "send")
        elif isinstance(reply, dict) and reply.get("ok") is True:
            pilot.stage = "working"
        else:
            why = str(reply.get("text") if isinstance(reply, dict) else "") or "bez důvodu"
            self._pause(pilot, f"relace zadání nepřijala ({why[:200]}).", "send")

    def _round_over(self, pilot: Pilot, s, now: float) -> None:
        """The session's turn after the prompt has ended: its last answer is the report, then the call."""
        if s.state == "waiting":
            pilot.note = "čeká na schválení v okně relace"
            return
        pilot.note = ""
        if s.state not in ("done", "idle", "error") or s.since < pilot.sent_at - 1:
            self._quiet.pop(pilot.session_id, None)
            return
        message = s.message or ""
        if not message and s.state != "error":
            # idle by Claude Code's list of sessions, the Stop with the answer not here yet (on 13. 10. it came 1 ms
            # later and the call had no report); an interrupted turn (Esc) has no Stop at all: it goes on after a while
            if now - self._quiet.setdefault(pilot.session_id, now) < STOP_WAIT_S:
                return
        self._quiet.pop(pilot.session_id, None)
        if END_MARK in message[:300]:
            self.stop(pilot.session_id, "ukončen v hovoru")
            self.events.append(("done", pilot.session_id, pilot.title, "Autopilot je vypnutý, jak sis v hovoru řekl."))
            return
        report = report_text(message)
        pilot.report = f"Relace skončila chybou: {report}" if s.state == "error" else report
        pilot.stage = "waiting"
        pilot.next_call = self._when(max(now, pilot.last_call + pilot.interval_s))
        log.info("Autopilot ve složce %s: kolo %d hotové, hlášení %d znaků", pilot.folder, pilot.round,
                 len(pilot.report))
        if pilot.next_call - now > 60:
            self.events.append(("info", pilot.session_id, pilot.title,
                                f"Kolo {pilot.round} je hotové, zavolám ti v {clock_text(pilot.next_call)}."))

    def _when(self, at: float) -> float:
        """`at`, or with the quiet nights on, 7:00 when it falls into the night."""
        if not self.settings().get("quiet", True):
            return at
        t = datetime.fromtimestamp(at)
        if QUIET_TO <= t.hour < QUIET_FROM:
            return at
        morning = t.replace(hour=QUIET_TO, minute=0, second=0, microsecond=0)
        return (morning if t.hour < QUIET_TO else morning + timedelta(days=1)).timestamp()

    def _pause(self, pilot: Pilot, why: str, resume: str) -> None:
        pilot.stage, pilot.note, pilot.resume = "paused", why, resume
        self.events.append(("error", pilot.session_id, pilot.title, f"Autopilot stojí: {why}"))

    # -- the phone's side --------------------------------------------------------------------------------------

    def _call(self, pilot: Pilot, now: float) -> None:
        cfg = self.settings()
        if not cfg.get("phone") or not cfg.get("key"):
            self._pause(pilot, "chybí telefonní číslo nebo klíč Bland AI (vyplň je v okně Autopilot).", "call")
            return
        pilot.calls = (pilot.calls + [Call(at=now, round=pilot.round)])[-KEEP_CALLS:]
        pilot.stage = "calling"
        self._jobs[pilot.session_id] = ("start", self._pool.submit(
            self.caller.start_call, cfg["key"], cfg["phone"], call_task(pilot, cfg.get("name", "")),
            first_sentence(pilot), cfg.get("voice", ""), SUMMARY_PROMPT))

    def _ask_about_call(self, pilot: Pilot, now: float) -> None:
        self._polled[pilot.session_id] = now
        key = self.settings().get("key", "")
        self._jobs[pilot.session_id] = ("details", self._pool.submit(self.caller.details, key, pilot.calls[-1].id))

    def _collect(self, now: float) -> None:
        """What Bland answered meanwhile (the requests run in threads)."""
        for sid, (kind, job) in list(self._jobs.items()):
            if not job.done():
                continue
            del self._jobs[sid]
            pilot = self.pilots.get(sid)
            if pilot is None or pilot.stage != "calling" or not pilot.calls:
                continue  # switched off meanwhile
            call = pilot.calls[-1]
            try:
                result = job.result()
            except bland.BlandError as e:
                if kind == "start":
                    call.result, call.error = "failed", str(e)
                    log.info("Autopilot ve složce %s: Bland AI nezavolal", pilot.folder)
                    self._pause(pilot, f"nezavolal jsem: {e}", "call")
                elif now - call.at > CALL_GIVE_UP_S:
                    call.result, call.error = "failed", str(e)
                    self._pause(pilot, f"o hovoru se od Bland AI nic nedozvím: {e}", "call")
                continue  # a failed question about a running call: asked again
            except Exception as e:
                log.exception("Autopilot: požadavek na Bland AI selhal")
                if kind == "start":
                    call.result, call.error = "failed", str(e)
                    self._pause(pilot, f"nezavolal jsem: {e}", "call")
                continue
            if kind == "start":
                call.id = str(result)
                self._polled[sid] = now
            else:
                self._call_details(pilot, call, result if isinstance(result, dict) else {}, now)
        for kind, job in list(self._other):
            if not job.done():
                continue
            self._other.remove((kind, job))
            try:
                result = job.result()
            except Exception as e:
                if not isinstance(e, bland.BlandError):
                    log.exception("Autopilot: požadavek na Bland AI selhal")
                self.events.append((f"{kind}-error", "", "", str(e)))
                continue
            if kind == "test":
                self.events.append(("test", "", "", "Bland AI ti volá, za chvíli zazvoní telefon."))
            else:
                balance = (result.get("billing") or {}).get("current_balance") if isinstance(result, dict) else None
                self.events.append(("account", "", "", f"{balance}" if isinstance(balance, (int, float)) else ""))

    def _call_details(self, pilot: Pilot, call: Call, details: dict, now: float) -> None:
        result = self.caller.outcome(details)
        if result is None:
            if now - call.at <= CALL_GIVE_UP_S:
                return
            result, call.error = "failed", "Bland AI hovor pořád hlásí jako probíhající."
        name = self.settings().get("name") or "Uživatel"
        call.result = result
        call.summary = " ".join(str(details.get("summary") or "").split())[:1000]
        call.transcript = self.caller.transcript(details, name)[:TRANSCRIPT_MAX]
        call.minutes = _number(details.get("call_length"))
        call.price = _number(details.get("price"))
        call.error = call.error or str(details.get("error_message") or "")[:300]
        pilot.last_call = now
        log.info("Autopilot ve složce %s: hovor %s, %.1f min", pilot.folder, result, call.minutes)
        if result == "answered":
            pilot.round += 1
            self._send(pilot, next_prompt(pilot, call, name))
            self.events.append(("done", pilot.session_id, pilot.title,
                                f"Hovor skončil, relace pokračuje kolem {pilot.round}."))
        elif result == "unanswered":
            pilot.stage, pilot.next_call = "waiting", self._when(now + pilot.interval_s)
            self.events.append(("waiting", pilot.session_id, pilot.title,
                                f"Hovor nikdo nezvedl. Relace počká, zkusím to znovu v "
                                f"{clock_text(pilot.next_call)}."))
        else:
            self._pause(pilot, f"hovor se nepovedl ({call.error or 'Bland AI neřekl proč'}).", "call")


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
