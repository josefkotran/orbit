"""Smoke test of a built bundle, run by build_installer.py with the bundle's own runtime\\python.exe:
    runtime\\python.exe build\\verify_bundle.py <bundle> <temp folder> [<folder with a Piper voice>]

Imports every module of app/ and the packages Orbit needs, builds the settings dialog offscreen
(QT_QPA_PLATFORM=offscreen, a screenshot goes to the temp folder), feeds a sample event to the
Claude Code hook and, with a downloaded Piper voice, reads a sentence aloud from a folder with diacritics.
The caller points ORBIT_DATA_DIR and ORBIT_CLAUDE_DIR into the temp folder.
Prints what failed and exits with 1 if anything did.
"""
import _winapi
import importlib
import inspect
import json
import os
import pkgutil
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path


def piper_say(model: str) -> int:
    """The child process of piper_nonascii(): Orbit's voice module reads a text with Piper, its log goes to stdout."""
    import logging
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    from app import voice
    if not voice.piper_installed():
        print("NOPIPER")  # no ASCII form of the path (8.3 names off): Orbit doesn't offer Piper at all
        return 0
    speaker = voice.PiperSpeaker(model)
    # only punctuation: espeak-ng starts and loads Czech (what a path with diacritics breaks), nothing is heard
    speaker.say(".")
    deadline = time.monotonic() + 120
    while speaker.speaking and time.monotonic() < deadline:
        time.sleep(0.05)
    if speaker.speaking:
        print("ERROR nedočetl do 2 minut")
    getattr(speaker, "close", lambda: None)()
    return 0


if sys.argv[1:2] == ["--piper-say"]:
    sys.exit(piper_say(sys.argv[2]))

bundle, temp = Path(sys.argv[1]), Path(sys.argv[2])
voices = Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
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


def piper_nonascii():
    """Orbit under a folder with diacritics (a Czech user name: C:\\Users\\Jiří Nový\\AppData\\Local\\Programs\\Orbit)
    reads aloud with Piper. espeak-ng can't open its data through such a path and ends the whole process it runs in
    with exit(1), no exception (1.0.0: Orbit vanished at the first text read aloud). The bundle is reached through a
    junction there, the voice is copied into a data folder next to it. Any warning in Orbit's log fails it."""
    model = next(p for p in sorted(voices.glob("*.onnx")) if Path(f"{p}.json").is_file())
    home = temp / "Jiří Nový"
    (home / "data" / "models" / "piper").mkdir(parents=True)
    for f in (model, Path(f"{model}.json")):
        shutil.copy2(f, home / "data" / "models" / "piper" / f.name)
    link = home / "Orbit"
    _winapi.CreateJunction(str(bundle.resolve()), str(link))
    try:
        r = subprocess.run([str(link / "runtime" / "python.exe"), str(Path(__file__).resolve()), "--piper-say",
                            model.stem], env=dict(os.environ, ORBIT_DATA_DIR=str(home / "data")),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    finally:
        os.rmdir(link)  # removes the junction only, never what it points to
    out = (r.stdout + r.stderr).strip()
    if r.returncode == 0 and "NOPIPER" in out.splitlines():
        return "Orbit tu Piper nenabízí (cesta bez krátkého jména 8.3), to je v pořádku"
    if "phontab" in out:
        raise RuntimeError("espeak-ng neotevřel svá data v cestě s diakritikou a ukončil proces, ve kterém běží: "
                           f"Orbit by tam hlasem Piperu nepřečetl nic (1.0.0 rovnou spadl).\n{out[-600:]}")
    if r.returncode or "načten" not in out or any(line.startswith(("WARNING", "ERROR", "CRITICAL"))
                                                  for line in out.splitlines()):
        raise RuntimeError(f"exit {r.returncode}: {out[-800:]}")
    return f"hlas načten, espeak-ng svá data našel ({link})"


check("dialog nastavení (offscreen)", settings_dialog)
check("hlasy QTextToSpeech", tts_engines)
check("hook Claude Code (cc_hook.py)", hook)
if piper and voices:
    check("Piper ve složce s diakritikou", piper_nonascii)
elif piper:
    print("  --    Piper ve složce s diakritikou: přeskočeno, chybí stažený hlas (models\\piper)")

print(f"Selhalo: {', '.join(failed)}" if failed else "Vše v pořádku.")
sys.exit(1 if failed else 0)
