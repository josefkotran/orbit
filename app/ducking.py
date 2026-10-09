"""Music and other sound quieter while the microphone is open (the setting "Hudba při diktování"): every other
program's audio session on every active output gets muted or turned down (what the Windows volume mixer shows per
app), and right after the recording back to what it was. Pepa asked for it on 8 Oct; Superwhisper and Aqua Voice do
the same. Less music in the microphone also means fewer of Whisper's made-up words.

Only what Orbit changed is put back, and only while it's still what Orbit set (the user may have changed it in the
mixer meanwhile). What was changed is written to <data>/ducked.json before it's changed: if Orbit dies in the middle
of a dictation, its next start puts it back. Orbit's own sounds (its process) and Windows' system sounds stay.

Core Audio through ctypes (IMMDeviceEnumerator → IAudioSessionManager2 → ISimpleAudioVolume), in a worker thread of
its own, so a slow audio driver never holds up the microphone. No Qt here."""
import ctypes
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from ctypes import POINTER, byref, c_float, c_int, c_long, c_uint, c_void_p
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

KEEP, LOWER, MUTE = "keep", "lower", "mute"  # the setting's values
LOWER_TO = 0.2  # "Ztiší se": a fifth of each program's own volume (about -14 dB)


@dataclass
class Change:
    id: str  # the session's instance identifier (this run of that program)
    group: str  # the session identifier (the program, the same after it restarts): a leftover after a crash
    pid: int
    mode: str  # LOWER or MUTE
    before: float  # its volume (LOWER), or 1.0 when it was muted (MUTE)
    set: float  # what Orbit set


def plan(sessions, mode: str, keep_pids: set[int]) -> list[Change]:
    """What to change: every program's session but Orbit's own (keep_pids) and Windows' system sounds; not one that's
    muted or silent already (that's the user's)."""
    changes = []
    for s in sessions:
        if s.system or s.pid in keep_pids or s.muted or s.volume < 0.02:
            continue
        if mode == MUTE:
            changes.append(Change(s.id, s.group, s.pid, MUTE, 0.0, 1.0))
        elif mode == LOWER:
            changes.append(Change(s.id, s.group, s.pid, LOWER, s.volume, round(s.volume * LOWER_TO, 4)))
    return changes


def apply(session, change: Change) -> None:
    if change.mode == MUTE:
        session.set_mute(True)
    else:
        session.set_volume(change.set)


def undo(session, change: Change) -> bool:
    """Back to what it was, unless the user changed it meanwhile. True when it was put back."""
    if change.mode == MUTE:
        if not session.muted:  # unmuted by hand: leave it
            return False
        session.set_mute(False)
        return True
    if abs(session.volume - change.set) > 0.01:  # moved by hand: leave it
        return False
    session.set_volume(change.before)
    return True


# --- Core Audio through ctypes ----------------------------------------------------------------

class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _GUID:
    g = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(g))
    return g


CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAudioSessionManager2 = "{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}"
IID_IAudioSessionControl2 = "{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}"
IID_ISimpleAudioVolume = "{87CE5498-68D6-44E5-9215-6DA47EF883D8}"
CLSCTX_ALL, E_RENDER, DEVICE_STATE_ACTIVE = 0x17, 0, 1


def _method(obj: c_void_p, index: int, *argtypes, restype=ctypes.HRESULT):
    """A COM object's method by its place in the vtable (an HRESULT raises OSError when it fails)."""
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    return lambda *args: ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtable[index])(obj, *args)


def _release(obj: c_void_p) -> None:
    if obj:
        _method(obj, 2, restype=wintypes.ULONG)()


def _query(obj: c_void_p, iid: str) -> c_void_p:
    out = c_void_p()
    _method(obj, 0, POINTER(_GUID), POINTER(c_void_p))(byref(_guid(iid)), byref(out))
    return out


def _string(obj: c_void_p, index: int) -> str:
    out = c_void_p()
    _method(obj, index, POINTER(c_void_p))(byref(out))
    try:
        return ctypes.wstring_at(out.value) if out.value else ""
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


class _Session:
    """One program's audio session on one output (ISimpleAudioVolume)."""

    def __init__(self, control2: c_void_p, volume: c_void_p):
        self._volume = volume
        pid = wintypes.DWORD()
        _method(control2, 14, POINTER(wintypes.DWORD))(byref(pid))  # GetProcessId
        self.pid = pid.value
        self.system = _method(control2, 15, restype=c_long)() == 0  # IsSystemSoundsSession: S_OK = yes
        self.group = _string(control2, 12)  # GetSessionIdentifier
        self.id = _string(control2, 13)  # GetSessionInstanceIdentifier

    @property
    def volume(self) -> float:
        out = c_float()
        _method(self._volume, 4, POINTER(c_float))(byref(out))
        return out.value

    @property
    def muted(self) -> bool:
        out = wintypes.BOOL()
        _method(self._volume, 6, POINTER(wintypes.BOOL))(byref(out))
        return bool(out.value)

    def set_volume(self, value: float) -> None:
        _method(self._volume, 3, c_float, c_void_p)(max(0.0, min(1.0, value)), None)

    def set_mute(self, on: bool) -> None:
        _method(self._volume, 5, wintypes.BOOL, c_void_p)(bool(on), None)


