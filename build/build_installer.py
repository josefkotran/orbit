"""Builds Orbit's Windows installer: build/output/Orbit-Setup-<version>.exe.

The bundle (build/dist/Orbit) is exactly what the installer puts into %LOCALAPPDATA%\\Programs\\Orbit:
    runtime\\   Python 3.13 embeddable distribution, Orbit's packages in runtime\\Lib\\site-packages
    app\\, Orbit.pyw, assets\\ (static files only), whisper\\, THIRD_PARTY_NOTICES.md
It's started as runtime\\pythonw.exe Orbit.pyw. Models aren't in it, Orbit downloads them on first run.

    .venv\\Scripts\\python.exe build\\build_installer.py [--whisper-dir whisper-next] [--without-piper] [--no-installer]

Downloads (cached in build/cache, Inno Setup in build/tools) need internet the first time. See build/README.md.
"""
import argparse
import ctypes
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from build_whisper import download  # same folder: download with SHA256 check

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
CACHE = BUILD / "cache"
DIST = BUILD / "dist" / "Orbit"
OUTPUT = BUILD / "output"

PY_VERSION = "3.13.7"
PY_ZIP = f"python-{PY_VERSION}-embed-amd64.zip"
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/{PY_ZIP}"
PY_SHA256 = "f6cca216a359be84797cabb54149ce5e062afb16cc7567eb7fc51cacb2d86b65"  # MD5 matches python.org's listing

INNO_VERSION = "6.7.3"
INNO_EXE = f"innosetup-{INNO_VERSION}.exe"
INNO_URL = f"https://github.com/jrsoftware/issrc/releases/download/is-{INNO_VERSION.replace('.', '_')}/{INNO_EXE}"
INNO_SHA256 = "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"
INNO_DIR = BUILD / "tools" / "InnoSetup"

PIPER_PACKAGES = {"piper-tts", "onnxruntime"}  # GPL-3.0 Piper and its ONNX runtime: left out by --without-piper
GENERATED_ASSETS = ("*.wav", "chevron.png")  # made by Orbit at runtime (see .gitignore)

# PySide6 is ~640 MB; Orbit needs a small part. Qt modules come from what app/ imports, plus these plugins.
QT_ALWAYS = {"QtCore", "QtGui", "QtWidgets"}
QT_PLUGINS = {
    "platforms": {"qwindows.dll", "qoffscreen.dll"},  # offscreen: the bundle check builds the UI without a screen
    "styles": {"*"},  # the native Windows style Qt starts with (Orbit then switches to Fusion)
    "imageformats": {"qico.dll", "qsvg.dll", "qjpeg.dll", "qgif.dll"},  # PNG/BMP are built into QtGui
    "iconengines": {"qsvgicon.dll"},
}
QT_MODULE_PLUGINS = {
    "QtTextToSpeech": {"texttospeech": {"qtexttospeech_winrt.dll", "qtexttospeech_sapi.dll"}},
    "QtNetwork": {"tls": {"*"}, "networkinformation": {"*"}},
    "QtMultimedia": {"multimedia": {"*"}},
    "QtSql": {"sqldrivers": {"qsqlite.dll"}},
    "QtPositioning": {"position": {"*"}},
}
QT_DROP_DIRS = ("qml", "translations", "resources", "include", "typesystems", "glue", "scripts", "examples", "doc",
                "metatypes", "lib")

# Visual C++ runtime: a clean Windows doesn't have it, Python's embeddable zip brings only vcruntime140*.dll.
# PySide6 ships the rest; next to python.exe it's found by every extension (onnxruntime, numpy, …).
VC_RUNTIME = re.compile(r"^(msvcp140(_\w+)?|vcruntime140(_\d)?|concrt140|vcomp140|vccorlib140)\.dll$", re.I)
NOT_WINDOWS = re.compile(r"^(msvcp|vcruntime|concrt|vcomp|vccorlib|vcamp|mfc|ucrtbased|vulkan-1|opencl|nvcuda"
                         r"|libcrypto|libssl|python\d)", re.I)  # in System32 on a dev PC, but not on a clean one


