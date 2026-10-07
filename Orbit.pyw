"""Orbit: runtime\\pythonw.exe Orbit.pyw once installed, .venv\\Scripts\\pythonw.exe Orbit.pyw in a dev checkout."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# A program Orbit looks up on the PATH (claude.exe, git, pwsh) never comes from the current folder (Claude Code does
# the same for its own lookups). A user's own setting wins.
os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")


def _import_numpy() -> None:
    """numpy's OpenBLAS starts a thread per logical processor at import and commits ~32 MB of memory for each
    (~490 MB with 16), and Orbit never multiplies a matrix: one thread. Only for this import, so the sessions and
    programs Orbit starts keep the user's own setting."""
    import importlib

    mine = "OPENBLAS_NUM_THREADS" not in os.environ
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    try:
        importlib.import_module("numpy")
    finally:
        if mine:
            del os.environ["OPENBLAS_NUM_THREADS"]


def _crash() -> None:
    """pythonw has no console, so a failed start (a broken install, an unwritable data folder) would just do nothing.
    Writes the details to crash.log and says where."""
    import ctypes
    import tempfile
    import time
    import traceback

    details = traceback.format_exc()
    folders = [Path(tempfile.gettempdir())]
    try:
        from app import paths
        folders.insert(0, paths.data_dir())
    except Exception:
        pass
    where = None
    for folder in folders:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with open(folder / "crash.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{details}\n")
            where = folder / "crash.log"
            break
        except OSError:
            continue
    error = details.strip().splitlines()[-1] if details.strip() else "neznámá chyba"
    text = f"Orbit se nespustil.\n\n{error}" + (f"\n\nPodrobnosti: {where}" if where else "")
    try:
        ctypes.windll.user32.MessageBoxW(None, text, "Orbit", 0x10)  # MB_ICONERROR
    except Exception:
        pass


if __name__ == "__main__":
    if "--cleanup" in sys.argv[1:]:  # the uninstaller: no window, no Qt, no single-instance check (app/cleanup.py)
        try:
            from app.cleanup import main as cleanup
            cleanup()
        except Exception:
            pass
        sys.exit(0)
    try:
        _import_numpy()  # before anything else imports it
        from app.main import main
        main()
    except Exception:
        _crash()
