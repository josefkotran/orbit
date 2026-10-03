"""Builds whisper-server (whisper.cpp + ggml, Vulkan) for any Windows x64 PC into whisper-next/.

Unlike the first build (CLAUDE.md) it isn't tuned to the build machine's CPU and doesn't need Vulkan to start:
ggml loads its backends as DLLs at runtime (GGML_BACKEND_DL), picks the best of the CPU variants
(GGML_CPU_ALL_VARIANTS: sse4.2 … avx512/amx) and uses ggml-vulkan.dll only when a Vulkan driver is there.

Everything happens in build/cache (portable MSYS2 UCRT64, no system install, nothing in the registry):
    .venv\\Scripts\\python.exe build\\build_whisper.py [--out whisper-next] [--jobs N]
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "build" / "cache"
MSYS = CACHE / "msys64"

MSYS_BASE = "msys2-base-x86_64-20260927.tar.xz"
MSYS_SHA256 = "ea2f31a0b6ade63914ce441ffb022f0f6aa96982bfefa2326460a26d5fb01322"
MSYS_URLS = [  # the hash is what makes a mirror trustworthy; repo.msys2.org is sometimes unreachable
    f"https://github.com/msys2/msys2-installer/releases/download/2026-09-27/{MSYS_BASE}",
    f"https://repo.msys2.org/distrib/x86_64/{MSYS_BASE}",
    f"https://mirror.selfnet.de/msys2/distrib/x86_64/{MSYS_BASE}",
]
PACKAGES = [f"mingw-w64-ucrt-x86_64-{p}" for p in ("gcc", "cmake", "ninja", "vulkan-devel", "shaderc")]

WHISPER_VERSION = "1.9.4"
WHISPER_SHA256 = "57e280cee375ab02425b806ad5146b99f6eb9357e3c2b31357c8a6af2e2e44ae"
WHISPER_URL = f"https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v{WHISPER_VERSION}.tar.gz"

STATIC_RT = "-static-libgcc -static-libstdc++"
# without --exclude-libs ggml-base.dll re-exports libgcc's _Unwind_Resume and the backend DLLs fail to link
DLL_RT = STATIC_RT + " -Wl,--exclude-libs,ALL"
CMAKE_FLAGS = [
    "-DCMAKE_BUILD_TYPE=Release",
    "-DGGML_NATIVE=OFF",  # not tuned to this CPU (the old build crashed on CPUs without its instructions)
    "-DGGML_BACKEND_DL=ON",  # backends are DLLs loaded at runtime: starts without a Vulkan driver
    "-DGGML_CPU_ALL_VARIANTS=ON",  # one CPU backend per instruction set, the best one is picked at runtime
    "-DGGML_VULKAN=ON",
    "-DGGML_OPENMP=OFF",  # like the old build: ggml's own thread pool, no libgomp-1.dll
    "-DBUILD_SHARED_LIBS=ON",
    "-DWHISPER_BUILD_TESTS=OFF",
    # ggml looks for ggml-cpu-*.dll / ggml-vulkan.dll on Windows; MinGW would name them libggml-*.dll
    "-DCMAKE_SHARED_MODULE_PREFIX=",
    "-DCMAKE_SHARED_LIBRARY_PREFIX=",
    f"-DCMAKE_EXE_LINKER_FLAGS={STATIC_RT}",
    f"-DCMAKE_SHARED_LINKER_FLAGS={DLL_RT}",
    f"-DCMAKE_MODULE_LINKER_FLAGS={DLL_RT}",
]

# DLLs every Windows 10/11 has (UCRT included); anything else must be shipped next to the exe
SYSTEM_DLLS = {"kernel32.dll", "advapi32.dll", "ws2_32.dll", "user32.dll", "gdi32.dll", "shell32.dll", "ole32.dll",
               "msvcrt.dll", "ntdll.dll", "bcrypt.dll", "shlwapi.dll", "dbghelp.dll", "psapi.dll", "version.dll"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(urls: list[str], dest: Path, digest: str) -> None:
    if dest.exists() and sha256(dest) == digest:
        return
    for url in urls:
        print(f"Stahuju {url}")
        try:
            with urllib.request.urlopen(url, timeout=60) as r, open(dest.with_suffix(".part"), "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
        except OSError as e:
            print(f"  nepovedlo se: {e}")
            continue
        if sha256(dest.with_suffix(".part")) == digest:
            dest.with_suffix(".part").replace(dest)
            return
        print("  nesedí SHA256, zkouším další zdroj")
    sys.exit(f"Nepodařilo se stáhnout {dest.name} se správným SHA256.")


def bash(script: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MSYS", "MINGW"))}
    env.update(MSYSTEM="UCRT64", CHERE_INVOKING="1", MSYS2_PATH_TYPE="minimal")
    subprocess.run([str(MSYS / "usr" / "bin" / "bash.exe"), "-lc", script], cwd=CACHE, env=env, check=True)


def ensure_toolchain() -> None:
    if not (MSYS / "usr" / "bin" / "bash.exe").exists():
        archive = CACHE / MSYS_BASE
        download(MSYS_URLS, archive, MSYS_SHA256)
        print("Rozbaluju MSYS2…")
        with tarfile.open(archive) as t:
            t.extractall(CACHE, filter="tar")
    if not (MSYS / "ucrt64" / "bin" / "glslc.exe").exists():  # the first login also sets up pacman's keyring
        bash("pacman -Sy --noconfirm --needed " + " ".join(PACKAGES))


def ensure_source() -> Path:
    src = CACHE / f"whisper.cpp-{WHISPER_VERSION}"
    if not (src / "CMakeLists.txt").exists():
        archive = CACHE / f"whisper.cpp-{WHISPER_VERSION}.tar.gz"
        download([WHISPER_URL], archive, WHISPER_SHA256)
        with tarfile.open(archive) as t:
            t.extractall(CACHE, filter="data")
    return src


def imports(path: Path) -> list[str]:
    out = subprocess.run([str(MSYS / "ucrt64" / "bin" / "objdump.exe"), "-p", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return [line.split("DLL Name:")[1].strip() for line in out.splitlines() if "DLL Name:" in line]


def missing_dlls(folder: Path) -> dict[str, list[str]]:
    """What each exe/dll imports that is neither in the folder nor part of Windows."""
    present = {p.name.lower() for p in folder.glob("*.dll")}
    result = {}
    for f in sorted(folder.glob("*.exe")) + sorted(folder.glob("*.dll")):
        bad = [d for d in imports(f) if d.lower() not in present and d.lower() not in SYSTEM_DLLS
               and not d.lower().startswith("api-ms-win-")]
        # vulkan-1.dll comes with the GPU driver; only the Vulkan backend (loaded on demand) may import it
        bad = [d for d in bad if not (d.lower() == "vulkan-1.dll" and f.name.lower() == "ggml-vulkan.dll")]
        if bad:
            result[f.name] = bad
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="whisper-next", help="output folder (relative to the repo), never whisper/")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    args = ap.parse_args()
    out = (ROOT / args.out).resolve()
    if out == (ROOT / "whisper").resolve():
        sys.exit("whisper/ používá běžící Orbit, zvol jinou složku.")

    CACHE.mkdir(parents=True, exist_ok=True)
    ensure_toolchain()
    src = ensure_source()
    build = CACHE / "whisper-build"
    flags = " ".join(f"'{f}'" for f in CMAKE_FLAGS)
    bash(f"cmake -S '{src.as_posix()}' -B '{build.as_posix()}' -G Ninja {flags} && "
         f"cmake --build '{build.as_posix()}' --target whisper-server -j {args.jobs}")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copy2(build / "bin" / "whisper-server.exe", out)
    for dll in sorted((build / "bin").glob("*.dll")):
        shutil.copy2(dll, out)
    shutil.copy2(MSYS / "ucrt64" / "bin" / "libwinpthread-1.dll", out)
    shutil.copy2(src / "LICENSE", out / "LICENSE")
    shutil.copy2(MSYS / "ucrt64" / "share" / "licenses" / "libwinpthread" / "COPYING", out / "LICENSE-winpthreads")
    bash(f"strip --strip-unneeded '{out.as_posix()}'/*.exe '{out.as_posix()}'/*.dll")

    for f in sorted(out.iterdir()):
        print(f"  {f.name:32} {f.stat().st_size / 1e6:7.1f} MB")
    missing = missing_dlls(out)
    if missing:
        sys.exit(f"Chybí knihovny: {missing}")
    print(f"Hotovo: {out}")


if __name__ == "__main__":
    main()
