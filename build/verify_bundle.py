"""Smoke test of a built bundle, run by build_installer.py with the bundle's own runtime\\python.exe:
    runtime\\python.exe build\\verify_bundle.py <bundle> <temp folder>

Imports every module of app/ and the packages Orbit needs, builds the settings dialog offscreen
(QT_QPA_PLATFORM=offscreen, a screenshot goes to the temp folder) and feeds a sample event to the
Claude Code hook. The caller points ORBIT_DATA_DIR and ORBIT_CLAUDE_DIR into the temp folder.
Prints what failed and exits with 1 if anything did.
"""
import importlib
import inspect
import json
import os
import pkgutil
import subprocess
import sys
import traceback
from pathlib import Path

bundle, temp = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(bundle))
failed = []


def check(what, fn):
    try:
        result = fn()
        print(f"  ok    {what}" + (f": {result}" if result not in (None, "") else ""))
    except BaseException:
        failed.append(what)
        print(f"  CHYBA {what}\n" + "".join("        " + line for line in traceback.format_exc().splitlines(True)))


def own_runtime():
    if not Path(sys.executable).resolve().is_relative_to(bundle.resolve()):
        raise RuntimeError(f"běží {sys.executable}, ne python z balíčku")
    here = Path(__file__).resolve().parent
    stray = [p for p in sys.path
             if p and Path(p).resolve() != here and not Path(p).resolve().is_relative_to(bundle.resolve())]
    if stray:
        raise RuntimeError(f"sys.path míří mimo balíček: {stray}")
    # the ._pth has no "import site" (no user site-packages), so .pth files would be silently ignored
    pth = [p.name for p in (bundle / "runtime" / "Lib" / "site-packages").glob("*.pth")]
    if pth:
        raise RuntimeError(f"balíček má soubory .pth, které bez modulu site nic neudělají: {pth}")
    return sys.version.split()[0]


check("vlastní runtime", own_runtime)

import app  # noqa: E402

for mod in sorted(m.name for m in pkgutil.iter_modules(app.__path__)):
    if mod == "cc_hook":
        continue  # a script Claude Code runs on its own, tested below
    check(f"import app.{mod}", lambda mod=mod: importlib.import_module(f"app.{mod}") and None)

piper = (bundle / "runtime" / "Lib" / "site-packages" / "piper").is_dir()
for mod in ["numpy", "sounddevice", "pynput.keyboard", "requests", "PySide6.QtTextToSpeech"] + \
           (["onnxruntime", "piper"] if piper else []):
    check(f"import {mod}", lambda mod=mod: importlib.import_module(mod) and None)
check("PortAudio", lambda: f"{len(__import__('sounddevice').query_devices())} zařízení")
if piper:
    check("onnxruntime", lambda: ", ".join(__import__("onnxruntime").get_available_providers()))


def settings_dialog():
    from PySide6.QtWidgets import QApplication
    from app import config, theme, ui

    qapp = QApplication.instance() or QApplication([])
    theme.apply(qapp)
    known = {"cfg": config.load(), "mics": [], "models": [], "autostart": False, "first_run": False,
             "level_source": lambda: 0.0, "handsfree_mics": set()}
    params = inspect.signature(ui.SettingsDialog).parameters.values()
    dlg = ui.SettingsDialog(**{p.name: known.get(p.name) for p in params if p.default is p.empty})
    dlg.adjustSize()
    shot = temp / "settings.png"
    dlg.grab().save(str(shot))
    dlg.deleteLater()
    return shot


def tts_engines():
    from PySide6.QtTextToSpeech import QTextToSpeech
    engines = QTextToSpeech.availableEngines()
    if "winrt" not in engines:
        raise RuntimeError(f"chybí winrt, jsou jen {engines}")
    return ", ".join(engines)


def hook():
    event = {"hook_event_name": "SessionStart", "session_id": "verify-bundle", "cwd": str(temp),
             "transcript_path": str(temp / "verify-bundle.jsonl"), "source": "startup"}
    r = subprocess.run([sys.executable, str(bundle / "app" / "cc_hook.py")], input=json.dumps(event),
                       capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError(f"exit {r.returncode}: {r.stderr.strip()[-500:]}")
    written = [p for folder in (Path(os.environ["ORBIT_DATA_DIR"]), bundle) for p in folder.rglob("verify-bundle*")]
    if not written:
        raise RuntimeError("hook nic nezapsal")
    return f"zapsal {', '.join(str(p) for p in written)}"


check("dialog nastavení (offscreen)", settings_dialog)
check("hlasy QTextToSpeech", tts_engines)
check("hook Claude Code (cc_hook.py)", hook)

print(f"Selhalo: {', '.join(failed)}" if failed else "Vše v pořádku.")
sys.exit(1 if failed else 0)
