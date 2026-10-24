"""Phone calls through Bland AI (https://www.bland.ai) for the Autopilot (autopilot.py): Bland calls the user's phone,
its voice agent talks with them in Czech by the instructions it's given (the session's report, what to ask), and when
the call is over its transcript is asked for. Nothing has to reach this PC from the internet: Orbit only polls.

The API key is the user's own (v2.app.bland.ai › Settings › API key). It's kept in config.json encrypted for the
user's Windows account (DPAPI: protect / unprotect), never in plain text, and never logged; neither is the phone
number (masked) nor what was said."""
import base64
import ctypes
import logging
import re
from ctypes import wintypes

import requests

log = logging.getLogger(__name__)

API = "https://api.bland.ai/v1"
KEY_PAGE = "https://v2.app.bland.ai/settings"  # where the user creates the API key (as the reel showed)
TIMEOUT_S = 20
LANGUAGE = "cs"
MAX_MINUTES = 10  # Bland ends a call that runs this long


class BlandError(Exception):
    """Why Bland didn't do it, in Czech for the user."""


# -- the API key, encrypted for the Windows account --------------------------------------------------------------

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt(fn, data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in, blob_out = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    # no UI (CRYPTPROTECT_UI_FORBIDDEN): never a dialog from a background thread
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
        raise OSError(ctypes.GetLastError(), "DPAPI")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def protect(secret: str) -> str:
    """The key as config.json keeps it: encrypted for this Windows account ("" for "")."""
    if not secret:
        return ""
    return "dpapi:" + base64.b64encode(_crypt(ctypes.windll.crypt32.CryptProtectData, secret.encode())).decode()


def unprotect(stored: str) -> str:
    """The key back ("" when there is none, or it can't be read: another Windows account, another PC)."""
    if not stored.startswith("dpapi:"):
        return ""
    try:
        return _crypt(ctypes.windll.crypt32.CryptUnprotectData, base64.b64decode(stored[6:])).decode()
    except (OSError, ValueError):
        log.warning("Klíč Bland AI nejde rozšifrovat (jiný účet Windows nebo jiný počítač)")
        return ""


# -- phone numbers ----------------------------------------------------------------------------------------------

def normalize_phone(text: str) -> str | None:
    """+420602123456 from "602 123 456", "+420 602 123 456", "00420602123456"; None when it isn't a number Bland can
    call (E.164: a + and 8-15 digits). Nine digits alone are a Czech number."""
    digits = re.sub(r"[\s\-./()]", "", text or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if re.fullmatch(r"\d{9}", digits):
        digits = "+420" + digits
    return digits if re.fullmatch(r"\+[1-9]\d{7,14}", digits) else None


def masked(phone: str) -> str:
    """For the log: "…456"."""
    return "…" + phone[-3:] if phone else "?"


# -- the API ----------------------------------------------------------------------------------------------------

def _request(method: str, path: str, key: str, payload: dict | None = None) -> dict:
    try:
        r = requests.request(method, f"{API}{path}", json=payload, timeout=TIMEOUT_S,
                             headers={"authorization": key, "content-type": "application/json"})
    except requests.RequestException as e:
        raise BlandError(f"Bland AI teď není dostupný ({type(e).__name__}). Je počítač připojený k internetu?") from e
    try:
        body = r.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    if r.status_code in (401, 403):
        raise BlandError("Bland AI klíč nepřijal. Zkontroluj ho v Autopilotovi (v2.app.bland.ai › Settings › API key).")
    if r.status_code == 402:
        raise BlandError("Na účtu Bland AI došel kredit. Dobij ho na v2.app.bland.ai (hovory do Česka chtějí "
                         "nákup aspoň za 5 $).")
    if r.status_code == 429:
        raise BlandError("Bland AI odmítl hovor: moc požadavků naráz. Zkus to za chvíli.")
    said = _message(body)
    if "international calling" in said.lower():  # "…requires a completed purchase. Adding a card by itself does not…"
        raise BlandError("Bland AI volá mimo USA a Kanadu až po zaplaceném nákupu kreditu: kredit zdarma ani samotná "
                         "karta nestačí. Na v2.app.bland.ai v Billing kup kredit (nebo zapni auto-recharge), a až se "
                         "platba připíše, zkus to znovu.")
    if r.status_code >= 400 or body.get("status") == "error":
        raise BlandError(f"Bland AI odpověděl chybou {r.status_code}: {said or 'bez popisu'}")
    return body


def _message(body: dict) -> str:
    """Bland's own words about an error (they come in a few shapes)."""
    for key in ("message", "error", "errors"):
        value = body.get(key)
        if isinstance(value, list):
            value = "; ".join(str(v.get("message", v) if isinstance(v, dict) else v) for v in value[:3])
        if isinstance(value, dict):
            value = value.get("message") or str(value)
        if value:
            return str(value)[:300]
    return ""


def account(key: str) -> dict:
    """{"status", "billing": {"current_balance"}, "total_calls"}: the key works (BlandError when it doesn't)."""
    return _request("GET", "/me", key)


def start_call(key: str, phone: str, task: str, first_sentence: str, voice: str = "",
               summary_prompt: str = "") -> str:
    """Bland calls the phone and talks by `task`; its id (BlandError when it won't call)."""
    payload = {
        "phone_number": phone,
        "task": task,
        "first_sentence": first_sentence,
        "language": LANGUAGE,
        "max_duration": MAX_MINUTES,
        "wait_for_greeting": True,  # a Czech "Haló?" first, then Orbit speaks
        "record": False,  # nothing kept that isn't needed: the transcript is enough
        "voicemail": {"action": "hangup"},  # a voicemail isn't the user: hang up, the Autopilot tries again later
        "metadata": {"orbit": "autopilot"},
    }
    if voice:
        payload["voice"] = voice
    if summary_prompt:
        payload["summary_prompt"] = summary_prompt[:2000]
    body = _request("POST", "/calls", key, payload)
    call_id = str(body.get("call_id") or "")
    if not call_id:
        raise BlandError(f"Bland AI hovor nezaložil: {_message(body) or 'odpověď bez čísla hovoru'}")
    log.info("Bland AI volá %s", masked(phone))
    return call_id


def details(key: str, call_id: str) -> dict:
    """The call as Bland has it now: completed, status, answered_by, transcripts, summary, call_length, price…"""
    if not re.fullmatch(r"[\w-]{4,80}", call_id):
        raise BlandError("Neplatné číslo hovoru.")
    return _request("GET", f"/calls/{call_id}", key)


def outcome(call: dict) -> str | None:
    """What became of a call: "answered" (the user talked), "unanswered" (no answer, busy, a voicemail, picked up and
    silent), "failed" (Bland's error), or None while it still runs."""
    status = str(call.get("status") or "").lower()
    queue = str(call.get("queue_status") or "").lower()
    if queue.endswith("_error") or status == "failed" and not call.get("completed"):
        return "failed"
    if not call.get("completed") and status not in ("completed", "no-answer", "busy", "canceled", "failed"):
        return None
    if status in ("no-answer", "busy", "canceled") or call.get("answered_by") in ("voicemail", "no-answer"):
        return "unanswered"
    said = any(isinstance(t, dict) and t.get("user") == "user" and str(t.get("text") or "").strip()
               for t in call.get("transcripts") or [])
    if not said:
        said = bool(re.search(r"(?m)^\s*user:\s*\S", str(call.get("concatenated_transcript") or "")))
    return "answered" if said else "unanswered"


def transcript(call: dict, name: str = "Uživatel") -> str:
    """The conversation as lines "Uživatel: …" / "Orbit: …" (what the session gets)."""
    lines = []
    for t in call.get("transcripts") or []:
        if not isinstance(t, dict) or t.get("user") not in ("user", "assistant"):
            continue
        text = " ".join(str(t.get("text") or "").split())
        if text:
            lines.append(f"{name if t['user'] == 'user' else 'Orbit'}: {text}")
    if lines:
        return "\n".join(lines)
    text = str(call.get("concatenated_transcript") or "")
    return re.sub(r"(?m)^\s*assistant:", "Orbit:", re.sub(r"(?m)^\s*user:", f"{name}:", text)).strip()
