"""Renders Orbit's real widgets with demo data into PNGs for the video (video/public/screens).

Run from the repo root:  .venv\\Scripts\\python.exe video\\capture\\grab.py
Nothing is shown on screen and no microphone, hook or Claude call is touched: the widgets are only painted
into pixmaps at 3x scale, so they stay sharp when the video zooms in on them. The data and Claude Code folders are
temporary ones (ORBIT_DATA_DIR, ORBIT_CLAUDE_DIR), so nothing of the user's is read or written.

The fold animation (app/foldfx.py) of the same panel goes to video/out/fold-ref/ (frames at u = 0, 0.1, … 1, folding
and unfolding): the reference for its copy in the video (src/components/FoldFx.tsx) and on the website (site.js).
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["QT_SCALE_FACTOR"] = "3"
ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="orbit-grab-"))
os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(TMP / "data"), str(TMP / "claude")
(TMP / "claude").mkdir(parents=True)
(TMP / "claude" / "settings.json").write_text(json.dumps({"model": "opus[1m]"}), encoding="utf-8")
(TMP / "data" / "cache").mkdir(parents=True)  # the models' exact names, as Claude Code 2.1.30x tells them
(TMP / "data" / "cache" / "models.json").write_text(json.dumps({"models": {
    f: {"id": f"claude-{f}-{v.replace('.', '-')}", "name": f"{f.capitalize()} {v}"}
    for f, v in (("fable", "5.1"), ("opus", "5.5"), ("sonnet", "5.5"), ("haiku", "5.5"))}}), encoding="utf-8")
sys.path.insert(0, str(ROOT))
OUT = ROOT / "video" / "public" / "screens"
REF = ROOT / "video" / "out" / "fold-ref"

import math  # noqa: E402

from types import SimpleNamespace  # noqa: E402

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, Qt, Signal  # noqa: E402
from PySide6.QtGui import QPixmap, QRegion  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QWidget, QWidgetAction  # noqa: E402

app = QApplication(sys.argv)

from app import colors, foldfx, theme, ui  # noqa: E402
from app.claude_usage import Limit, Usage  # noqa: E402
from app.config import DEFAULTS  # noqa: E402
from app.sessions import Session  # noqa: E402

theme.apply(app)
OUT.mkdir(parents=True, exist_ok=True)
REF.mkdir(parents=True, exist_ok=True)
now = datetime.now(timezone.utc)
FOLDERS = {"eshop": "orange", "faktury": "green", "web": "blue"}


def save(widget, name: str, out: Path = OUT) -> QPixmap:
    """Paints the widget into a transparent pixmap (grab() would put its translucent parts on white)."""
    widget.setAttribute(Qt.WA_DontShowOnScreen)
    widget.show()
    for _ in range(5):
        app.processEvents()
    ratio = 3
    pm = QPixmap(widget.width() * ratio, widget.height() * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    widget.render(pm, QPoint(), QRegion(), QWidget.DrawChildren | QWidget.DrawWindowBackground)
    pm.save(str(out / f"{name}.png"))
    print(name, pm.width(), pm.height())
    widget.hide()
    return pm


def usage() -> Usage:
    return Usage([Limit("session", "5 h", "5hodinové okno", 42, now + timedelta(hours=2, minutes=14)),
                  Limit("weekly_all", "Týden", "Týdenní limit", 63, now + timedelta(days=3)),
                  Limit("weekly_scoped", "Fable", "Týdenní limit Fable", 28, now + timedelta(days=3))])


def sessions() -> list[Session]:
    def s(i, folder, topic, state, ctx, model=""):
        return Session(id=str(i), cwd=f"C:\\Users\\demo\\{folder}", state=state, topic=topic, model=model,
                       context_tokens=int(ctx * 1_000_000), context_size=1_000_000, started=i)
    return [s(1, "eshop", "Překlad katalogu z němčiny", "working", 0.34),
            s(2, "faktury", "Oprava exportu faktur", "waiting", 0.12),
            s(3, "web", "Nová úvodní stránka", "done", 0.57, "claude-sonnet-5-5")]


def button(state="idle", usage_on=True, with_sessions=True, feed=None, agent_state="idle", reading=False):
    b = ui.FloatingButton(lambda: 0.6)
    b._timer.stop()
    b._work_timer.stop()
    b._wanted_align = lambda pos: ("right", False)  # the panel above the circles, lined up with the mic's edge
    b.set_claude(True)
    b.set_folder_colors(FOLDERS)
    b.set_usage_visible(usage_on)
    if usage_on:
        b.set_usage(usage(), None)
    if with_sessions:
        b.set_sessions(sessions())
    b.set_agent(True)
    b.set_notes_count(2)
    b.set_claude_version({"installed": "2.1.304", "latest": "2.1.304", "state": "current", "target": "", "tip": ""})
    b._agent_state = agent_state
    b._agent_feed = feed
    b._relayout(keep_button_in_place=False)
    b._state = state
    b._reading = reading
    b._level = 0.7
    return b


panel = button()
shot = save(panel, "panel")
save(button(usage_on=True, with_sessions=False), "panel-limits")
save(button(state="recording", usage_on=False, with_sessions=False), "mic-recording")
save(button(state="idle", usage_on=False, with_sessions=False), "mic-idle")
feed = {"you": "Co dělá relace s katalogem?",
        "reply": "Překládá katalog z němčiny, má hotovou zhruba polovinu stránek.",
        "send": {"name": "Překlad katalogu z němčiny", "folder": "eshop",
                 "message": "Ceny v katalogu rovnou převeď na koruny.", "status": "sent", "session_id": "1"}}
save(button(feed=feed), "panel-agent")
folded = button()
folded._collapsed = True
folded._relayout(keep_button_in_place=False)
save(folded, "icon")

for kind, title, text, note, name in (
        ("done", "Nová úvodní stránka", "Stránka je hotová a nasazená. Přidal jsem i video do horní části.",
         "hotovo", "bubble-done"),
        ("waiting", "Oprava exportu faktur", "Můžu přepsat starý export? Potřebuju tvoje svolení.", "čeká na tebe",
         "bubble-waiting")):
    bub = ui.Bubble(kind, title, text, note)
    bub._tail = None
    bub.setFixedSize(bub.W + 2 * bub.SHADOW, bub._card_h + 2 * bub.SHADOW)
    save(bub, name)



class Connected(QObject):
    """onboarding.ClaudeConnection as the settings see it with Claude Code installed, logged in and up to date."""
    changed, busy_changed, release_changed = Signal(), Signal(), Signal()
    connected, busy, message, updating, checking_release, update_note, old_sessions = True, "", "", "", False,         ("", True), []
    status = SimpleNamespace(error=None, installed=True, logged_in=True, connected=True, version="2.1.304",
                             describe=lambda: "Předplatné Claude Max.")
    release = SimpleNamespace(installed="2.1.304", latest="2.1.304", behind=False, auto_updates=True, error=None,
                              channel="latest")

    def __getattr__(self, name):  # install, login, update_claude, refresh, check_release: nothing to do here
        return lambda *a, **k: None


cfg = dict(DEFAULTS)
cfg.update({"ptt": {"kind": "mouse", "code": 6}, "vocabulary": "Orbit, Claude Code, Whisper",
            "replacements": [["klód", "Claude"]], "insert_mode": "paste", "duck_audio": "duck", "voice_edit": True,
            "claude_hooks": True, "claude_statusline": True, "tint_sessions": True, "agent": True})
dlg = ui.SettingsDialog(cfg, ["Mikrofon (USB headset)"], ["ggml-large-v3.bin", "ggml-large-v3-turbo.bin"],
                        True, lambda: 0.0, set(), Connected())
wave = dlg.findChild(theme.LevelWave)
wave._timer.stop()
for i in range(200):  # a spoken sentence: syllable bumps under a slow phrase envelope, quiet before it starts
    phrase = max(0.0, math.sin(math.pi * max(0, i - 70) / 130)) if i > 70 else 0.02
    wave._samples.append(min(0.85, phrase * (0.45 + 0.4 * abs(math.sin(i * 0.9)) * abs(math.sin(i * 0.23)))))
dlg.setFixedSize(820, dlg.layout().totalHeightForWidth(820) + 40)
dlg.setAttribute(Qt.WA_DontShowOnScreen)
dlg.show()
app.processEvents()
scroll = dlg.findChild(QScrollArea)  # all of both columns in sight: as tall as they are, no scroll bar
dlg.setFixedSize(820, dlg.height() + scroll.widget().sizeHint().height() - scroll.viewport().height())
app.processEvents()


def where(widget) -> str:
    r = QRect(widget.mapTo(dlg, QPoint(0, 0)), widget.size())
    return f"x {r.x()} y {r.y()} w {r.width()} h {r.height()}"


print("settings marks (logical px in the dialog):")
print("  model combo", where(dlg.model))
print("  learn row", where(dlg.learn))
for label in dlg.findChildren(QLabel):
    if label.text().startswith("Mikrofon je zapnutý jen"):
        print("  mic note", where(label))
print("  duck combo", where(dlg.duck))
save(dlg, "settings")

# the + above the panel: a new session in a favourite folder, with the model picked at the top (main._fill_favorites)
menu = ui.FolderMenu()
menu.addAction("Nová relace Claude Code ve složce").setEnabled(False)
holder = QWidgetAction(menu)
holder.setDefaultWidget(ui.ModelPicker(menu))
menu.addAction(holder)
for folder, color in FOLDERS.items():
    menu.addAction(ui.color_icon(colors.accent(color)), folder)
menu.addSeparator()
menu.addAction(theme.glyph_icon(ui.ADD_GLYPH, theme.DIM, 16), "Nové repo…")
menu.addAction(theme.glyph_icon(ui.CHOOSE_GLYPH, theme.DIM, 16), "Vybrat složky a barvy…")
menu.resize(menu.sizeHint())
save(menu, "menu-new")

# the fold animation of the panel above, as the app plays it (the picture is the panel's window, the icon at the mic)
center = QPointF(panel._button_center())
rect = QRect(QPoint(0, 0), panel.size())
for folding in (True, False):
    fx = foldfx.FoldFx(shot, rect, center, folding, folded._paint_icon, ui.FloatingButton.ICON_D / 2, 1.0, seed=7)
    for k in range(11):
        u = k / 10
        fx.frame(u).save(str(REF / f"{'fold' if folding else 'unfold'}-{k:02d}.png"))
    print("fold-ref", "fold" if folding else "unfold", fx.width(), fx.height())
shutil.rmtree(TMP, ignore_errors=True)
