"""Claude plan usage: the 5-hour and the weekly limit (what Claude Code's /usage shows).

Two sources (config "usage_source"):
- "statusline" (the default): Orbit's status line in Claude Code (app/cc_status.py) leaves the limits Claude Code
  reports after each answer in <data>/sessions/status/; the newest of them count. Official, needs nothing else, but
  only Pro and Max report limits, and only once a session has had an answer. No per-model weekly limit there.
- "oauth" (opt-in, not in the settings window; kept for configs from before the status line): reads the OAuth token
  Claude Code keeps in .credentials.json in its folder and asks the internal usage endpoint. The token is only read,
  never refreshed here – Claude Code refreshes it itself whenever it runs. Since 10 Oct only on top of what the
  sessions themselves report (combined): the endpoint answers 429 for up to an hour when the account asks it often,
  and Claude Code's sessions ask it themselves too.
The sessions' own figures come from <data>/sessions/status/: <id>.json from Orbit's status line, <id>.mod.json from the
orbit-mozek mod (mods/, the engine hands it the limits after each turn), both read alike.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from . import paths
from .config import CACHE_DIR, SESSIONS_DIR

log = logging.getLogger(__name__)

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
STATUS_DIR = SESSIONS_DIR / "status"
SOURCES = ("statusline", "oauth")
STATUS_KEEP_S = 8 * 86400  # status files older than this (past any weekly window) are deleted
NO_DATA = "Limity se ukážou po první zprávě v Claude Code."
NOT_REPORTED = "Claude Code limity tvého účtu nehlásí (hlásí je jen předplatné Pro a Max)."
WINDOWS = (("five_hour", "session"), ("seven_day", "weekly_all"))  # status line key -> kind


class UsageError(Exception):
    pass


@dataclass
class Limit:
    kind: str
    label: str  # short, for the panel
    title: str  # long, for the tooltip
    percent: float
    resets_at: datetime | None
    at: datetime | None = None  # when it was reported (a session's answer, the endpoint's answer)


@dataclass
class Usage:
    limits: list[Limit]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""  # instead of the bars when there are none yet
    action: str = ""  # with the note, a link in the panel: "statusline" = the user's yes to Orbit's status line
    source: str = "oauth"
    updated_at: datetime | None = None  # status line: when Claude Code last reported them

    def get(self, kind: str) -> Limit | None:
        return next((lim for lim in self.limits if lim.kind == kind), None)


def _parse_time(value) -> datetime | None:
    """ISO text (the endpoint) or Unix seconds (the status line)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not value or not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _describe(kind: str, scope) -> tuple[str, str]:
    model = ((scope or {}).get("model") or {}).get("display_name")
    if kind == "session":
        return "5 h", "5hodinové okno"
    if kind == "weekly_all":
        return "Týden", "Týden – všechny modely"
    if model:
        return model, f"Týden – {model}"
    return kind, kind


def fetch(source: str = "statusline", force: bool = False) -> Usage:
    return combined(force) if source == "oauth" else from_status_line()


# --- the status line ----------------------------------------------------------------------------

_pruned_at = 0.0


def from_status_line(now: float | None = None) -> Usage:
    """The newest limits any session's status line reported (a window that has reset since doesn't count)."""
    global _pruned_at
    now = time.time() if now is None else now
    newest: dict[str, tuple[float, float, datetime | None]] = {}  # kind -> (reported at, percent, resets at)
    seen_limits = answered = False
    try:
        files = list(STATUS_DIR.glob("*.json"))
    except OSError:
        files = []
    prune = now - _pruned_at > 3600
    for f in files:
        try:
            if prune and f.stat().st_mtime < now - STATUS_KEEP_S:
                f.unlink(missing_ok=True)
                continue
            record = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        reported = float(record.get("time") or 0)
        window = record.get("context_window") if isinstance(record.get("context_window"), dict) else {}
        answered = answered or bool(window.get("current_usage"))
        limits = record.get("rate_limits") if isinstance(record.get("rate_limits"), dict) else {}
        for key, kind in WINDOWS:
            item = limits.get(key) if isinstance(limits.get(key), dict) else {}
            pct = item.get("used_percentage")
            if not isinstance(pct, (int, float)) or isinstance(pct, bool):
                continue
            seen_limits = True
            resets = _parse_time(item.get("resets_at"))
            if resets is not None and resets.timestamp() <= now:
                continue  # that window is over: the next answer brings the new one
            if kind not in newest or reported > newest[kind][0]:
                newest[kind] = (reported, float(pct), resets)
    if prune:
        _pruned_at = now
    result = []
    for _, kind in WINDOWS:
        if kind in newest:
            label, title = _describe(kind, None)
            result.append(Limit(kind, label, title, newest[kind][1], newest[kind][2],
                                datetime.fromtimestamp(newest[kind][0], timezone.utc)))
    note = "" if result else NOT_REPORTED if answered and not seen_limits else NO_DATA
    updated = max((t for t, _, _ in newest.values()), default=0.0)
    return Usage(result, note=note, source="statusline",
                 updated_at=datetime.fromtimestamp(updated, timezone.utc) if updated else None)


