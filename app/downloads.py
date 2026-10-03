"""What isn't in the installer and gets downloaded on first use: Whisper models and Piper voices, from Hugging Face
into the data folder. Plus which model suits this PC's graphics card.

No Qt: callers run download() in a worker thread. A download resumes where it stopped (a .part file next to the
target, HTTP Range), is checked (SHA-256 pinned here, at a pinned revision of the repository, and confirmed by the
hash Hugging Face sends in X-Linked-Etag) and only then renamed into place, so a file under its real name is always
complete.
"""
import ctypes
import functools
import hashlib
import logging
import os
import re
import shutil
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import MODELS_DIR

log = logging.getLogger(__name__)

PIPER_DIR = MODELS_DIR / "piper"
_WHISPER = "https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/"
_PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/cs/cs_CZ/"
CHUNK = 1 << 20
SPARE = 300 * 2 ** 20  # free space left on the disk after a download
RETRIES = 3  # a dropped connection is resumed this many times before giving up
LARGE_VRAM = int(5.5 * 2 ** 30)  # dedicated graphics memory for large-v3 (a "6 GB" card reports a bit less)


class DownloadError(Exception):
    pass


class Cancelled(DownloadError):
    pass


@dataclass(frozen=True)
class Remote:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Item:
    """One thing to download (a model, or a voice = its .onnx and .onnx.json) into `folder`."""
    key: str
    label: str
    folder: Path
    files: tuple[Remote, ...]

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)

    def present(self) -> bool:
        return all((self.folder / f.name).is_file() for f in self.files)


def _voice(key: str, label: str, onnx: tuple[int, str], meta: tuple[int, str]) -> Item:
    path = _PIPER + key.split("-")[1] + "/medium/" + key
    return Item(key, label, PIPER_DIR, (Remote(f"{key}.onnx.json", f"{path}.onnx.json", *meta),
                                        Remote(f"{key}.onnx", f"{path}.onnx", *onnx)))


ITEMS = {item.key: item for item in (
    Item("ggml-large-v3.bin", "model large-v3", MODELS_DIR, (Remote(
        "ggml-large-v3.bin", _WHISPER + "ggml-large-v3.bin", 3095033483,
        "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2"),)),
    Item("ggml-large-v3-turbo.bin", "model large-v3-turbo", MODELS_DIR, (Remote(
        "ggml-large-v3-turbo.bin", _WHISPER + "ggml-large-v3-turbo.bin", 1624555275,
        "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"),)),
    _voice("cs_CZ-jirka-medium", "hlas Jirka",
           (63201294, "cbd5c900acacc8e8cbecd64347abb8de39c00a9d3104bed06fee92e4f319efc8"),
           (5025, "fb38b1799b7354808227c065efa97b1ffa2b0cde59505babb56a36d35af9c637")),
    _voice("cs_CZ-kasandra-medium", "hlas Kasandra",
           (63511038, "09d08aa23691ed2d53fb3db242cfe82b189adf9c1812dd5fe928b5789ed76df7"),
           (3232, "5039f9e49def4f4f8438db031868800a13bf4c6246b62afdb0947f4c5478770e")),
)}
WHISPER_MODELS = ("ggml-large-v3.bin", "ggml-large-v3-turbo.bin")


def size_text(size: float) -> str:
    """3,1 GB / 63 MB / 5 kB, in thousands like Hugging Face shows them"""
    for unit, scale in (("TB", 10 ** 12), ("GB", 10 ** 9), ("MB", 10 ** 6), ("kB", 10 ** 3)):
        if size >= scale * 0.95 or unit == "kB":
            value = size / scale
            text = f"{value:.1f}" if value < 10 else f"{value:.0f}"
            return f"{text.replace('.', ',')} {unit}"
    return ""


# --- downloading ---------------------------------------------------------------------------------

def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Orbit (Windows dictation; model download)"
    return s


