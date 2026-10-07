"""Builds Orbit's Windows installer: build/output/Orbit-Setup-<version>.exe.

The bundle (build/dist/Orbit) is exactly what the installer puts into %LOCALAPPDATA%\\Programs\\Orbit:
    runtime\\   Python 3.13 embeddable distribution, Orbit's packages in runtime\\Lib\\site-packages
    app\\, Orbit.pyw, assets\\ (static files only), whisper\\, THIRD_PARTY_NOTICES.md
It's started as runtime\\pythonw.exe Orbit.pyw. Models aren't in it, Orbit downloads them on first run.

    .venv\\Scripts\\python.exe build\\build_installer.py [--whisper-dir whisper-next] [--without-piper] [--no-installer]
    .venv\\Scripts\\python.exe build\\build_installer.py --update-lock    (after a change in requirements.txt)

Downloads (cached in build/cache, Inno Setup in build/tools) need internet the first time. See build/README.md.
"""
import argparse
import ctypes
import json
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
PIP_TARGET = ["--only-binary=:all:", "--platform", "win_amd64", "--python-version", "3.13", "--implementation", "cp"]
# Every wheel in runtime\Lib\site-packages with the SHA-256 PyPI served for it (win_amd64, CPython 3.13). pip installs
# exactly these (--require-hashes --no-deps): requirements.txt pins only Orbit's direct dependencies, so a new release
# of urllib3, idna, certifi… would otherwise go into the next installer unnoticed. "piper" = only Piper needs it
# (--without-piper leaves it out). After changing requirements.txt refresh it on purpose with --update-lock (it
# rewrites this block) and check the git diff.
BUNDLE_LOCK = """
certifi==2026.7.22 sha256:62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775
cffi==2.1.1 sha256:1aa5645c30469b09530c4ebca77ebf8f17618293c58f8549cb1a543a50236e7d
charset-normalizer==3.5.2 sha256:78456a747de8dc58360ffa581f30a002baf5aa28cb262536545e91f113ed7639
flatbuffers==25.12.19 sha256:7634f50c427838bb021c2d66a3d1168e9d199b0607e6329399f04846d42e20b4 piper
idna==3.20 sha256:ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c
numpy==2.5.3 sha256:71cad2b2a7451ab79d8f5e71b453485b6775963d5cf794179144a7463fe6e8ec
onnxruntime==1.30.0 sha256:4b63041bd623a9a9ac5e353948436c6fa7f43edd12d6b4a4ebc340bca959ba93 piper
packaging==26.3 sha256:d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c piper
pathvalidate==3.3.1 sha256:5263baab691f8e1af96092fa5137ee17df5bdfbd6cff1fcac4d6ef4bc2e1735f piper
piper-tts==1.8.0 sha256:5da9bfdb05dfe15da3536859d422e605483ffa6d2b3ec2c5b9593bae6b5aa6a4 piper
protobuf==7.36.2 sha256:a300819d441e078a5608c0d3c709796bb548136058fda017ae51d425b44fd353 piper
pycparser==3.0 sha256:b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992
pynput==1.8.2 sha256:8cc38cf13a6ab2749cb375678be8a0fd705d7ce49c8001ff5db4007a723bbef1
PySide6==6.11.2 sha256:3201d67e3c10be2eaedd3910ff0f02351eca7e88c95a291cde5e7f2f55ef207f
PySide6_Addons==6.11.2 sha256:f449ea4431da20e7b86752cca8d166f93434516fe417f981c27e5f8e1b554407
PySide6_Essentials==6.11.2 sha256:c8a29def77032773a30879f7f24415b5395ad08592d147c170824ef4c735dfc1
requests==2.34.2 sha256:2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0
shiboken6==6.11.2 sha256:6ab0eba1c904455df621f9a6df3ca2bb896bab8670572d2bc4e37804ae91f19a
six==1.17.0 sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274
sounddevice==0.5.6 sha256:7f4162f514f007b0bf25a3ccfed3f1705bc2ec311888a90232729eec4f57a4f4
urllib3==2.8.0 sha256:0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3
"""
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


def canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirements(without_piper: bool) -> list[str]:
    """The lines of requirements.txt (Orbit's direct dependencies)."""
    reqs = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name = canon(re.split(r"[<>=!~;\[\s]", line.strip(), maxsplit=1)[0])
        if name and not name.startswith("#") and not (without_piper and name in PIPER_PACKAGES):
            reqs.append(line.strip())
    return reqs


def read_lock(text: str | None = None) -> list[tuple[str, str, str, bool]]:
    """(name, version, sha256, only for Piper) for each line of BUNDLE_LOCK."""
    pins = []
    for line in (BUNDLE_LOCK if text is None else text).strip().splitlines():
        m = re.fullmatch(r"([\w.-]+)==(\S+) sha256:([0-9a-f]{64})( piper)?", line.strip())
        if not m:
            sys.exit(f"Vadný řádek zámku balíčků v build_installer.py: {line}")
        pins.append((m[1], m[2], m[3], bool(m[4])))
    return pins


def locked_requirements(without_piper: bool) -> list[str]:
    """pip requirement lines with hashes from BUNDLE_LOCK. Stops when requirements.txt wants something the lock
    doesn't have (a new package or another version)."""
    pins = read_lock()
    versions = {canon(name): version for name, version, _, _ in pins}
    for line in requirements(without_piper):
        m = re.match(r"([\w.-]+)\s*(==\s*([^\s;]+))?", line)
        name = canon(m[1])
        if name not in versions or (m[3] and m[3] != versions[name]):
            sys.exit(f"requirements.txt chce {line}, zámek balíčků v build_installer.py má "
                     f"{versions.get(name, 'nic')}. Spusť build_installer.py --update-lock a zkontroluj git diff.")
    return [f"{name}=={version} --hash=sha256:{sha}" for name, version, sha, piper in pins
            if not (without_piper and piper)]