# --- the OAuth usage endpoint (opt-in) ------------------------------------------------------------

def parse(data: dict, at: datetime | None = None) -> Usage:
    at = at or datetime.now(timezone.utc)
    limits = []
    for item in data.get("limits") or []:
        if not isinstance(item, dict) or item.get("percent") is None:
            continue
        label, title = _describe(item.get("kind", ""), item.get("scope"))
        limits.append(Limit(item.get("kind", ""), label, title, float(item["percent"]),
                            _parse_time(item.get("resets_at")), at))
    if not limits:  # older response shape
        for key, kind in (("five_hour", "session"), ("seven_day", "weekly_all")):
            if isinstance(data.get(key), dict):
                label, title = _describe(kind, None)
                limits.append(Limit(kind, label, title, float(data[key]["utilization"]),
                                    _parse_time(data[key].get("resets_at")), at))
    return Usage(limits, fetched_at=at, source="oauth")


_retry_at = 0.0  # after a 429: no asking before this
# The last answer and the 429 pause, kept over a restart of Orbit: every start asked at once, a few restarts in a row
# got a 429 and a fresh Orbit then had no limits to show for 5 minutes and more (9 Oct).
OAUTH_CACHE = CACHE_DIR / "usage-oauth.json"
OAUTH_FRESH_S = 110  # an answer this new is shown again instead of asking (Orbit asks every 2 minutes)
OAUTH_SHOW_S = 3600  # while asking isn't possible, an answer up to this old is shown (marked as not current)
TOO_OFTEN = "Claude teď odpovídá, že se ptáme moc často. Zkusím to za pár minut."


class Limited(UsageError):
    """Not asked now (a 429 earlier); last = the last answer, when there is a recent one."""

    def __init__(self, message: str, last: Usage | None):
        super().__init__(message)
        self.last = last


