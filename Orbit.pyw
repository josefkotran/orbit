"""Orbit: runtime\\pythonw.exe Orbit.pyw once installed, .venv\\Scripts\\pythonw.exe Orbit.pyw in a dev checkout."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


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
        from app.main import main
        main()
    except Exception:
        _crash()
