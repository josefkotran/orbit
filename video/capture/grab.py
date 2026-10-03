"""Renders Orbit's real widgets with demo data into PNGs for the video (video/public/screens).

Run from the repo root:  .venv\\Scripts\\python.exe video\\capture\\grab.py
Nothing is shown on screen and no microphone, hook or Claude call is touched: the widgets are only painted
into pixmaps at 3x scale, so they stay sharp when the video zooms in on them.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["QT_SCALE_FACTOR"] = "3"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "video" / "public" / "screens"

import math  # noqa: E402

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QPixmap, QRegion  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication(sys.argv)

from app import theme, ui  # noqa: E402
from app.claude_usage import Limit, Usage  # noqa: E402
from app.config import DEFAULTS  # noqa: E402
from app.sessions import Session  # noqa: E402

theme.apply(app)
OUT.mkdir(parents=True, exist_ok=True)
now = datetime.now(timezone.utc)


def save(widget, name: str) -> None:
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
    pm.save(str(OUT / f"{name}.png"))
    print(name, pm.width(), pm.height())
    widget.hide()


def usage() -> Usage:
    return Usage([Limit("session", "5 h", "5hodinové okno", 42, now + timedelta(hours=2, minutes=14)),
                  Limit("weekly_all", "Týden", "Týdenní limit", 63, now + timedelta(days=3)),
                  Limit("weekly_scoped", "Fable", "Týdenní limit Fable", 28, now + timedelta(days=3))])


def sessions() -> list[Session]:
    def s(i, folder, topic, state, ctx):
        return Session(id=str(i), cwd=f"C:\\Users\\demo\\{folder}", state=state, topic=topic,
                       context_tokens=int(ctx * 1_000_000), context_size=1_000_000, started=i)
    return [s(1, "eshop", "Překlad katalogu z němčiny", "working", 0.34),
            s(2, "faktury", "Oprava exportu faktur", "waiting", 0.12),
            s(3, "web", "Nová úvodní stránka", "done", 0.57)]


def button(state="idle", usage_on=True, with_sessions=True, feed=None, agent_state="idle", reading=False):
    b = ui.FloatingButton(lambda: 0.6)
    b._timer.stop()
    b.set_usage_visible(usage_on)
    if usage_on:
        b.set_usage(usage(), None)
    if with_sessions:
        b.set_sessions(sessions())
    b.set_agent(True)
    b._agent_state = agent_state
    b._agent_feed = feed
    b._relayout(keep_button_in_place=False)
    b._state = state
    b._reading = reading
    b._level = 0.7
    return b


save(button(), "panel")
save(button(usage_on=True, with_sessions=False), "panel-limits")
save(button(state="recording", usage_on=False, with_sessions=False), "mic-recording")
save(button(state="idle", usage_on=False, with_sessions=False), "mic-idle")
feed = {"you": "Co dělá relace s katalogem?",
        "reply": "Překládá katalog z němčiny, má hotovou zhruba polovinu stránek.",
        "send": {"name": "Překlad katalogu z němčiny", "folder": "eshop",
                 "message": "Ceny v katalogu rovnou převeď na koruny.", "status": "sent", "session_id": "1"}}
save(button(feed=feed), "panel-agent")

for kind, title, text, note, name in (
        ("done", "Nová úvodní stránka", "Stránka je hotová a nasazená. Přidal jsem i video do horní části.",
         "hotovo", "bubble-done"),
        ("waiting", "Oprava exportu faktur", "Můžu přepsat starý export? Potřebuju tvoje svolení.", "čeká na tebe",
         "bubble-waiting")):
    bub = ui.Bubble(kind, title, text, note)
    bub._tail = None
    bub.setFixedSize(bub.W + 2 * bub.SHADOW, bub._card_h + 2 * bub.SHADOW)
    save(bub, name)

cfg = dict(DEFAULTS)
cfg.update({"ptt": {"kind": "mouse", "code": 6}, "vocabulary": "Orbit, Claude Code, Whisper",
            "replacements": [["klód", "Claude"]], "insert_mode": "paste"})
dlg = ui.SettingsDialog(cfg, ["Mikrofon (USB headset)"], ["ggml-large-v3.bin", "ggml-large-v3-turbo.bin"],
                        True, False, lambda: 0.0, set())
wave = dlg.findChild(theme.LevelWave)
wave._timer.stop()
for i in range(200):  # a spoken sentence: syllable bumps under a slow phrase envelope, quiet before it starts
    phrase = max(0.0, math.sin(math.pi * max(0, i - 70) / 130)) if i > 70 else 0.02
    wave._samples.append(min(0.85, phrase * (0.45 + 0.4 * abs(math.sin(i * 0.9)) * abs(math.sin(i * 0.23)))))
dlg.setFixedSize(820, dlg.layout().totalHeightForWidth(820) + 40)
save(dlg, "settings")