def install_packages(site: Path, without_piper: bool) -> None:
    reqs = locked_requirements(without_piper)
    req_file = CACHE / "requirements-bundle.txt"
    req_file.write_text("\n".join(reqs) + "\n", encoding="utf-8")
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
           "--require-hashes", "--no-deps", "--target", str(site), *PIP_TARGET, "-r", str(req_file)]
    if sys.version_info[:2] != (3, 13):
        cmd.append("--no-compile")  # .pyc made by another Python version would just be ignored
    print("pip install " + " ".join(r.split(" --hash")[0] for r in reqs))
    subprocess.run(cmd, check=True)
    shutil.rmtree(site / "bin", ignore_errors=True)  # console scripts (pyside6-designer, …)


def resolve(reqs: list[str]) -> dict[str, tuple[str, str]]:
    """What pip picks for these requirements on the target, from PyPI: name -> (version, sha256). Installs nothing."""
    with tempfile.TemporaryDirectory(prefix="orbit-lock-") as tmp:
        req_file, report = Path(tmp, "requirements.txt"), Path(tmp, "report.json")
        req_file.write_text("\n".join(reqs) + "\n", encoding="utf-8")
        subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--quiet", "--dry-run",
                        "--ignore-installed", "--report", str(report), "--target", str(Path(tmp, "site")),
                        *PIP_TARGET, "-r", str(req_file)], check=True)
        installs = json.loads(report.read_text(encoding="utf-8"))["install"]
    return {i["metadata"]["name"]: (i["metadata"]["version"], i["download_info"]["archive_info"]["hashes"]["sha256"])
            for i in installs}


def update_lock(script: Path = Path(__file__)) -> None:
    """Resolves requirements.txt again and rewrites BUNDLE_LOCK in this script."""
    full, core = resolve(requirements(False)), {canon(name) for name in resolve(requirements(True))}
    lines = [f"{name}=={version} sha256:{sha}" + ("" if canon(name) in core else " piper")
             for name, (version, sha) in sorted(full.items(), key=lambda item: canon(item[0]))]
    with open(script, encoding="utf-8", newline="") as f:
        text = f.read()
    block = re.search(r'(?ms)^BUNDLE_LOCK = """(.*?)^"""', text)
    if not block:
        sys.exit(f"V {script} chybí BUNDLE_LOCK.")
    nl = "\r\n" if "\r\n" in text else "\n"
    with open(script, "w", encoding="utf-8", newline="") as f:
        f.write(text[:block.start()] + f'BUNDLE_LOCK = """{nl}' + nl.join(lines) + f'{nl}"""' + text[block.end():])
    old, new = {canon(n): v for n, v, _, _ in read_lock(block[1])}, {canon(n): v for n, (v, _) in full.items()}
    changes = [f"{n} {old.get(n, '–')} -> {new.get(n, 'pryč')}" for n in sorted(old.keys() | new.keys())
               if old.get(n) != new.get(n)]
    print(f"Zámek balíčků ({len(lines)}) zapsán do {script}: " + (", ".join(changes) or "beze změny"))


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
    shutil.copy2(ROOT / "LICENSE", dist / "LICENSE.txt")  # Orbit's own licence (GPL-3.0-or-later)
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
    # a downloaded Piper voice (only read: the check copies it) for reading aloud from a folder with diacritics
    voices = next((d for d in (ROOT / "models" / "piper",
                               Path(os.environ.get("LOCALAPPDATA", ROOT)) / "Orbit" / "models" / "piper")
                   if any(d.glob("*.onnx.json"))), "")
    before = {p for p in dist.rglob("*")}
    # without -s, the way Orbit starts this Python itself (the check fails if sys.path leaves the bundle)
    r = subprocess.run([str(dist / "runtime" / "python.exe"), str(BUILD / "verify_bundle.py"), str(dist),
                        str(temp), str(voices)], env=env, cwd=temp)
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
    """Inno Setup style sign command ($f = the quoted file, $q = a quote), or None when signing isn't set up.
    Never with a password: the command goes into the ISCC and signtool command lines, which any process of the user
    can read (Win32_Process.CommandLine)."""
    if os.environ.get("ORBIT_SIGN_COMMAND"):
        return os.environ["ORBIT_SIGN_COMMAND"]
    pfx, thumb = os.environ.get("ORBIT_SIGN_PFX"), os.environ.get("ORBIT_SIGN_THUMBPRINT")
    if pfx and os.environ.get("ORBIT_SIGN_PASSWORD"):
        sys.exit("Podepisování: heslo k PFX by bylo vidět v příkazové řádce signtoolu a ISCC. Naimportuj certifikát "
                 "do úložiště Windows (Import-PfxCertificate -FilePath <soubor.pfx> -CertStoreLocation "
                 "Cert:\\CurrentUser\\My, bez -Exportable) a místo ORBIT_SIGN_PFX a ORBIT_SIGN_PASSWORD nastav "
                 "ORBIT_SIGN_THUMBPRINT, nebo použij ORBIT_SIGN_COMMAND.")
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
        cmd += f"/f $q{pfx}$q "  # a PFX without a password
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
    ap.add_argument("--update-lock", action="store_true",
                    help="resolve requirements.txt again and rewrite BUNDLE_LOCK in this script (needs internet)")
    args = ap.parse_args()
    if args.update_lock:
        update_lock()
        return
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
