"""Claude plan usage (the same numbers Claude Code's /usage shows).

Reads the OAuth token Claude Code keeps in ~/.claude/.credentials.json and asks the usage endpoint.
The token is only read, never refreshed here – Claude Code refreshes it itself whenever it runs.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"


class UsageError(Exception):
    pass


@dataclass
class Limit:
    kind: str
    label: str  # short, for the panel
    title: str  # long, for the tooltip
    percent: float
    resets_at: datetime | None


@dataclass
class Usage:
    limits: list[Limit]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get(self, kind: str) -> Limit | None:
        return next((lim for lim in self.limits if lim.kind == kind), None)


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _describe(kind: str, scope) -> tuple[str, str]:
    model = ((scope or {}).get("model") or {}).get("display_name")
    if kind == "session":
        return "5 h", "5hodinové okno"
    if kind == "weekly_all":
        return "Týden", "Týden – všechny modely"
    if model:
        return model, f"Týden – {model}"
    return kind, kind


def parse(data: dict) -> Usage:
    limits = []
    for item in data.get("limits") or []:
        if item.get("percent") is None:
            continue
        label, title = _describe(item.get("kind", ""), item.get("scope"))
        limits.append(Limit(item.get("kind", ""), label, title, float(item["percent"]),
                            _parse_time(item.get("resets_at"))))
    if not limits:  # older response shape
        for key, kind in (("five_hour", "session"), ("seven_day", "weekly_all")):
            if data.get(key):
                label, title = _describe(kind, None)
                limits.append(Limit(kind, label, title, float(data[key]["utilization"]),
                                    _parse_time(data[key].get("resets_at"))))
    return Usage(limits)


def fetch() -> Usage:
    try:
        creds = json.loads(CREDENTIALS.read_text(encoding="utf-8"))["claudeAiOauth"]
    except FileNotFoundError:
        raise UsageError("Claude Code není na tomhle počítači přihlášený.")
    except (KeyError, ValueError):
        raise UsageError("Nerozumím souboru s přihlášením Claude Code.")

    try:
        r = requests.get(USAGE_URL, timeout=10, headers={
            "Authorization": f"Bearer {creds['accessToken']}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
        })
    except requests.RequestException:
        raise UsageError("Nepodařilo se spojit s Claude.")
    if r.status_code == 401:
        raise UsageError("Přihlášení vypršelo – stačí spustit Claude Code, ten ho obnoví.")
    if r.status_code != 200:
        raise UsageError(f"Claude odpověděl chybou {r.status_code}.")
    return parse(r.json())


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