# --- PE imports (which DLLs a .dll/.pyd/.exe needs) ---------------------------------------------------------------

def pe_imports(path: Path) -> tuple[list[str], list[str]]:
    """(normal imports, delay-loaded imports) of a PE file."""
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return [], []
    sections, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    dirs = opt + (112 if struct.unpack_from("<H", data, opt)[0] == 0x20B else 96)
    table = []
    for i in range(sections):
        vsize, va, raw_size, raw = struct.unpack_from("<IIII", data, opt + opt_size + 40 * i + 8)
        table.append((va, max(vsize, raw_size), raw))

    def offset(rva):
        return next((rva - va + raw for va, size, raw in table if va <= rva < va + size), None)

    def names(entry, size, name_at):
        rva = struct.unpack_from("<I", data, dirs + 8 * entry)[0]
        o, result = offset(rva) if rva else None, []
        while o is not None and o + size <= len(data):
            name_rva = struct.unpack_from("<I", data, o + name_at)[0]
            n = offset(name_rva) if name_rva else None
            if n is None:
                break
            result.append(data[n:data.index(b"\0", n)].decode("ascii", "replace"))
            o += size
        return result

    return names(1, 20, 12), names(13, 32, 4)


def missing_dlls(folder: Path) -> list[str]:
    """Imports that neither the bundle nor a clean Windows provides."""
    files = [p for p in folder.rglob("*") if p.suffix.lower() in (".dll", ".pyd", ".exe")]
    present = {p.name.lower() for p in files}
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    problems = []
    for f in files:
        imports, delayed = pe_imports(f)
        for name, optional in [(n, False) for n in imports] + [(n, True) for n in delayed]:
            low = name.lower()
            if low in present or low.startswith(("api-ms-win-", "ext-ms-")):
                continue
            if (system / name).exists() and not NOT_WINDOWS.match(name):
                continue
            if low == "vulkan-1.dll" and f.name.lower() == "ggml-vulkan.dll":
                continue  # comes with the GPU driver; without it ggml just skips this backend
            if not optional:
                problems.append(f"{f.relative_to(folder)} -> {name}")
    return sorted(problems)


# --- steps -----------------------------------------------------------------------------------------------------------

def read_version() -> str:
    text = (ROOT / "app" / "version.py").read_text(encoding="utf-8")
    m = re.search(r"""^VERSION\s*=\s*["']([^"']+)["']""", text, re.M)
    if not m:
        sys.exit("V app/version.py chybí VERSION = \"x.y.z\".")
    return m.group(1)


def make_runtime(runtime: Path) -> None:
    zip_path = CACHE / PY_ZIP
    download([PY_URL], zip_path, PY_SHA256)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(runtime)
    # the ._pth file replaces sys.path (and PYTHONPATH etc. are ignored): the stdlib zip, runtime\, its
    # site-packages and the app root (..) where Orbit.pyw and app\ are. No "import site": it would add the user's
    # own %APPDATA%\Python\Python313\site-packages (another numpy, another PySide6) to every start that lacks -s,
    # and Orbit itself starts this Python without it (the Run key, Claude Code's hooks and status line, the agent's
    # tool server). Nothing in the bundle needs site (no .pth files: checked by verify_bundle.py).
    (runtime / "python313._pth").write_text(
        "python313.zip\n.\nLib\\site-packages\n..\n", encoding="utf-8")


def install_packages(site: Path, without_piper: bool) -> None:
    reqs = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name = re.split(r"[<>=!~;\[\s]", line.strip(), maxsplit=1)[0].lower().replace("_", "-")
        if name and not name.startswith("#") and not (without_piper and name in PIPER_PACKAGES):
            reqs.append(line.strip())
    req_file = CACHE / "requirements-bundle.txt"
    req_file.write_text("\n".join(reqs) + "\n", encoding="utf-8")
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
           "--target", str(site), "--only-binary=:all:", "--platform", "win_amd64", "--python-version", "3.13",
           "--implementation", "cp", "-r", str(req_file)]
    if sys.version_info[:2] != (3, 13):
        cmd.append("--no-compile")  # .pyc made by another Python version would just be ignored
    print("pip install " + " ".join(reqs))
    subprocess.run(cmd, check=True)
    shutil.rmtree(site / "bin", ignore_errors=True)  # console scripts (pyside6-designer, …)


