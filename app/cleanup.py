"""`Orbit.pyw --cleanup`: what the uninstaller runs (runtime\\python.exe, hidden, waits for it).

Takes this installation's entries out of Claude Code's settings.json (hooks, status line; the user's previous status
line comes back) and out of the Run key. Another Orbit copy's entries and the user's own stay. No window, no
single-instance check (a running Orbit doesn't matter), never fails: what it did goes to orbit.log and stdout, and it
always exits with 0 so the uninstall carries on.
"""
import logging
import sys

log = logging.getLogger("orbit.cleanup")


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)] if sys.stdout else []
    try:
        from . import paths
        folder = paths.data_dir()
        if folder.is_dir():  # never creates the data folder just for this
            handlers.append(logging.FileHandler(folder / "orbit.log", encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    try:
        _setup_logging()
        log.info("Úklid před odinstalací (%s)", sys.executable)
    except Exception:
        pass
    try:
        from . import claude_settings, paths
        log.info("Claude Code (%s): %s", paths.claude_dir(), ", ".join(claude_settings.cleanup()))
    except Exception:
        log.exception("Úklid nastavení Claude Code selhal")
    try:
        from . import winutil
        log.info("Spouštění s Windows: %s", "odebráno" if winutil.set_autostart(False) else "nebylo nastavené")
    except Exception:
        log.exception("Úklid spouštění s Windows selhal")
    return 0