def _expected(http: requests.Session, remote: Remote) -> str | None:
    """Asks Hugging Face what the file is: X-Linked-Etag is the SHA-256 for big (LFS) files, the git blob SHA-1 for
    small ones. Returns the git SHA-1 to check too, if any. Raises when it says something else than this table."""
    try:
        r = http.head(remote.url, allow_redirects=False, timeout=20)
    except requests.RequestException:
        raise DownloadError("Nepodařilo se spojit s huggingface.co. Jsi připojený k internetu?")
    if r.status_code >= 400:
        raise DownloadError(f"Server huggingface.co odpověděl chybou {r.status_code}.")
    etag = r.headers.get("X-Linked-Etag", "").strip().removeprefix("W/").strip('"').lower()
    size = r.headers.get("X-Linked-Size")
    if (len(etag) == 64 and etag != remote.sha256) or (size and int(size) != remote.size):
        raise DownloadError(f"Soubor {remote.name} na serveru je jiný, než Orbit čeká. Stahování jsem zastavil.")
    return etag if re.fullmatch(r"[0-9a-f]{40}", etag) else None


def _hash_file(path: Path, hasher, cancel: threading.Event) -> None:
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            if cancel.is_set():
                raise Cancelled("Zrušeno.")
            hasher.update(chunk)


def _check_space(folder: Path, need: int) -> None:
    free = shutil.disk_usage(folder).free
    if free < need + SPARE:
        drive = Path(folder).anchor or str(folder)
        raise DownloadError(f"Na disku {drive} je volných jen {size_text(free)}, potřeba je {size_text(need + SPARE)}. "
                            "Uvolni místo a zkus to znovu.")


def fetch(remote: Remote, folder: Path, progress=None, cancel: threading.Event | None = None) -> Path:
    """Blocking: downloads one file into folder (resuming a .part from before) and checks it.
    progress(done, total) in bytes. Raises DownloadError (a Czech message) or Cancelled."""
    cancel = cancel or threading.Event()
    progress = progress or (lambda done, total: None)
    target = folder / remote.name
    if target.is_file():
        return target
    folder.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    http = _session()
    git_sha1 = _expected(http, remote)
    for attempt in range(RETRIES + 1):
        have = part.stat().st_size if part.exists() else 0
        if have > remote.size:
            part.unlink()
            have = 0
        _check_space(folder, remote.size - have)
        hasher = hashlib.sha256()
        if have:
            _hash_file(part, hasher, cancel)
        progress(have, remote.size)
        try:
            hasher = _get(http, remote, part, have, hasher, progress, cancel)
            break
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            if attempt == RETRIES:
                raise DownloadError("Spojení se opakovaně přerušilo. Zkus to znovu, naváže to, kde skončilo.")
            log.warning("Stahování %s přerušeno (%s), navazuji", remote.name, e)
            time.sleep(2 + 3 * attempt)
    if hasher.hexdigest() != remote.sha256:
        part.unlink(missing_ok=True)
        raise DownloadError(f"Stažený soubor {remote.name} je poškozený (nesedí kontrolní součet). Zkus to znovu.")
    if git_sha1:  # a small file: Hugging Face's own hash of it, too
        blob = hashlib.sha1(b"blob %d\0" % remote.size)
        _hash_file(part, blob, cancel)
        if blob.hexdigest() != git_sha1:
            part.unlink(missing_ok=True)
            raise DownloadError(f"Stažený soubor {remote.name} nesedí s tím na serveru. Zkus to znovu.")
    for attempt in range(10):
        try:
            os.replace(part, target)
            break
        except PermissionError:  # an antivirus scans the fresh file
            if attempt == 9:
                raise DownloadError(f"Soubor {target} nejde uložit, drží ho jiný program.")
            time.sleep(0.5)
    log.info("Staženo: %s (%s)", target, size_text(remote.size))
    return target


def _get(http: requests.Session, remote: Remote, part: Path, have: int, hasher, progress, cancel):
    """Downloads the rest of the file onto the .part (or all of it again when the server can't resume). Returns the
    hash of the whole .part."""
    if have == remote.size:
        return hasher
    headers = {"Range": f"bytes={have}-"} if have else {}
    with http.get(remote.url, headers=headers, stream=True, timeout=(20, 60)) as r:
        if have and r.status_code == 200:  # the server ignored the range: start over
            have, hasher = 0, hashlib.sha256()
        elif r.status_code not in (200, 206):
            raise DownloadError(f"Server huggingface.co odpověděl chybou {r.status_code}.")
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_content(CHUNK):
                if cancel.is_set():
                    raise Cancelled("Zrušeno.")
                f.write(chunk)
                hasher.update(chunk)
                have += len(chunk)
                progress(have, remote.size)
    if have != remote.size:
        raise requests.ConnectionError(f"jen {have} z {remote.size} bajtů")
    return hasher