class CoreAudio:
    """The sessions of every active output. sessions() hands them to a function and lets go of them after."""

    _local = threading.local()

    @classmethod
    def _com(cls) -> None:
        if not getattr(cls._local, "ready", False):
            ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED, once per thread
            cls._local.ready = True

    def sessions(self, use) -> None:
        self._com()
        held: list[c_void_p] = []

        def keep(obj: c_void_p) -> c_void_p:
            held.append(obj)
            return obj
        try:
            enumerator = keep(c_void_p())
            ctypes.oledll.ole32.CoCreateInstance(byref(_guid(CLSID_MMDeviceEnumerator)), None, CLSCTX_ALL,
                                                 byref(_guid(IID_IMMDeviceEnumerator)), byref(enumerator))
            devices = keep(c_void_p())
            _method(enumerator, 3, c_int, wintypes.DWORD, POINTER(c_void_p))(E_RENDER, DEVICE_STATE_ACTIVE,
                                                                             byref(devices))
            count = c_uint()
            _method(devices, 3, POINTER(c_uint))(byref(count))
            found = []
            for i in range(count.value):
                device, manager, sessions = keep(c_void_p()), keep(c_void_p()), keep(c_void_p())
                try:
                    _method(devices, 4, c_uint, POINTER(c_void_p))(i, byref(device))
                    _method(device, 3, POINTER(_GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p))(
                        byref(_guid(IID_IAudioSessionManager2)), CLSCTX_ALL, None, byref(manager))
                    _method(manager, 5, POINTER(c_void_p))(byref(sessions))  # GetSessionEnumerator
                    n = c_int()
                    _method(sessions, 3, POINTER(c_int))(byref(n))
                except OSError:
                    log.debug("Výstup zvuku %d nejde projít", i, exc_info=True)
                    continue
                for j in range(n.value):
                    try:
                        control = keep(c_void_p())
                        _method(sessions, 4, c_int, POINTER(c_void_p))(j, byref(control))
                        control2 = keep(_query(control, IID_IAudioSessionControl2))
                        volume = keep(_query(control, IID_ISimpleAudioVolume))
                        found.append(_Session(control2, volume))
                    except OSError:
                        log.debug("Zvuková relace %d nejde přečíst", j, exc_info=True)
            use(found)
        finally:
            for obj in reversed(held):
                try:
                    _release(obj)
                except OSError:
                    pass


class Ducker:
    """duck() when the microphone opens, restore() when it closes; both run one after another in a thread of their
    own (the calls return at once)."""

    def __init__(self, state: Path, audio=None):
        self._state = state
        self._audio = audio or CoreAudio()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ducking")
        self._changes: list[Change] = []

    def duck(self, mode: str, keep_pids: set[int]) -> None:
        if mode in (LOWER, MUTE):
            self._pool.submit(self._run, self._duck, mode, set(keep_pids))

    def restore(self) -> None:
        self._pool.submit(self._run, self._restore)

    def restore_leftover(self) -> None:
        """At start: what a run that ended in the middle of a dictation left muted or turned down."""
        self._pool.submit(self._run, self._leftover)

    def shutdown(self) -> None:
        """Quitting: back to normal before Orbit goes (waits for it)."""
        self.restore()
        self._pool.shutdown(wait=True)

    @staticmethod
    def _run(fn, *args) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("Ztlumení zvuku při diktování selhalo")

    def _duck(self, mode: str, keep_pids: set[int]) -> None:
        if self._changes:  # still ducked (a recording right after another): what's quiet stays quiet
            return

        def use(sessions):
            changes = plan(sessions, mode, keep_pids)
            if not changes:
                return
            self._save(changes)  # first written down, then changed: a crash can't lose the way back
            by_id = {s.id: s for s in sessions}
            for change in changes:
                try:
                    apply(by_id[change.id], change)
                    self._changes.append(change)
                except OSError:
                    log.debug("Relaci %d nejde ztlumit", change.pid, exc_info=True)
            log.info("Při diktování ztlumeno: %d programů (%s)", len(self._changes), mode)
        self._audio.sessions(use)

    def _restore(self, changes: list[Change] | None = None, leftover: bool = False) -> None:
        changes = self._changes if changes is None else changes
        if not changes:
            return

        def use(sessions):
            by_id = {s.id: s for s in sessions}
            by_group = {s.group: s for s in sessions} if leftover else {}
            back = 0
            for change in changes:
                session = by_id.get(change.id) or by_group.get(change.group)
                if session is None:  # the program has ended meanwhile
                    continue
                try:
                    back += undo(session, change)
                except OSError:
                    log.debug("Relaci %d nejde vrátit", change.pid, exc_info=True)
            log.info("Zvuk po diktování vrácen: %d z %d programů", back, len(changes))
        try:
            self._audio.sessions(use)
        finally:
            self._changes = []
            self._state.unlink(missing_ok=True)

    def _leftover(self) -> None:
        try:
            data = json.loads(self._state.read_text(encoding="utf-8"))
            changes = [Change(**item) for item in data.get("changes", [])]
        except FileNotFoundError:
            return
        except Exception:
            log.exception("Záznam o ztlumení zvuku nejde přečíst")
            self._state.unlink(missing_ok=True)
            return
        log.info("Vracím zvuk, který zůstal ztlumený z minulého běhu (%d programů)", len(changes))
        self._restore(changes, leftover=True)

    def _save(self, changes: list[Change]) -> None:
        self._state.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state.with_name(self._state.name + ".tmp")
        tmp.write_text(json.dumps({"changes": [asdict(c) for c in changes]}), encoding="utf-8")
        os.replace(tmp, self._state)