def _cache() -> dict:
    try:
        data = json.loads(OAUTH_CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _keep(**changes) -> None:
    data = dict(_cache(), **changes)
    try:
        OAUTH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = OAUTH_CACHE.with_name(OAUTH_CACHE.name + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(OAUTH_CACHE)
    except OSError:
        pass  # only a cache


def _cached(max_age: float) -> Usage | None:
    """The kept answer if it's at most max_age seconds old."""
    data = _cache()
    at = data.get("at")
    if not isinstance(at, (int, float)) or not isinstance(data.get("answer"), dict) or \
            not 0 <= time.time() - at <= max_age:
        return None
    try:
        return parse(data["answer"], datetime.fromtimestamp(at, timezone.utc))
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def fetch_oauth() -> Usage:
    global _retry_at
    kept = _cache().get("retry_at")
    if isinstance(kept, (int, float)):
        _retry_at = max(_retry_at, min(kept, time.time() + 3600))
    if time.time() < _retry_at:
        raise Limited(TOO_OFTEN, _cached(OAUTH_SHOW_S))
    if usage := _cached(OAUTH_FRESH_S):  # Orbit restarted right after it asked: that answer still holds
        return usage
    try:
        creds = json.loads((paths.claude_dir() / ".credentials.json").read_text(encoding="utf-8"))["claudeAiOauth"]
        token = creds["accessToken"]
    except FileNotFoundError:
        raise UsageError("Claude Code není na tomhle počítači přihlášený.")
    except (KeyError, TypeError, ValueError, OSError):
        raise UsageError("Nerozumím souboru s přihlášením Claude Code.")

    try:
        r = requests.get(USAGE_URL, timeout=10, headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
        })
    except requests.RequestException:
        raise UsageError("Nepodařilo se spojit s Claude.")
    if r.status_code == 401:
        raise UsageError("Přihlášení vypršelo – stačí spustit Claude Code, ten ho obnoví.")
    if r.status_code == 429:
        try:
            wait = float(r.headers.get("Retry-After") or 0)
        except ValueError:
            wait = 0
        _retry_at = time.time() + min(max(wait, 300), 3600)
        _keep(retry_at=_retry_at)
        raise Limited(TOO_OFTEN, _cached(OAUTH_SHOW_S))
    if r.status_code != 200:
        raise UsageError(f"Claude odpověděl chybou {r.status_code}.")
    try:
        answer = r.json()
        usage = parse(answer)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise UsageError("Odpovědi Clauda o využití nerozumím.")
    _keep(at=time.time(), answer=answer, retry_at=0)
    return usage


# --- both: the sessions' own figures, the endpoint on top (usage_source "oauth") ----------------------------------

OAUTH_EVERY_S = 1800  # with the sessions' figures at hand the endpoint is asked this rarely (any outcome counts),
# and only when a session reported something since: while Claude Code isn't used the limits don't move (10 Oct)
OAUTH_ALONE_S = 300  # without them, the endpoint alone
OAUTH_EXTRA_S = 12 * 3600  # what only the endpoint has (a model's weekly limit, Fable) from an answer up to this old
_failed: UsageError | None = None  # the endpoint's last try in this run, when it failed


def _merge(local: Usage, answer: Usage | None, now: float) -> Usage:
    """The 5-hour and the weekly limit from whichever reported them later, then the endpoint's other rows (Fable)."""
    def current(lim: Limit | None) -> Limit | None:
        return lim if lim and not (lim.resets_at and lim.resets_at.timestamp() <= now) else None

    rows = []
    for kind in ("session", "weekly_all"):
        found = [lim for lim in (current(local.get(kind)), current(answer.get(kind) if answer else None)) if lim]
        if found:
            rows.append(max(found, key=lambda lim: lim.at.timestamp() if lim.at else 0.0))
    if answer:
        rows += [lim for lim in answer.limits if lim.kind not in ("session", "weekly_all") and current(lim)]
    newest = max((lim.at for lim in rows if lim.at), default=None)
    return Usage(rows, fetched_at=newest or datetime.now(timezone.utc), source="combined",
                 updated_at=local.updated_at)


def combined(force: bool = False) -> Usage:
    """The limits as the sessions report them (no request at all: Orbit's status line or the orbit-mozek mod), with
    the OAuth endpoint asked on top at most every OAUTH_EVERY_S and only after Claude Code was used (force: now, the
    menu's "Obnovit"), for what only it has: a model's weekly limit (Fable) and work outside Claude Code (the
    browser, the phone). The endpoint's 429 lasts up to an hour and came again and again (10 Oct): with the sessions'
    figures the bars stay, only Fable's row gets older. Without them it's the endpoint alone every OAUTH_ALONE_S, and
    its errors are raised. (Orbit's own `claude -p` runs never ask the endpoint: checked with --debug-file, 10 Oct.)"""
    global _failed
    now = time.time()
    local = from_status_line(now)
    asked = _cache().get("asked_at")
    asked = asked if isinstance(asked, (int, float)) and asked <= now else 0.0  # kept over a restart of Orbit
    if local.limits:  # every half hour, and only when Claude Code was used since (or there's no answer to add)
        used = local.updated_at is not None and local.updated_at.timestamp() > asked
        due = now - asked >= OAUTH_EVERY_S and (used or _cached(OAUTH_EXTRA_S) is None)
    else:
        due = now - asked >= OAUTH_ALONE_S
        if _failed is None and _cached(OAUTH_SHOW_S) is None:
            due = True  # nothing to show at all (a restart after a long pause): ask now (a 429 pause still holds)
    due = due or force
    if due:
        _keep(asked_at=now)
        before = str(_failed or "")
        try:
            fetch_oauth()  # (its answer goes to the cache)
            _failed = None
        except UsageError as e:
            _failed = e
            if local.limits and str(e) != before:
                log.info("Endpoint využití Clauda: %s (5 h a týden dál z relací Claude Code)", e)
    if not local.limits:
        if _failed:
            raise _failed
        return _cached(OAUTH_SHOW_S) or Usage([], note="Načítám využití Clauda…")
    return _merge(local, _cached(OAUTH_EXTRA_S), now)


# --- forecast and texts ------------------------------------------------------------------------------

def forecast(samples: list[tuple[datetime, float]], resets_at: datetime | None) -> datetime | None:
    """When the limit runs out at the pace of the last 30 minutes – only if that's before it resets."""
    recent = [(t, p) for t, p in samples if t >= samples[-1][0] - timedelta(minutes=30)] if samples else []
    if len(recent) < 2:
        return None
    (t0, p0), (t1, p1) = recent[0], recent[-1]
    seconds = (t1 - t0).total_seconds()
    if seconds < 600 or p1 - p0 < 1:  # too short to tell, or it barely moves
        return None
    eta = t1 + timedelta(seconds=(100 - p1) * seconds / (p1 - p0))
    return eta if resets_at is None or eta < resets_at else None


def countdown(when: datetime | None) -> str:
    if when is None:
        return ""
    minutes = int((when - datetime.now(timezone.utc)).total_seconds() // 60)
    if minutes <= 0:
        return "teď"
    hours, minutes = divmod(minutes, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days} d {hours} h"
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


_DAYS = ["po", "út", "st", "čt", "pá", "so", "ne"]


def reset_text(when: datetime | None) -> str:
    if when is None:
        return ""
    local = when.astimezone()
    now = datetime.now().astimezone()
    if local.date() == now.date():
        day = "dnes"
    else:
        day = f"{_DAYS[local.weekday()]} {local.day}. {local.month}."
    return f"obnoví se {day} v {local.hour}:{local.minute:02d} (za {countdown(when)})"