def used_qt_modules() -> set[str]:
    mods = set(QT_ALWAYS)
    for f in [ROOT / "Orbit.pyw", *(ROOT / "app").rglob("*.py")]:
        text = f.read_text(encoding="utf-8", errors="replace")
        mods |= set(re.findall(r"PySide6\.(Qt\w+)", text))
        for group in re.findall(r"from\s+PySide6\s+import\s+\(?([\w\s,]+)", text):
            mods |= {m.strip() for m in group.split(",") if m.strip().startswith("Qt")}
    return mods


def prune_pyside(site: Path) -> None:
    pyside = site / "PySide6"
    mods = used_qt_modules()
    print(f"Qt moduly: {', '.join(sorted(mods))}")
    for f in pyside.glob("*.pyd"):
        if f.stem.startswith("Qt") and f.stem not in mods:
            f.unlink()
    for pattern in ("*.pyi", "*.exe", "*.lib"):
        for f in pyside.glob(pattern):
            f.unlink()
    for d in QT_DROP_DIRS:
        shutil.rmtree(pyside / d, ignore_errors=True)

    keep = {k: set(v) for k, v in QT_PLUGINS.items()}
    for mod in mods:
        for folder, files in QT_MODULE_PLUGINS.get(mod, {}).items():
            keep.setdefault(folder, set()).update(files)
    for folder in (pyside / "plugins").iterdir():
        if folder.name not in keep:
            shutil.rmtree(folder)
            continue
        for f in folder.iterdir():
            if "*" not in keep[folder.name] and f.name not in keep[folder.name]:
                f.unlink()

    # keep the Qt DLLs the remaining modules and plugins need (directly or through each other)
    present = {p.name.lower(): p for p in pyside.glob("*.dll")}
    needed, todo = set(), [*pyside.glob("*.pyd"), *(pyside / "plugins").rglob("*.dll"), pyside / "pyside6.abi3.dll"]
    while todo:
        imports, delayed = pe_imports(todo.pop())
        for name in imports + delayed:
            dll = present.get(name.lower())
            if dll and dll not in needed:
                needed.add(dll)
                todo.append(dll)
    for dll in present.values():
        if dll not in needed and not VC_RUNTIME.match(dll.name):
            dll.unlink()


def prune_site(site: Path) -> None:
    for tests in list((site / "numpy").rglob("tests")):
        shutil.rmtree(tests, ignore_errors=True)
    shutil.rmtree(site / "shiboken6" / "include", ignore_errors=True)
    for f in (site / "shiboken6").glob("*.lib"):
        f.unlink()
    # PortAudio: only the 64-bit build without ASIO (Orbit records through MME; the ASIO builds contain
    # Steinberg's SDK, which has its own licence)
    for f in (site / "_sounddevice_data" / "portaudio-binaries").iterdir():
        if f.is_dir():
            shutil.rmtree(f)
        elif f.name not in ("libportaudio64bit.dll", "README.md"):
            f.unlink()


def file_version(path: Path) -> tuple[int, ...]:
    ver = ctypes.windll.version
    size = ver.GetFileVersionInfoSizeW(str(path), None)
    buf = ctypes.create_string_buffer(size)
    ptr, n = ctypes.c_void_p(), ctypes.c_uint()
    if not size or not ver.GetFileVersionInfoW(str(path), 0, size, buf) \
            or not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)):
        return ()
    ms, ls = struct.unpack_from("<II", ctypes.string_at(ptr.value, n.value), 8)  # VS_FIXEDFILEINFO
    return ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF


def copy_vc_runtime(site: Path, runtime: Path) -> None:
    """One consistent set next to python.exe: msvcp140 must not be newer than vcruntime140, so PySide6's newer
    vcruntime140*.dll also replaces the embeddable zip's (Python runs fine on a newer one)."""
    for dll in (site / "PySide6").glob("*.dll"):
        target = runtime / dll.name
        if VC_RUNTIME.match(dll.name) and (not target.exists() or file_version(dll) > file_version(target)):
            shutil.copy2(dll, target)