def download(key: str, progress=None, cancel: threading.Event | None = None) -> None:
    """Blocking: every missing file of ITEMS[key]; progress(done, total) over all of them."""
    item = ITEMS[key]
    progress = progress or (lambda done, total: None)
    done = 0
    for remote in item.files:
        fetch(remote, item.folder, lambda have, _, base=done: progress(base + have, item.size), cancel)
        done += remote.size
    progress(item.size, item.size)


# --- which model for this PC ---------------------------------------------------------------------

@dataclass(frozen=True)
class Gpu:
    name: str
    vram: int  # dedicated memory in bytes

    @property
    def vram_text(self) -> str:
        return f"{round(self.vram / 2 ** 30)} GB" if self.vram >= 2 ** 30 else size_text(self.vram)


class _Luid(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _AdapterDesc1(ctypes.Structure):
    _fields_ = [("Description", wintypes.WCHAR * 128), ("VendorId", wintypes.UINT), ("DeviceId", wintypes.UINT),
                ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT), ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t), ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", _Luid), ("Flags", wintypes.UINT)]


class _Guid(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _com(obj: ctypes.c_void_p, index: int, *argtypes):
    """Method `index` of a COM object's vtable."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[index])


@functools.cache
def gpus() -> tuple[Gpu, ...]:
    """Graphics cards (DXGI, no driver tools needed), most dedicated memory first. Software adapters (Microsoft
    Basic Render Driver) are left out."""
    found = []
    factory = ctypes.c_void_p()
    iid = _Guid(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    try:
        if ctypes.WinDLL("dxgi").CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0:
            return ()
        for i in range(16):
            adapter = ctypes.c_void_p()
            # IDXGIFactory1::EnumAdapters1 (3 IUnknown + 4 IDXGIObject + 5 IDXGIFactory methods before it)
            if _com(factory, 12, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))(factory, i, ctypes.byref(adapter)):
                break  # DXGI_ERROR_NOT_FOUND: no more adapters
            desc = _AdapterDesc1()
            # IDXGIAdapter1::GetDesc1 (3 + 4 + 3 before it)
            ok = _com(adapter, 10, ctypes.POINTER(_AdapterDesc1))(adapter, ctypes.byref(desc)) == 0
            _com(adapter, 2)(adapter)  # Release
            if ok and not desc.Flags & 2:  # DXGI_ADAPTER_FLAG_SOFTWARE
                found.append(Gpu(desc.Description.strip(), int(desc.DedicatedVideoMemory)))
    except (OSError, AttributeError):
        log.exception("Zjištění grafické karty selhalo")
    finally:
        if factory:
            _com(factory, 2)(factory)
    return tuple(sorted(found, key=lambda g: -g.vram))


@functools.cache
def vulkan() -> bool:
    """Is the Vulkan loader there (whisper-server needs it for the graphics card)? Missing in VMs and with the basic
    display driver."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LoadLibraryExW.restype = ctypes.c_void_p
    kernel32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
    handle = kernel32.LoadLibraryExW("vulkan-1.dll", None, 0x800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
    if handle:
        kernel32.FreeLibrary(handle)
    return bool(handle)


@dataclass(frozen=True)
class Advice:
    model: str
    gpu: Gpu | None  # the card that will do the work, None = the processor
    text: str  # what Orbit found, for the user
    slow: bool = False  # no usable card: it will be slow


def advise() -> Advice:
    """large-v3 with at least ~6 GB of dedicated graphics memory, turbo with less, turbo on the processor (slow)."""
    cards = gpus()
    gpu = cards[0] if cards and vulkan() else None
    if gpu is None:
        why = "Grafickou kartu s Vulkanem jsem nenašel" if not cards else f"{cards[0].name} nemá Vulkan"
        return Advice("ggml-large-v3-turbo.bin", None, f"{why}: přepis poběží na procesoru a bude pomalý (i krátká "
                      "věta pár sekund). Doporučuju menší model turbo.", slow=True)
    if gpu.vram >= LARGE_VRAM:
        return Advice("ggml-large-v3.bin", gpu, f"Grafika: {gpu.name}, {gpu.vram_text} paměti. Stačí na nejpřesnější "
                      "model.")
    return Advice("ggml-large-v3-turbo.bin", gpu, f"Grafika: {gpu.name}, {gpu.vram_text} paměti. Na nejpřesnější "
                  "model to je málo, doporučuju menší model turbo.")