def copy_app(dist: Path, whisper_dir: Path) -> None:
    shutil.copytree(ROOT / "app", dist / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "Orbit.pyw", dist)
    shutil.copytree(ROOT / "assets", dist / "assets", ignore=shutil.ignore_patterns(*GENERATED_ASSETS))
    shutil.copytree(whisper_dir, dist / "whisper", ignore=shutil.ignore_patterns("*.log"))
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", dist)
    shutil.copytree(ROOT / "installer" / "licenses", dist / "licenses")  # (L)GPL texts the Qt/pynput wheels lack


def package_inventory(site: Path, out: Path) -> None:
    """Every installed Python package with its version and declared licence (the licence files themselves
    stay in each package's *.dist-info)."""
    rows = []
    for meta in sorted(site.glob("*.dist-info/METADATA")):
        fields = {}
        for line in meta.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                break  # the headers end at the first empty line
            key, _, value = line.partition(": ")
            if key in ("Name", "Version", "License-Expression", "License") and key not in fields:
                fields[key] = value.strip()
        lic = fields.get("License-Expression") or fields.get("License") or "viz dist-info"
        rows.append(f"{fields.get('Name', meta.parent.name)} {fields.get('Version', '')}: {lic[:100]}")
    out.write_text("Python packages in runtime\\Lib\\site-packages (licence files in each *.dist-info):\n\n"
                   + "\n".join(rows) + "\n", encoding="utf-8")


def verify(dist: Path) -> None:
    """Runs verify_bundle.py with the bundle's own Python, a minimal PATH and data folders in %TEMP%."""
    temp = Path(tempfile.mkdtemp(prefix="orbit-verify-"))
    (temp / "data").mkdir()
    (temp / "claude").mkdir()
    system = os.environ.get("SystemRoot", r"C:\Windows")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "QT_", "ORBIT_"))}
    env.update(PATH=f"{system}\\System32;{system};{system}\\System32\\Wbem", QT_QPA_PLATFORM="offscreen",
               QT_QPA_FONTDIR=f"{system}\\Fonts",  # the offscreen platform has no fonts of its own
               ORBIT_DATA_DIR=str(temp / "data"), ORBIT_CLAUDE_DIR=str(temp / "claude"))
    before = {p for p in dist.rglob("*")}
    # without -s, the way Orbit starts this Python itself (the check fails if sys.path leaves the bundle)
    r = subprocess.run([str(dist / "runtime" / "python.exe"), str(BUILD / "verify_bundle.py"), str(dist),
                        str(temp)], env=env, cwd=temp)
    # whatever the check generated inside the bundle (bytecode, sounds, logs) must not end up in the installer
    for p in sorted({p for p in dist.rglob("*")} - before, key=lambda p: len(p.parts), reverse=True):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    print(f"Výstupy kontroly (screenshot nastavení): {temp}")
    if r.returncode:
        sys.exit("Kontrola balíčku selhala.")


def ensure_inno() -> Path:
    iscc = INNO_DIR / "ISCC.exe"
    if iscc.exists():
        return iscc
    exe = CACHE / INNO_EXE
    download([INNO_URL], exe, INNO_SHA256)
    # Inno Setup's own installer in portable mode: no uninstaller, no registry, no shortcuts, no admin
    print(f"Instaluju Inno Setup {INNO_VERSION} (portable) do {INNO_DIR}")
    subprocess.run([str(exe), "/PORTABLE=1", "/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                    "/SP-", "/NOICONS", "/TASKS=", f"/DIR={INNO_DIR}"], check=True)
    if not iscc.exists():
        sys.exit("Inno Setup se nenainstaloval.")
    return iscc


def sign_command() -> str | None:
    """Inno Setup style sign command ($f = the quoted file, $q = a quote), or None when signing isn't set up."""
    if os.environ.get("ORBIT_SIGN_COMMAND"):
        return os.environ["ORBIT_SIGN_COMMAND"]
    pfx, thumb = os.environ.get("ORBIT_SIGN_PFX"), os.environ.get("ORBIT_SIGN_THUMBPRINT")
    if not pfx and not thumb:
        return None
    signtool = os.environ.get("ORBIT_SIGNTOOL") or next(iter(sorted(
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Windows Kits", "10", "bin")
        .glob("*/x64/signtool.exe"), reverse=True)), None)
    if not signtool:
        sys.exit("Podepisování: signtool.exe nenalezen, nastav ORBIT_SIGNTOOL.")
    stamp = os.environ.get("ORBIT_SIGN_TIMESTAMP", "http://timestamp.digicert.com")
    cmd = f"$q{signtool}$q sign /fd sha256 /tr {stamp} /td sha256 /d Orbit "
    if pfx:
        cmd += f"/f $q{pfx}$q " + (f"/p $q{os.environ['ORBIT_SIGN_PASSWORD']}$q "
                                    if os.environ.get("ORBIT_SIGN_PASSWORD") else "")
    else:
        cmd += f"/sha1 {thumb} "
    return cmd + "$f"


def sign_files(command: str, files: list[Path]) -> None:
    for f in files:
        subprocess.run(command.replace("$q", '"').replace("$f", f'"{f}"'), check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--whisper-dir", default="whisper", help="whisper-server and its DLLs (default whisper/)")
    ap.add_argument("--without-piper", action="store_true", help="leave out piper-tts (GPL-3.0) and onnxruntime")
    ap.add_argument("--no-installer", action="store_true", help="only build and check build/dist/Orbit")
    args = ap.parse_args()
    whisper_dir = (ROOT / args.whisper_dir).resolve()
    if not (whisper_dir / "whisper-server.exe").exists():
        sys.exit(f"V {whisper_dir} není whisper-server.exe.")

    started = time.time()
    version = read_version()
    print(f"Orbit {version}, whisper z {whisper_dir}{', bez Piperu' if args.without_piper else ''}")
    CACHE.mkdir(parents=True, exist_ok=True)
    if DIST.exists():
        shutil.rmtree(DIST)
    runtime, site = DIST / "runtime", DIST / "runtime" / "Lib" / "site-packages"
    make_runtime(runtime)
    install_packages(site, args.without_piper)
    prune_pyside(site)
    prune_site(site)
    copy_vc_runtime(site, runtime)
    copy_app(DIST, whisper_dir)
    package_inventory(site, DIST / "licenses" / "python-packages.txt")

    sources = [ROOT / "Orbit.pyw", *(ROOT / "app").glob("*.py")]
    if not any("--cleanup" in f.read_text(encoding="utf-8", errors="replace") for f in sources):
        # the uninstaller runs "Orbit.pyw --cleanup" and waits: without it, it would start Orbit and hang
        print("POZOR: Orbit.pyw --cleanup ještě není v kódu, odinstalace by spustila Orbit a čekala na něj.")
    missing = missing_dlls(DIST)
    if missing:
        sys.exit("Chybějící knihovny (na čistých Windows by to nešlo spustit):\n  " + "\n  ".join(missing))
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"Balíček {DIST}: {size / 1e6:.0f} MB")
    verify(DIST)
    if args.no_installer:
        return

    sign = sign_command()
    if sign:
        sign_files(sign, sorted((DIST / "whisper").glob("*.exe")) + sorted((DIST / "whisper").glob("*.dll")))
    iscc = ensure_inno()
    OUTPUT.mkdir(exist_ok=True)
    cmd = [str(iscc), "/Qp", f"/DAppVersion={version}", f"/DSourceDir={DIST}", f"/DOutputDir={OUTPUT}"]
    if sign:
        cmd += ["/DSign=1", f"/Sorbitsign={sign}"]
    subprocess.run(cmd + [str(ROOT / "installer" / "orbit.iss")], check=True)
    setup = OUTPUT / f"Orbit-Setup-{version}.exe"
    print(f"Hotovo za {(time.time() - started) / 60:.1f} min: {setup} ({setup.stat().st_size / 1e6:.0f} MB)"
          + ("" if sign else ", nepodepsaný"))


if __name__ == "__main__":
    main()
