import ctypes
import math
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize,
                            QStandardPaths, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontMetricsF, QGuiApplication, QIcon, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient, QTextLayout)
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QToolTip,
                               QVBoxLayout, QWidget)

from . import config, downloads, hotkey, theme, vocab, voice
from .claude_usage import Usage, countdown, reset_text
from .config import MODEL_LABELS
from .sessions import STATE_LABELS, Session
from .theme import GLYPH_KEYBOARD, GLYPH_MOUSE, LISTEN, TEXT, LevelWave, Toggle, glyph_icon, style_titlebar
from .version import VERSION

MIC_GLYPH = ""  # "Microphone" in Segoe Fluent Icons / Segoe MDL2 Assets
REFRESH_GLYPH = chr(0xE72C)  # "Refresh" in Segoe Fluent Icons / Segoe MDL2 Assets
SPEAKER_GLYPH = chr(0xE767)  # "Volume"
MUTE_GLYPH = chr(0xE74F)  # "Mute"

COLORS = {  # state: (background, glyph)
    "idle": ("#2F3542", "#FFFFFF"),
    "loading": ("#5B6272", "#D7DBE3"),
    "recording": ("#E5484D", "#FFFFFF"),
    "busy": ("#F5A524", "#2A1C00"),
    "error": ("#7A1F24", "#FFB4B4"),
}


SESSION_COLORS = {  # Claude Code session state -> status dot
    "working": QColor("#5B9DFF"),
    "waiting": QColor("#F5A524"),
    "done": QColor("#3DD68C"),
    "idle": QColor("#5B6272"),
    "error": QColor("#E5484D"),
}


def paint_mic(p: QPainter, rect: QRectF, state: str) -> None:
    bg, fg = COLORS[state]
    p.setPen(QPen(QColor(0, 0, 0, 60), max(1.0, rect.width() / 40)))
    p.setBrush(theme.tint(bg) if state in ("idle", "loading") else QColor(bg))
    p.drawEllipse(rect)
    font = QFont(theme.icon_font())
    font.setPixelSize(int(rect.height() * 0.46))
    p.setFont(font)
    p.setPen(QColor(fg))
    p.drawText(rect, Qt.AlignCenter, MIC_GLYPH)


def mic_icon(state: str, size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    paint_mic(p, QRectF(1, 1, size - 2, size - 2), state)
    p.end()
    return QIcon(pm)


def _bar_color(percent: float) -> QColor:
    return QColor("#E5484D" if percent >= 90 else "#F5A524" if percent >= 70 else theme.ACCENT)


def _no_activate(widget: QWidget) -> None:
    """WS_EX_NOACTIVATE (+ tool window, topmost): clicking the window must not steal focus from the target window."""
    user32 = ctypes.windll.user32
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    hwnd = ctypes.c_void_p(int(widget.winId()))
    ex = user32.GetWindowLongPtrW(hwnd, -20)
    user32.SetWindowLongPtrW(hwnd, -20, ex | 0x08000000 | 0x00000080 | 0x00000008)


def _wrap(text: str, font: QFont, width: float, max_lines: int) -> list[str]:
    """Word-wrapped lines (\\n starts a new one); the last one ends with … when the text doesn't fit."""
    spans = []  # (start in text, length)
    offset = 0
    for para in text.split("\n"):
        layout = QTextLayout(para, font)
        layout.beginLayout()
        while (line := layout.createLine()).isValid():
            line.setLineWidth(width)
            spans.append((offset + line.textStart(), line.textLength()))
        layout.endLayout()
        offset += len(para) + 1
    lines = [text[s:s + n].strip() for s, n in spans[:max_lines]]
    if len(spans) > max_lines:
        rest = text[spans[max_lines - 1][0]:].replace("\n", " ")
        lines[-1] = QFontMetricsF(font).elidedText(rest, Qt.ElideRight, width)
    return lines


class FloatingButton(QWidget):
    """Always-on-top round mic button that never takes keyboard focus from the window you type into.

    Optionally shows a small Claude usage panel above (or below, near the top of the screen) the button.
    A second circle of the same size left of the mic mutes all of Orbit's sounds. Three small colour dots outside
    the panel's far right corner switch the colour theme; next to them sits the voice agent's chip (a planet with
    a ring and a moon), and the agent's last exchange shows at the bottom of the panel.
    """

    pressed = Signal()
    released = Signal()
    cancelled = Signal()
    moved = Signal(QPoint)  # new top-left of the button area, in screen coordinates
    menu_requested = Signal(QPoint)
    session_clicked = Signal(str)
    mute_toggled = Signal()
    theme_chosen = Signal(str)
    agent_clicked = Signal()
    connect_clicked = Signal()  # "Připojit Clauda" in the panel
    statusline_clicked = Signal()  # "Zapnout" in the panel: the yes to Orbit's status line in Claude Code

    DIAMETER = 52
    MARGIN = 10
    GAP = 8  # between the speaker circle and the mic circle
    PANEL_W = 440
    PAD = 8
    HEADER_H = 16
    ROW_H = 18
    SEP_H = 9  # gap with a hairline between the limits and the sessions
    DOT = 10  # theme colour dots, in a small pill outside the panel
    DOT_STEP = 20
    PILL_H = 22
    AGENT_D = 30  # the voice agent's chip left of the pill
    STRIP_H = 40  # the chip (with its glow), the pill and the gap to the panel
    FEED_LINE = 15  # a text line of the agent's part of the panel
    AGENT_STATUS = {"listening": "Poslouchám…", "transcribing": "Přepisuji…", "thinking": "Přemýšlím…",
                    "speaking": "Mluví", "confirm": "Mám? Řekni „jo“"}
    SEND_STATUS = {  # status of a message for a session: (label, colour or None = dim)
        "confirm": ("čeká na tvoje „jo“", "#F5A524"), "sending": ("posílám…", None), "sent": ("odesláno ✓", "#3DD68C"),
        "opened": ("otevřeno ✓", "#3DD68C"), "opening": ("otevírám…", None),
        "failed": ("nepovedlo se", "#E5484D"), "cancelled": ("zrušeno", None), "changed": ("upravuje", None),
        "expired": ("nepotvrzeno", None), "held": ("čeká na schválení v relaci", "#F5A524")}
    STALE_AFTER_S = 600
    IDLE_FADE_MS = 3000  # nothing happening for this long -> almost fully transparent
    FADED_OPACITY = 0.3

    def __init__(self, level_source):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)
        self.setCursor(Qt.PointingHandCursor)
        self._level_source = level_source
        self._level = 0.0
        self._state = "loading"
        self._phase = 0.0
        self._button_tip = ""
        self._press_global: QPoint | None = None
        self._press_pos = QPoint()
        self._press_on_button = False
        self._press_on_speaker = False
        self._dragging = False
        self._hovered = False
        self._muted = False  # no beeps, chimes or reading aloud
        self._reading = False  # an artifact summary is being read right now
        self._agent_on = False  # the voice agent is enabled: its chip sits next to the colour dots
        self._agent_key = hotkey.binding_name({"kind": "mouse", "code": hotkey.MOUSE_X1})  # its button's name
        self._agent_state = "idle"  # idle / listening / transcribing / thinking / speaking / confirm
        self._agent_feed: dict | None = None  # its last exchange, shown at the bottom of the panel
        self._feed_rect = QRectF()

        self._show_usage = False
        self._claude: bool | None = None  # Claude connected (None = still finding out); not: a call to action
        self._cta_rect = QRectF()
        self._cta_kind = ""  # what the link does: "connect" (Claude) or "statusline" (the limits' status line)
        self._usage: Usage | None = None
        self._usage_error: str | None = None
        self._forecast: datetime | None = None
        self._sessions: list[Session] = []
        self._session_rows: list[tuple[QRectF, Session]] = []
        self._attention = False  # a session waits for Pepa – don't fade out
        self._held = False  # a bubble points at the button – don't fade out either
        self._align = "right"  # which circle edge the panel lines up with
        self._below = False  # panel under the button (when the button is near the top of the screen)
        self._btn_off = QPoint()
        self._panel = QRectF()
        self._relayout(keep_button_in_place=False)

        self._timer = QTimer(self, interval=33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._clock = QTimer(self, interval=30_000)  # keeps the reset countdown current
        self._clock.timeout.connect(self.update)
        self._clock.start()
        self._fade_timer = QTimer(self, singleShot=True, interval=self.IDLE_FADE_MS)
        self._fade_timer.timeout.connect(self._fade_out)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)

    # -- geometry ---------------------------------------------------------------------------

    @property
    def _side(self) -> int:
        """The mic's square (the circle and room for the level ring around it)."""
        return self.DIAMETER + 2 * self.MARGIN

    @property
    def _slot(self) -> int:
        """Room left of the mic's square for the speaker circle."""
        return self.DIAMETER * 3 // 2 + self.GAP - self._side // 2 + 4

    @property
    def _has_panel(self) -> bool:
        return self._show_usage or bool(self._sessions) or self._show_feed

    @property
    def _show_feed(self) -> bool:
        """The agent's part of the panel: its last exchange, or just its title row while it's busy."""
        return bool(self._agent_feed) or self._agent_state != "idle"

    def _panel_height(self) -> int:
        h = self.PAD + self.HEADER_H + self.PAD - 2
        if self._show_usage:
            h += (len(self._usage.limits) if self._usage and self._usage.limits and self._claude is not False
                  else 1) * self.ROW_H
        if self._sessions:
            h += (self.SEP_H if self._show_usage else 0) + len(self._sessions) * self.ROW_H
        if self._show_feed:
            h += self.SEP_H + self.ROW_H + len(self._feed_rows()) * self.FEED_LINE
        return h

    def _relayout(self, keep_button_in_place: bool = True) -> None:
        anchor = self.button_pos()
        side, slot = self._side, self._slot
        if not self._has_panel:
            self._panel = QRectF()
            self._btn_off = QPoint(slot, 0)
            self.setFixedSize(slot + side, side)
        else:
            ph = self._panel_height()
            if self._align == "center":  # both circles centered under the panel
                w = max(self.PANEL_W, slot + side)
                bx, px = (w - slot - side) // 2 + slot, (w - self.PANEL_W) // 2
            elif self._align == "right":  # panel's right edge = the mic circle's
                w = self.PANEL_W + self.MARGIN
                bx, px = w - side, 0
            else:  # panel's left edge = the speaker circle's
                px = 4
                w = px + self.PANEL_W
                bx = slot
            by, py = (0, side) if self._below else (self.STRIP_H + ph, self.STRIP_H)  # dots on the far side
            self._btn_off = QPoint(bx, by)
            self._panel = QRectF(px, py, self.PANEL_W, ph)
            self.setFixedSize(w, self.STRIP_H + ph + side)
        if keep_button_in_place:
            self.move(anchor - self._btn_off)
        self.update()

    def button_pos(self) -> QPoint:
        return self.pos() + self._btn_off

    def button_rect(self, pos: QPoint) -> QRect:
        """Both circles' square area (speaker and mic) when the mic square's top left is at pos."""
        return QRect(pos.x() - self._slot, pos.y(), self._slot + self._side, self._side)

    def place_button(self, pos: QPoint) -> None:
        self.move(pos - self._btn_off)
        self._auto_align()

    def _auto_align(self) -> None:
        """Keep the panel on screen: line it up with the circle edge that faces the screen's middle."""
        if not self._has_panel:
            return
        center = self.button_pos() + QPoint(self._side // 2, self._side // 2)
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        third = geo.width() / 6
        align = "right" if center.x() > geo.center().x() + third else \
            "left" if center.x() < geo.center().x() - third else "center"
        below = self.button_pos().y() - self._panel_height() - self.STRIP_H < geo.top()
        if (align, below) != (self._align, self._below):
            self._align, self._below = align, below
            self._relayout()

    def _button_center(self) -> QPointF:
        return QPointF(self._btn_off.x() + self._side / 2, self._btn_off.y() + self._side / 2)

    def _speaker_center(self) -> QPointF:
        return self._button_center() - QPointF(self.DIAMETER + self.GAP, 0)

    def _on_speaker(self, pos: QPointF) -> bool:
        d = pos - self._speaker_center()
        return math.hypot(d.x(), d.y()) <= self.DIAMETER / 2 + 2

    def _dots(self) -> list[tuple[str, QPointF]]:
        """Centres of the theme colour dots: lined up with the panel's right end, just outside it."""
        if not self._has_panel:
            return []
        gap = 4 + self.AGENT_D / 2  # from the panel to the strip's middle
        y = self._panel.bottom() + gap if self._below else self._panel.top() - gap
        first = self._panel.right() - self.PILL_H / 2 - self.DOT_STEP * (len(theme.THEMES) - 1)
        return [(name, QPointF(first + i * self.DOT_STEP, y)) for i, name in enumerate(theme.THEMES)]

    def _dot_at(self, pos: QPointF) -> str | None:
        return next((name for name, c in self._dots()
                     if math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= self.DOT_STEP / 2), None)

    def _agent_center(self) -> QPointF | None:
        """The agent's chip: left of the colour pill."""
        dots = self._dots()
        if not dots or not self._agent_on:
            return None
        first = dots[0][1]
        return QPointF(first.x() - self.PILL_H / 2 - 8 - self.AGENT_D / 2, first.y())

    def _on_agent(self, pos: QPointF) -> bool:
        c = self._agent_center()
        return c is not None and math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= self.AGENT_D / 2 + 2

    # -- state ------------------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        _no_activate(self)

    def bubble_anchor(self) -> tuple[QRect, str | None]:
        """Both circles (speaker and mic) in screen coordinates, and where the panel is ('above', 'below' or None)."""
        c = self.mapToGlobal(self._button_center().toPoint())
        r = self.DIAMETER // 2
        panel = ("below" if self._below else "above") if self._has_panel else None
        left = c.x() - r - self.DIAMETER - self.GAP
        return QRect(left, c.y() - r, c.x() + r - left, 2 * r), panel

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.update()
            self._wake()
        self._sync_timer()

    def _sync_timer(self) -> None:
        animate = self._state in ("recording", "busy", "loading") or self._agent_state != "idle"
        if animate and not self._timer.isActive():
            self._timer.start()
        elif not animate and self._timer.isActive():
            self._timer.stop()
            self.update()

    def set_button_tip(self, text: str) -> None:
        self._button_tip = text

    def set_usage_visible(self, visible: bool) -> None:
        if visible != self._show_usage:
            self._show_usage = visible
            self._relayout()
            self._auto_align()

    def set_usage(self, usage: Usage | None, error: str | None) -> None:
        rows_before = self._panel_height()
        self._usage, self._usage_error = usage, error
        if self._show_usage and self._panel_height() != rows_before:
            self._relayout()
            self._auto_align()
        self.update()

    def set_claude(self, connected: bool | None) -> None:
        """Without Claude the limits part of the panel invites to connect it instead of showing empty bars."""
        if connected != self._claude:
            self._resize_after(lambda: setattr(self, "_claude", connected))

    def set_forecast(self, eta: datetime | None) -> None:
        """When the 5-hour limit runs out at the current pace (None = not before it resets)."""
        self._forecast = eta
        self.update()

    def set_sessions(self, sessions: list[Session]) -> None:
        count_before = len(self._sessions)
        self._sessions = sessions
        if len(sessions) != count_before:
            self._relayout()
            self._auto_align()
        self.update()

    def set_attention(self, on: bool) -> None:
        if on != self._attention:
            self._attention = on
            self._wake()

    def set_held(self, on: bool) -> None:
        if on != self._held:
            self._held = on
            self._wake()

    def set_muted(self, on: bool) -> None:
        if on != self._muted:
            self._muted = on
            self.update()

    def set_agent(self, on: bool, key: str = "") -> None:
        """key: the name of the agent's button (for its tooltip)."""
        self._agent_key = key or self._agent_key
        if on != self._agent_on:
            self._agent_on = on
            self.update()

    def set_agent_state(self, state: str) -> None:
        if state != self._agent_state:
            self._resize_after(lambda: setattr(self, "_agent_state", state))
            self._wake()
            self._sync_timer()

    def set_agent_feed(self, feed: dict | None) -> None:
        """The agent's last exchange (you, reply, send = dict name, folder, message, status, session_id) or None."""
        self._resize_after(lambda: setattr(self, "_agent_feed", feed or None))

    def _resize_after(self, change) -> None:
        """Applies a change of the agent's part and resizes the window if the panel grew or shrank."""
        size = (self._has_panel, self._panel_height())
        change()
        if (self._has_panel, self._panel_height()) != size:
            self._relayout()
            self._auto_align()
        self.update()

    def set_reading(self, on: bool) -> None:
        if on != self._reading:
            self._reading = on
            self.update()
            self._wake()

    def _stale(self) -> bool:
        if self._usage is None:
            return True
        age = (datetime.now(timezone.utc) - self._usage.fetched_at).total_seconds()
        return age > self.STALE_AFTER_S

    def _tick(self):
        self._phase = (self._phase + 0.12) % (2 * math.pi)
        target = self._level_source() if self._state == "recording" or self._agent_state == "listening" else 0.0
        self._level += (target - self._level) * 0.45
        self.update()

    # -- fading out when nothing happens ----------------------------------------------------

    def wake(self) -> None:
        """Something happened worth a look – full opacity for a moment."""
        self._wake()

    def _wake(self) -> None:
        """Fully visible now; when idle, fade out again after IDLE_FADE_MS."""
        self._animate_opacity(1.0, 150)
        if self._can_fade():
            self._fade_timer.start()
        else:
            self._fade_timer.stop()

    def _can_fade(self) -> bool:
        return self._state == "idle" and self._agent_state == "idle" and not (
            self._hovered or self._attention or self._held or self._reading)

    def _fade_out(self) -> None:
        if QApplication.activePopupWidget():  # our context menu is open
            self._fade_timer.start()
        elif self._can_fade() and self._press_global is None:
            self._animate_opacity(self.FADED_OPACITY, 600)

    def _animate_opacity(self, target: float, ms: int) -> None:
        self._fade.stop()
        if abs(self.windowOpacity() - target) > 0.01:
            self._fade.setDuration(ms)
            self._fade.setStartValue(self.windowOpacity())
            self._fade.setEndValue(target)
            self._fade.start()

    def enterEvent(self, event):
        self._hovered = True
        self._wake()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._wake()
        super().leaveEvent(event)

    # -- painting ---------------------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._has_panel:
            self._paint_panel(p)
            self._paint_dots(p)
            self._paint_agent_chip(p)
        c = self._button_center()
        r = self.DIAMETER / 2
        if self._state == "recording":
            ring = r + 2 + self._level * (self.MARGIN - 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(229, 72, 77, 90))
            p.drawEllipse(c, ring, ring)
        paint_mic(p, QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), self._state)
        if self._state in ("busy", "loading"):
            pen = QPen(QColor(COLORS[self._state][1]), 3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            arc = QRectF(c.x() - r + 4, c.y() - r + 4, 2 * r - 8, 2 * r - 8)
            p.drawArc(arc, int(-math.degrees(self._phase) * 16 * 2), 90 * 16)
        self._paint_speaker(p)

    def _paint_speaker(self, p: QPainter) -> None:
        """The speaker circle, styled like the mic: speaker = Orbit makes sounds, grey crossed speaker = muted,
        accent colour = reading aloud right now."""
        c, r = self._speaker_center(), self.DIAMETER / 2
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        p.setPen(QPen(QColor(0, 0, 0, 60), max(1.0, rect.width() / 40)))
        p.setBrush(QColor(theme.ACCENT) if self._reading else theme.tint("#2F3542"))
        p.drawEllipse(rect)
        font = QFont(theme.icon_font())
        font.setPixelSize(int(rect.height() * 0.46))
        p.setFont(font)
        p.setPen(QColor("#8B96AD" if self._muted else "#FFFFFF"))
        p.drawText(rect, Qt.AlignCenter, MUTE_GLYPH if self._muted else SPEAKER_GLYPH)

    def _speaker_tooltip(self) -> str:
        if self._muted:
            return "Orbit je ztlumený: nepípá, bubliny jsou bez zvuku a nic nečte nahlas.\nKlikni a zvuky zapneš."
        if self._reading:
            return "Čtu nahlas. Klikni a Orbit ztlumíš."
        return "Zvuky jsou zapnuté: pípání, zvuky bublin a předčítání.\nKlikni a Orbit ztlumíš."

    def _paint_dots(self, p: QPainter) -> None:
        """Theme colour dots in a small pill of the panel's style; a ring marks the current one."""
        dots = self._dots()
        first, last = dots[0][1], dots[-1][1]
        half = self.PILL_H / 2
        pill = QRectF(first.x() - half, first.y() - half, last.x() - first.x() + self.PILL_H, self.PILL_H)
        bg = theme.tint("#181B22")
        bg.setAlpha(235)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.setBrush(bg)
        p.drawRoundedRect(pill.adjusted(0.5, 0.5, -0.5, -0.5), half, half)
        r = self.DOT / 2
        for name, c in dots:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.THEMES[name][1]))
            p.drawEllipse(c, r, r)
            if name == theme.current:
                p.setPen(QPen(QColor("#E6E8EC"), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, r + 2.5, r + 2.5)

    def _paint_agent_chip(self, p: QPainter) -> None:
        """The voice agent: a small planet with a ring and a moon. Red while it listens, the moon circles while it
        thinks, it glows while it speaks, orange while it waits for Pepa's yes."""
        c = self._agent_center()
        if c is None:
            return
        state, r = self._agent_state, self.AGENT_D / 2
        color = QColor(LISTEN if state == "listening" else "#F5A524" if state == "confirm" else theme.ACCENT)
        p.setPen(Qt.NoPen)
        if state in ("listening", "speaking", "confirm"):
            pulse = self._level if state == "listening" else 0.5 + 0.5 * math.sin(self._phase * 2)
            halo = QColor(color)
            halo.setAlpha(int(45 + 60 * pulse))
            p.setBrush(halo)
            p.drawEllipse(c, r + 1.5 + 3.5 * pulse, r + 1.5 + 3.5 * pulse)
        bg = QColor(LISTEN) if state == "listening" else theme.tint("#181B22")
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.setBrush(bg)
        p.drawEllipse(c, r - 0.5, r - 0.5)

        ink = QColor("#FFFFFF") if state == "listening" else color
        a, b, planet, moon = r * 0.8, r * 0.27, r * 0.38, r * 0.15
        t = self._phase * 1.6 if state in ("transcribing", "thinking") else math.radians(40)
        moon_at, moon_front = QPointF(a * math.cos(t), b * math.sin(t)), math.sin(t) >= 0
        ring_pen, gap_pen = QPen(ink, 1.6), QPen(bg, 4.0)  # the gap keeps the ring apart from the planet
        ring_pen.setCapStyle(Qt.RoundCap)
        p.save()
        p.translate(c)
        p.rotate(-24)
        ring = QRectF(-a, -b, 2 * a, 2 * b)

        def draw_moon():
            p.setPen(QPen(bg, 1.6))
            p.setBrush(ink)
            p.drawEllipse(moon_at, moon, moon)

        far = QColor(ink)
        far.setAlphaF(0.7)
        p.setPen(QPen(far, 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawArc(ring, 0, 180 * 16)  # the far half of the ring, behind the planet
        if not moon_front:
            draw_moon()
        shade = QRadialGradient(QPointF(-planet * 0.45, -planet * 0.5), planet * 1.6)  # lit from the top left
        shade.setColorAt(0.0, ink.lighter(135))
        shade.setColorAt(1.0, ink.darker(150))
        p.setPen(Qt.NoPen)
        p.setBrush(shade)
        p.drawEllipse(QPointF(0, 0), planet, planet)
        p.setBrush(Qt.NoBrush)
        p.setPen(gap_pen)
        p.drawArc(ring, 200 * 16, 140 * 16)  # the near half, in front of it
        p.setPen(ring_pen)
        p.drawArc(ring, 180 * 16, 180 * 16)
        if moon_front:
            draw_moon()
        p.restore()

    def _agent_tooltip(self) -> str:
        return (f"Agent Orbit: podrž {hotkey.in_sentence(self._agent_key)} a mluv. Nebo klikni (tím tlačítkem nebo "
                "sem) a mluv, poslouchá, dokud se neodmlčíš.\nZeptej se, co dělají relace, nebo mu řekni, co má kam "
                "napsat. Než něco pošle, přečte ti to a počká na tvoje „jo“.")

    def _paint_panel(self, p: QPainter) -> None:
        rect = self._panel
        bg = theme.tint("#181B22")
        bg.setAlpha(235)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.setBrush(bg)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        font = QFont("Segoe UI")
        font.setPixelSize(11)
        bold = QFont(font)
        bold.setWeight(QFont.DemiBold)
        text, dim = QColor("#E6E8EC"), QColor("#9AA1AD")
        x, right = rect.left() + 10, rect.right() - 10
        y = rect.top() + self.PAD

        header = QRectF(x, y, right - x, self.HEADER_H)
        p.setFont(bold)
        p.setPen(dim)
        p.drawText(header, Qt.AlignLeft | Qt.AlignVCenter, "Claude")
        if self._show_usage and self._claude is not False:
            self._paint_header_note(p, header, font, text, dim)
        y += self.HEADER_H
        if self._show_usage:
            y = self._paint_limits(p, x, right, y, font, bold, text, dim)
        self._session_rows = []
        if self._sessions:
            if self._show_usage:
                p.setPen(QPen(QColor(255, 255, 255, 22), 1))
                p.drawLine(QPointF(x, y + self.SEP_H / 2), QPointF(right, y + self.SEP_H / 2))
                y += self.SEP_H
            y = self._paint_sessions(p, x, right, y, font, bold, text, dim)
        self._feed_rect = QRectF()
        if self._show_feed:
            p.setPen(QPen(QColor(255, 255, 255, 22), 1))
            p.drawLine(QPointF(x, y + self.SEP_H / 2), QPointF(right, y + self.SEP_H / 2))
            self._paint_feed(p, x, right, y + self.SEP_H, font, bold, text, dim)

    def _paint_header_note(self, p: QPainter, header: QRectF, font: QFont, text: QColor, dim: QColor) -> None:
        """Right side of the header: when the 5-hour window resets – or when it runs out first at this pace."""
        session = self._usage.get("session") if self._usage else None
        note, refresh_icon = "", False
        if self._usage_error and self._stale():
            note = "neaktuální"
        elif self._forecast:
            local = self._forecast.astimezone()
            note = f"dojde v {local.hour}:{local.minute:02d}"
            p.setPen(QColor("#F5A524"))
        elif session and session.resets_at:
            note, refresh_icon = countdown(session.resets_at), True
        p.setFont(font)
        p.drawText(header, Qt.AlignRight | Qt.AlignVCenter, note)
        if refresh_icon:
            icon_font = QFont(theme.icon_font())
            icon_font.setPixelSize(12)
            p.setFont(icon_font)
            p.setPen(text)
            text_w = QFontMetricsF(font).horizontalAdvance(note)
            p.drawText(QRectF(header.right() - text_w - 18, header.top(), 14, header.height()),
                       Qt.AlignCenter, REFRESH_GLYPH)

    def _paint_link_row(self, p: QPainter, row: QRectF, note: str, link: str, kind: str, font: QFont, bold: QFont,
                        dim: QColor) -> None:
        """A dim note with a small call to action on the right (see _cta_kind)."""
        link_w = QFontMetricsF(bold).horizontalAdvance(link)
        p.setFont(font)
        p.setPen(dim)
        p.drawText(row.adjusted(0, 0, -link_w - 10, 0), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(font).elidedText(note, Qt.ElideRight, row.width() - link_w - 10))
        p.setFont(bold)
        p.setPen(QColor(theme.ACCENT))
        p.drawText(row, Qt.AlignRight | Qt.AlignVCenter, link)
        self._cta_rect, self._cta_kind = row.adjusted(-6, 0, 6, 0), kind

    def _paint_limits(self, p: QPainter, x: float, right: float, y: float, font: QFont, bold: QFont, text: QColor,
                      dim: QColor) -> float:
        self._cta_rect, self._cta_kind = QRectF(), ""
        row = QRectF(x, y, right - x, self.ROW_H)
        if self._claude is False:  # not connected: a small call to action instead of empty bars
            self._paint_link_row(p, row, "Limity uvidíš, až připojíš Claude Code.", "Připojit Clauda →", "connect",
                                 font, bold, dim)
            return y + self.ROW_H
        if self._usage and not self._usage.limits and self._usage.action == "statusline":
            self._paint_link_row(p, row, self._usage.note, "Zapnout →", "statusline", font, bold, dim)
            return y + self.ROW_H
        if not self._usage or not self._usage.limits:
            p.setPen(dim)
            p.setFont(font)
            msg = self._usage.note if self._usage and self._usage.note else \
                "Načítám…" if not self._usage_error else "Nedostupné – najeď myší"
            p.drawText(row, Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetricsF(font).elidedText(msg, Qt.ElideRight, row.width()))
            return y + self.ROW_H

        if self._stale():
            p.setOpacity(0.5)
        label_w, pct_w = 44, 36
        for lim in self._usage.limits:
            row = QRectF(x, y, right - x, self.ROW_H)
            p.setFont(bold)
            p.setPen(text)
            p.drawText(QRectF(row.left(), row.top(), label_w, row.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       lim.label)
            p.setFont(font)
            p.drawText(QRectF(row.right() - pct_w, row.top(), pct_w, row.height()),
                       Qt.AlignRight | Qt.AlignVCenter, f"{lim.percent:.0f} %")
            bar = QRectF(row.left() + label_w + 4, row.center().y() - 3, row.width() - label_w - pct_w - 10, 6)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawRoundedRect(bar, 3, 3)
            filled = QRectF(bar.left(), bar.top(), bar.width() * min(100.0, max(0.0, lim.percent)) / 100, bar.height())
            if filled.width() > 0:
                p.setBrush(_bar_color(lim.percent))
                p.drawRoundedRect(filled, 3, 3)
            y += self.ROW_H
        p.setOpacity(1.0)
        return y

    def _paint_sessions(self, p: QPainter, x: float, right: float, y: float, font: QFont, bold: QFont,
                        text: QColor, dim: QColor) -> float:
        """One row per Claude Code session: status dot, its topic, its folder, what it's doing, how full its
        context is."""
        pct_w, state_w, gap = 34, 70, 10
        metrics = QFontMetricsF(font)
        folder_w = min(110.0, max(metrics.horizontalAdvance(s.folder) for s in self._sessions)) if any(
            s.topic for s in self._sessions) else 0.0  # no topics: the names already are the folders
        for s in self._sessions:
            row = QRectF(x, y, right - x, self.ROW_H)
            self._session_rows.append((row.adjusted(-6, 0, 6, 0), s))
            p.setPen(Qt.NoPen)
            p.setBrush(SESSION_COLORS[s.state])
            p.drawEllipse(QPointF(row.left() + 4, row.center().y()), 3.5, 3.5)
            p.setFont(bold)
            p.setPen(text)
            name_rect = QRectF(row.left() + 13, row.top(),
                               row.width() - 13 - (folder_w + gap if folder_w else 0) - state_w - pct_w, row.height())
            p.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetricsF(bold).elidedText(s.name, Qt.ElideRight, name_rect.width()))
            p.setFont(font)
            if folder_w and s.topic:
                p.setPen(dim)
                p.drawText(QRectF(name_rect.right() + gap, row.top(), folder_w, row.height()),
                           Qt.AlignLeft | Qt.AlignVCenter, metrics.elidedText(s.folder, Qt.ElideRight, folder_w))
            p.setPen(SESSION_COLORS[s.state] if s.state in ("waiting", "error") else dim)
            p.drawText(QRectF(row.right() - pct_w - state_w, row.top(), state_w, row.height()),
                       Qt.AlignRight | Qt.AlignVCenter, STATE_LABELS[s.state])
            if s.context is not None:
                p.setPen(QColor("#F5A524") if s.context >= 0.8 else dim)
                p.drawText(QRectF(row.right() - pct_w, row.top(), pct_w, row.height()),
                           Qt.AlignRight | Qt.AlignVCenter, f"{s.context * 100:.0f} %")
            y += self.ROW_H
        return y

    @staticmethod
    def _feed_font() -> QFont:
        font = QFont("Segoe UI")
        font.setPixelSize(11)
        return font

    def _feed_rows(self) -> list[tuple[str, str]]:
        """The agent's part of the panel below its title row, as (style, text) lines."""
        feed, font, width = self._agent_feed or {}, self._feed_font(), self.PANEL_W - 20
        rows = [("you", feed["you"])] if feed.get("you") else []
        if feed.get("reply"):
            rows += [("reply", line) for line in _wrap(feed["reply"], font, width, 3)]
        if feed.get("send"):
            rows.append(("target", ""))
            # all of it while it waits for the yes (muted, nothing is read out: this is what gets approved)
            lines = 10 if feed["send"].get("status") == "confirm" else 4
            rows += [("message", line) for line in _wrap(feed["send"]["message"], font, width - 10, lines)]
        return rows

    def _paint_feed(self, p: QPainter, x: float, right: float, y: float, font: QFont, bold: QFont, text: QColor,
                    dim: QColor) -> None:
        """The voice agent's last exchange: what Pepa said, its answer, and which session it sends what to."""
        feed, metrics, bold_metrics = self._agent_feed, QFontMetricsF(font), QFontMetricsF(bold)
        top = y
        head = QRectF(x, y, right - x, self.ROW_H)
        p.setFont(bold)
        p.setPen(QColor(theme.ACCENT))
        p.drawText(head, Qt.AlignLeft | Qt.AlignVCenter, "Agent Orbit")
        p.setFont(font)
        p.setPen(QColor(LISTEN) if self._agent_state == "listening" else
                 QColor("#F5A524") if self._agent_state == "confirm" else dim)
        p.drawText(head, Qt.AlignRight | Qt.AlignVCenter, self.AGENT_STATUS.get(self._agent_state, ""))
        y += self.ROW_H
        for style, line in self._feed_rows():
            row = QRectF(x, y, right - x, self.FEED_LINE)
            if style == "you":
                p.setPen(dim)
                p.drawText(row, Qt.AlignLeft | Qt.AlignVCenter,
                           metrics.elidedText(f"Ty: {line}", Qt.ElideRight, row.width()))
            elif style == "reply":
                p.setPen(text)
                p.drawText(row, Qt.AlignLeft | Qt.AlignVCenter, line)
            elif style == "target":  # → session topic, its folder, and how the message is doing
                send = feed["send"]
                label, color = self.SEND_STATUS.get(send.get("status"), ("", None))
                label_w = metrics.horizontalAdvance(label) + 10 if label else 0
                name = f"→ {send['name']}"
                name_w = min(bold_metrics.horizontalAdvance(name), row.width() - label_w - 70)
                p.setFont(bold)
                p.setPen(text)
                p.drawText(QRectF(row.left(), row.top(), name_w, row.height()), Qt.AlignLeft | Qt.AlignVCenter,
                           bold_metrics.elidedText(name, Qt.ElideRight, name_w))
                p.setFont(font)
                if send.get("folder"):
                    folder = QRectF(row.left() + name_w + 8, row.top(), row.width() - name_w - 8 - label_w,
                                    row.height())
                    p.setPen(dim)
                    p.drawText(folder, Qt.AlignLeft | Qt.AlignVCenter,
                               metrics.elidedText(send["folder"], Qt.ElideRight, folder.width()))
                p.setPen(QColor(color) if color else dim)
                p.drawText(row, Qt.AlignRight | Qt.AlignVCenter, label)
            else:  # the message itself, as a quote with an accent bar
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.ACCENT))
                p.drawRect(QRectF(row.left() + 1, row.top(), 2, row.height()))
                p.setPen(text)
                p.drawText(row.adjusted(10, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, line)
            y += self.FEED_LINE
        self._feed_rect = QRectF(x - 6, top, right - x + 12, y - top)

    def _feed_tooltip(self) -> str:
        feed = self._agent_feed or {}
        lines = [f"Ty: {feed['you']}"] if feed.get("you") else []
        if feed.get("reply"):
            lines.append(f"Agent: {feed['reply']}")
        if (send := feed.get("send")) and send.get("tool") == "page":
            lines.append(f"Stránka v Chromu: {send['name']}\n{send['message']}")
        elif send:
            lines.append(f"Pro relaci {send['name']} ({send['folder']}): {send['message']}")
            if send.get("session_id"):
                lines.append("Klikni a přepneš se do ní.")
        return "\n".join(lines)

    def _session_at(self, pos: QPointF) -> Session | None:
        return next((s for rect, s in self._session_rows if rect.contains(pos)), None)

    def _usage_tooltip(self) -> str:
        if self._claude is False:
            return ("Limity předplatného Claude (5 hodin, týden) a přehled relací Claude Code uvidíš tady, až připojíš "
                    "Claude Code.\nKlikni a připojíš ho. Skrýt to jde v nastavení: Využití Clauda nad tlačítkem.")
        lines = []
        if self._usage and self._usage.source == "statusline":
            if self._usage.updated_at:
                local = self._usage.updated_at.astimezone()
                lines.append(f"Využití Clauda podle Claude Code (poslední zpráva v {local.hour}:{local.minute:02d}, "
                             "práce v prohlížeči nebo v mobilu se ukáže až s další zprávou)")
            elif self._usage.action == "statusline":
                lines.append("Limity Orbit čte ze stavového řádku Claude Code (lišta pod místem, kam píšeš). Klikni "
                             "na Zapnout a Orbit si ho do Claude Code přidá. Tvůj vlastní stavový řádek zůstane vidět.")
            elif self._usage.note:
                lines.append(self._usage.note)
        elif self._usage:
            local = self._usage.fetched_at.astimezone()
            lines.append(f"Využití Clauda (aktualizováno v {local.hour}:{local.minute:02d})")
        if self._usage:
            for lim in self._usage.limits:
                reset = reset_text(lim.resets_at)
                lines.append(f"{lim.title}: {lim.percent:.0f} %" + (f" – {reset}" if reset else ""))
        if self._forecast:
            local = self._forecast.astimezone()
            lines.append(f"Při současném tempu 5hodinové okno dojde v {local.hour}:{local.minute:02d}, "
                         "dřív než se obnoví.")
        if self._usage_error:
            lines.append(("⚠ " if lines else "") + self._usage_error)
        return "\n".join(lines) or "Načítám využití Clauda…"

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            pos = event.position() if hasattr(event, "position") else QPointF(event.pos())
            session, dot = self._session_at(pos), self._dot_at(pos)
            if session:
                tip = session.tooltip()
            elif self._feed_rect.contains(pos):
                tip = self._feed_tooltip()
            elif self._has_panel and self._panel.contains(pos):
                tip = self._usage_tooltip()
            elif self._on_agent(pos):
                tip = self._agent_tooltip()
            elif dot:
                tip = f"Barva: {theme.THEMES[dot][0]}"
            else:
                tip = self._speaker_tooltip() if self._on_speaker(pos) else self._button_tip
            QToolTip.showText(event.globalPos(), tip, self)
            return True
        return super().event(event)

    # -- mouse ------------------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_pos = self.pos()
            self._dragging = False
            d = event.position() - self._button_center()
            self._press_on_speaker = self._on_speaker(event.position())
            self._press_on_button = not self._press_on_speaker and math.hypot(d.x(), d.y()) <= self._side / 2
            if self._press_on_button:
                self.pressed.emit()
        elif event.button() == Qt.RightButton:
            self.menu_requested.emit(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self._press_global is None:
            return
        delta = event.globalPosition().toPoint() - self._press_global
        if not self._dragging and delta.manhattanLength() > 6:
            self._dragging = True  # it's a drag, not push-to-talk
            if self._press_on_button:
                self.cancelled.emit()
        if self._dragging:
            self.move(self._press_pos + delta)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._press_global is None:
            return
        self._press_global = None
        if self._dragging:
            self._auto_align()
            self.moved.emit(self.button_pos())
        elif self._press_on_button:
            self.released.emit()
        elif self._press_on_speaker:
            self.mute_toggled.emit()
        elif self._on_agent(event.position()):
            self.agent_clicked.emit()
        elif dot := self._dot_at(event.position()):
            self.theme_chosen.emit(dot)
        elif self._cta_rect.contains(event.position()):
            (self.statusline_clicked if self._cta_kind == "statusline" else self.connect_clicked).emit()
        elif self._feed_rect.contains(event.position()) and (self._agent_feed or {}).get("send", {}).get("session_id"):
            self.session_clicked.emit(self._agent_feed["send"]["session_id"])
        elif session := self._session_at(event.position()):
            self.session_clicked.emit(session.id)


class Bubble(QWidget):
    """Orbit's notification: a card in the panel's style whose tail points at the mic button.
    Never takes focus. Click = clicked + close, right click = close, hovering keeps it open."""

    clicked = Signal()
    closed = Signal()

    W = 330
    PAD = 12
    ICON = 30
    TAIL = 8
    SHADOW = 12
    GAP = 6  # between the tail tip and the circle
    KINDS = {  # kind: (color, Segoe Fluent Icons glyph, how long it stays)
        "done": ("#3DD68C", chr(0xE73E), 7000),  # CheckMark
        "waiting": ("#F5A524", chr(0xE897), 12000),  # Help
        "error": ("#E5484D", chr(0xE171), 10000),  # Important
        "info": ("#5B9DFF", chr(0xE946), 7000),  # Info
    }

    def __init__(self, kind: str, title: str, text: str, note: str = ""):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.PointingHandCursor)
        self._color, self._glyph, self._duration = self.KINDS[kind]
        self._title, self._note = title, note
        self._title_font = QFont("Segoe UI Variable Text")
        self._title_font.setPixelSize(13)
        self._title_font.setWeight(QFont.DemiBold)
        self._text_font = QFont("Segoe UI Variable Text")
        self._text_font.setPixelSize(12)
        self._lines = _wrap(text, self._text_font, self.W - 2 * self.PAD - self.ICON - 12, 4)
        line_h = QFontMetricsF(self._text_font).lineSpacing()
        self._card_h = int(self.PAD * 2 + max(self.ICON, 18 + (3 + len(self._lines) * line_h if self._lines else 0)))
        self._tail = None  # which side of the card the tail sticks out of: "left", "right" or None
        self._tail_y = 0.0
        self._closing = False
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.dismiss)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._slide = QPropertyAnimation(self, b"pos", self)

    def _card(self) -> QRectF:
        x = self.SHADOW + (self.TAIL if self._tail == "left" else 0)
        return QRectF(x, self.SHADOW, self.W, self._card_h)

    def show_near(self, circle: QRect | None, panel: str | None = None) -> None:
        """circle: the mic button on screen (None = the button is hidden: bottom right corner, no tail);
        panel: 'above' / 'below' / None – where the limits panel is, so the bubble stays clear of it."""
        screen = (QGuiApplication.screenAt(circle.center()) if circle else None) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        s = self.SHADOW
        if circle is None:
            self.setFixedSize(self.W + 2 * s, self._card_h + 2 * s)
            target = QPoint(geo.right() - self.W - s - 12, geo.bottom() - self._card_h - s - 12)
            start = target + QPoint(0, 10)
        else:
            self._tail = "right" if circle.center().x() > geo.center().x() else "left"
            self.setFixedSize(self.W + self.TAIL + 2 * s, self._card_h + 2 * s)
            top = (circle.top() if panel == "above" else circle.bottom() - self._card_h if panel == "below"
                   else circle.center().y() - self._card_h // 2)
            top = max(geo.top() + 8, min(top, geo.bottom() - 8 - self._card_h))
            if self._tail == "right":
                x, dx = circle.left() - self.GAP - self.TAIL - self.W - s, 10
            else:
                x, dx = circle.left() + circle.width() + self.GAP - s, -10
            target = QPoint(x, top - s)
            start = target + QPoint(dx, 0)  # slides out of the button
            self._tail_y = min(max(circle.center().y() - top, 16), self._card_h - 16) + s
        self.move(start)
        self.setWindowOpacity(0.0)
        self.show()
        self._fade.setDuration(180)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._slide.setDuration(260)
        self._slide.setEasingCurve(QEasingCurve.OutCubic)
        self._slide.setStartValue(start)
        self._slide.setEndValue(target)
        self._slide.start()
        self._timer.start(self._duration)

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._fade.stop()
        self._fade.setDuration(220)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self.close)
        self._fade.start()
        self.closed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        _no_activate(self)

    def enterEvent(self, event):
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._closing:
            self._timer.start(2500)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        self.dismiss()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        card = self._card()
        p.setPen(Qt.NoPen)
        for i in range(1, 7):  # soft shadow
            p.setBrush(QColor(0, 0, 0, 9))
            p.drawRoundedRect(card.adjusted(-i * 1.6, -i * 1.2 + 2, i * 1.6, i * 1.6 + 2), 12 + i, 12 + i)

        shape = QPainterPath()
        shape.addRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        if self._tail:
            edge = card.right() - 1 if self._tail == "right" else card.left() + 1
            tip = card.right() + self.TAIL if self._tail == "right" else card.left() - self.TAIL
            tail = QPainterPath()
            tail.addPolygon(QPolygonF([QPointF(edge, self._tail_y - 7), QPointF(tip, self._tail_y),
                                       QPointF(edge, self._tail_y + 7)]))
            shape = shape.united(tail)
        bg = theme.tint("#181B22")
        bg.setAlpha(245)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.setBrush(bg)
        p.drawPath(shape)

        color = QColor(self._color)
        icon = QRectF(card.left() + self.PAD, card.top() + self.PAD, self.ICON, self.ICON)
        halo = QColor(color)
        halo.setAlpha(38)
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(icon)
        glyph_font = QFont(theme.icon_font())
        glyph_font.setPixelSize(15)
        p.setFont(glyph_font)
        p.setPen(color)
        p.drawText(icon, Qt.AlignCenter, self._glyph)

        x = icon.right() + 12
        right = card.right() - self.PAD
        title = QRectF(x, card.top() + self.PAD - 1, right - x, 18)
        note_w = 0.0
        if self._note:
            note_font = QFont(self._text_font)
            note_font.setPixelSize(11)
            note_w = QFontMetricsF(note_font).horizontalAdvance(self._note) + 10
            p.setFont(note_font)
            p.drawText(title, Qt.AlignRight | Qt.AlignVCenter, self._note)  # pen is still the kind's color
        p.setFont(self._title_font)
        p.setPen(QColor("#E6E8EC"))
        p.drawText(title.adjusted(0, 0, -note_w, 0), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(self._title_font).elidedText(self._title, Qt.ElideRight, title.width() - note_w))

        p.setFont(self._text_font)
        p.setPen(QColor("#AEB5C2"))
        line_h = QFontMetricsF(self._text_font).lineSpacing()
        y = title.bottom() + 3
        for line in self._lines:
            p.drawText(QRectF(x, y, right - x, line_h), Qt.AlignLeft | Qt.AlignVCenter, line)
            y += line_h


_NON_DEDICATED_VK = set(range(0x08, 0x0E)) | set(range(0x20, 0x5B)) | set(range(0x60, 0x70)) | set(range(0xBA, 0xE3))


def _repolish(widget: QWidget, **props) -> None:
    for name, value in props.items():
        widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _label(text: str, role: str | None = None, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    label.setWordWrap(wrap)
    return label


def _combo() -> QComboBox:
    """A combo box that doesn't make its column as wide as its longest item (long mic names, model labels)."""
    combo = QComboBox()
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(16)
    return combo


def _field(title: str, widget: QWidget, hint: str | None = None) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(5)
    box.addWidget(_label(title))
    box.addWidget(widget)
    if hint:
        box.addWidget(_label(hint, "dim", wrap=True))
    return box


def message_box(parent, title: str, text: str, warning: bool = False) -> None:
    box = QMessageBox(QMessageBox.Warning if warning else QMessageBox.Information, "Orbit", title, QMessageBox.Ok,
                      parent)
    box.setInformativeText(text)
    _repolish(box.button(QMessageBox.Ok), role="primary")
    style_titlebar(box)
    box.exec()


def _documents() -> str:
    return QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or str(Path.home())


def export_vocabulary(parent, vocabulary: str, replacements: list[list[str]]) -> str | None:
    """Asks where to save the vocabulary and the replacements and saves them there (for another PC). The file's path,
    or None when cancelled or when it failed (the user has been told)."""
    path, _ = QFileDialog.getSaveFileName(parent, "Exportovat slovník", str(Path(_documents()) / vocab.DEFAULT_NAME),
                                          "Slovník Orbitu (*.json)")
    if not path:
        return None
    try:
        vocab.export(path, vocabulary, replacements)
    except OSError as e:
        message_box(parent, "Slovník se nepodařilo uložit.", str(e.strerror or e), warning=True)
        return None
    return path


def import_vocabulary(parent, vocabulary: str, replacements: list[list[str]]) -> tuple[vocab.Merged, str] | None:
    """Asks for a file (an exported vocabulary or a plain list of words) and whether to merge it with the current
    vocabulary or replace it. The result and what to tell the user, or None (cancelled, or a bad file: told)."""
    path, _ = QFileDialog.getOpenFileName(parent, "Importovat slovník", _documents(),
                                          "Slovník Orbitu nebo seznam slov (*.json *.txt);;Všechny soubory (*)")
    if not path:
        return None
    try:
        words, fixes = vocab.read(path)
    except vocab.VocabError as e:
        message_box(parent, "Tenhle soubor nejde načíst.", str(e), warning=True)
        return None
    replace = False
    if vocab.parse_words(vocabulary) or replacements:
        found = " a ".join(part for part in (vocab.plural(len(words), "slovo", "slova", "slov") if words else "",
                                             vocab.plural(len(fixes), "opravu", "opravy", "oprav") if fixes else "")
                           if part)
        box = QMessageBox(QMessageBox.Question, "Orbit", f"Soubor obsahuje {found}.", QMessageBox.NoButton, parent)
        box.setInformativeText("Sloučit je přidá k tvému slovníku. Nahradit tvůj slovník a opravy smaže "
                               "a dá místo nich ty ze souboru.")
        merge = box.addButton("Sloučit", QMessageBox.AcceptRole)
        overwrite = box.addButton("Nahradit", QMessageBox.DestructiveRole)
        cancel = box.addButton("Zrušit", QMessageBox.RejectRole)
        _repolish(merge, role="primary")
        _repolish(overwrite, role="ghost")
        _repolish(cancel, role="ghost")
        box.setDefaultButton(merge)
        box.setEscapeButton(cancel)
        style_titlebar(box)
        box.exec()
        if box.clickedButton() not in (merge, overwrite):
            return None
        replace = box.clickedButton() is overwrite
    merged = vocab.merge(vocabulary, replacements, words, fixes, replace=replace)
    return merged, vocab.describe(merged, replaced=replace)


class _OptionRow(QWidget):
    """Title (and an optional explanation) on the left, a switch on the right; clicking the row flips it."""

    def __init__(self, title: str, sub: str | None, checked: bool):
        super().__init__()
        self.toggle = Toggle(checked)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 5, 0, 5)
        row.setSpacing(16)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(_label(title))
        if sub:
            texts.addWidget(_label(sub, "dim", wrap=True))
        row.addLayout(texts, 1)
        row.addWidget(self.toggle, 0, Qt.AlignVCenter)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.toggle.toggle()

    def isChecked(self) -> bool:
        return self.toggle.isChecked()

    def setChecked(self, on: bool) -> None:
        self.toggle.setChecked(on)


def scrolling(widget: QWidget) -> QScrollArea:
    """widget in a frameless, see-through scroll area (vertical only): a window taller than a laptop screen scrolls
    instead of pushing its buttons off the screen."""
    widget.setObjectName("scrollBody")
    area = QScrollArea()
    area.setObjectName("scroll")
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.viewport().setAutoFillBackground(False)
    return area


def fit_to_screen(window: QWidget, scroll: QScrollArea) -> None:
    """As big as its content wants (the scroll area's own size hint is capped), but no bigger than the screen."""
    screen = (window.screen() or QGuiApplication.primaryScreen()).availableGeometry()
    hint, area, body = window.sizeHint(), scroll.sizeHint(), scroll.widget().sizeHint()
    width = min(max(window.minimumWidth(), hint.width() - area.width() + body.width() + 14), screen.width() - 40)
    height = min(hint.height() - area.height() + body.height() + 4, screen.height() - 40)
    window.resize(width, height)
    frame = window.frameGeometry()
    frame.moveCenter(screen.center())
    window.move(frame.left(), max(screen.top() + 8, frame.top()))


class KeyAndMic(QWidget):
    """The key you hold to talk (click it to capture a new one) and what the microphone hears right now, with the
    choice of microphone. In the settings and in the first-run wizard; whoever shows it keeps the mic open only while
    it's on screen (Recorder.set_monitor). stacked: one column (the narrower wizard)."""

    capture_requested = Signal()
    mic_changed = Signal(object)

    def __init__(self, binding: dict, mic: str | None, mics: list[str], level_source, handsfree_mics: set,
                 title: str | None = None, stacked: bool = False):
        super().__init__()
        self._binding = dict(binding)
        hero = QVBoxLayout(self) if stacked else QHBoxLayout(self)
        hero.setContentsMargins(0, 0, 0, 0)
        hero.setSpacing(18 if stacked else 32)
        left = QVBoxLayout()
        left.setSpacing(8)
        if title:
            left.addWidget(_label(title, "hero"))
        self.keycap = QPushButton()
        self.keycap.setObjectName("keycap")
        self.keycap.setIconSize(QSize(22, 22))
        self.keycap.setCursor(Qt.PointingHandCursor)
        self.keycap.clicked.connect(self._start_capture)
        left.addWidget(self.keycap)
        self.key_hint = _label("", "dim", wrap=True)
        left.addWidget(self.key_hint)
        if not stacked:
            left.addStretch(1)
        hero.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(8)
        wave = LevelWave(level_source)
        if stacked:
            wave.setFixedHeight(48)
        right.addWidget(wave)
        right.addWidget(_label("Řekni něco a sleduj, jestli tě mikrofon slyší.", "dim"))
        self.mic = _combo()
        self.mic.addItem("Výchozí mikrofon Windows", None)
        for name in mics:
            self.mic.addItem(name, name)
        if mic and mic not in mics:
            self.mic.addItem(f"{mic} (odpojeno)", mic)
        self.mic.setCurrentIndex(max(0, self.mic.findData(mic)))
        self.mic.currentIndexChanged.connect(lambda _: self.mic_changed.emit(self.mic.currentData()))
        right.addWidget(self.mic)
        bt_warning = _label("Mikrofon Bluetooth sluchátek: během diktování přepnou sluchátka do režimu hovoru "
                            "(hudba zhorší kvalitu) a nahrávají jen v telefonní kvalitě, takže přepis bude "
                            "méně přesný. Lepší je jiný mikrofon.", "warn", wrap=True)
        right.addWidget(bt_warning)
        show_warning = lambda: bt_warning.setVisible(self.mic.currentData() in handsfree_mics)
        self.mic.currentIndexChanged.connect(lambda _: show_warning())
        show_warning()
        right.addWidget(_label("Mikrofon je zapnutý jen při držení klávesy a v tomhle okně. "
                               "Mluv, až pípne nebo tlačítko zčervená.", "dim", wrap=True))
        if not stacked:
            right.addStretch(1)
        hero.addLayout(right, 6)
        self._show_binding()

    @property
    def binding(self) -> dict:
        return dict(self._binding)

    def mic_choice(self) -> str | None:
        return self.mic.currentData()

    def _start_capture(self):
        self.keycap.setText("Stiskni klávesu nebo tlačítko myši…")
        self.keycap.setIcon(glyph_icon(GLYPH_KEYBOARD, LISTEN, 22))
        self.keycap.setEnabled(False)
        _repolish(self.keycap, capturing=True)
        self.key_hint.setText("Esc zruší změnu.")
        _repolish(self.key_hint, role="dim")
        self.capture_requested.emit()

    def on_captured(self, binding, refused: str = ""):
        """binding: the new one (None = Esc); refused: why it can't be used (it's kept as it was)."""
        if binding and not refused:
            self._binding = binding
        self.keycap.setEnabled(True)
        _repolish(self.keycap, capturing=False)
        self._show_binding()
        if refused:
            self.key_hint.setText(refused)
            _repolish(self.key_hint, role="warn")

    def _show_binding(self):
        mouse = self._binding["kind"] == "mouse"
        self.keycap.setText(hotkey.binding_name(self._binding))
        self.keycap.setIcon(glyph_icon(GLYPH_MOUSE if mouse else GLYPH_KEYBOARD, TEXT, 22))
        if not mouse and self._binding["code"] in _NON_DEDICATED_VK:
            self.key_hint.setText("Tuhle klávesu pak nepůjde normálně používat. Lepší je Pravý Ctrl, F9–F12, "
                                  "Pause nebo boční tlačítko myši.")
            _repolish(self.key_hint, role="warn")
        else:
            self.key_hint.setText("Klikni a stiskni novou klávesu nebo tlačítko myši.")
            _repolish(self.key_hint, role="dim")


CLAUDE_PRIVACY = "Přihlásíš se na stránce Anthropicu v prohlížeči. Orbit tvoje heslo nikdy neuvidí."


class ClaudeBox(QWidget):
    """Is Claude Code here and logged in, and Anthropic's own install and login (onboarding.ClaudeConnection does the
    work; conn None = unknown)."""

    def __init__(self, conn):
        super().__init__()
        self._conn = conn
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        self._dot = QLabel("●")
        self._title = _label("")
        head.addWidget(self._dot, 0, Qt.AlignVCenter)
        head.addWidget(self._title, 1)
        box.addLayout(head)
        self._sub = _label("", "dim", wrap=True)
        box.addWidget(self._sub)
        self._message = _label("", "warn", wrap=True)
        box.addWidget(self._message)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._install = QPushButton("Nainstalovat Claude Code")
        self._login = QPushButton("Přihlásit se")
        self._recheck = QPushButton("Zkontrolovat znovu")
        for button, role in ((self._install, "primary"), (self._login, "primary"), (self._recheck, "small")):
            button.setProperty("role", role)
            button.setCursor(Qt.PointingHandCursor)
            button.setAutoDefault(False)
            buttons.addWidget(button)
        buttons.addStretch(1)
        box.addLayout(buttons)
        self._privacy = _label(CLAUDE_PRIVACY, "dim", wrap=True)
        box.addWidget(self._privacy)
        if conn is not None:
            self._install.clicked.connect(conn.install)
            self._login.clicked.connect(conn.login)
            self._recheck.clicked.connect(conn.refresh)
            conn.changed.connect(self._update)
            conn.busy_changed.connect(self._update)
        self._update()

    def _update(self, *_):
        s = self._conn.status if self._conn else None
        busy = self._conn.busy if self._conn else ""
        color, title, sub, button = "#8B96AD", "", "", None
        if busy == "installing":
            title = "Instaluju Claude Code…"
            sub = "Sleduj okno PowerShellu. Až instalace doběhne, přihlásíš se."
        elif busy == "login":
            title = "Čekám na přihlášení…"
            sub = ("V prohlížeči se otevřela stránka Anthropicu. Přihlas se tam svým účtem Claude, okno přihlášení "
                   "se pak samo zavře.")
        elif s is None:
            title = "Zjišťuju, jestli tu je Claude Code…"
        elif s.error:
            color, title, sub, button = "#F5A524", "Stav Claude Code nejde zjistit", s.error, self._recheck
        elif not s.installed:
            color, title, button = "#F5A524", "Claude Code tu není", self._install
            sub = "Nainstaluje se oficiálním instalátorem od Anthropicu, bez práv správce. Uvidíš ho v okně PowerShellu."
        elif not s.logged_in:
            color, title, button = "#F5A524", "Claude Code není přihlášený", self._login
            sub = (f"Verze {s.version}. " if s.version else "") + "Přihlas se svým předplatným Claude (Pro nebo Max)."
        else:
            color, title = "#3DD68C", "Claude je připojený"
            sub = s.describe() + (f" Claude Code {s.version}." if s.version else "")
        self._dot.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._title.setText(title)
        self._sub.setText(sub)
        self._sub.setVisible(bool(sub))
        message = self._conn.message if self._conn else ""
        self._message.setText(message)
        self._message.setVisible(bool(message))
        for b in (self._install, self._login):
            b.setVisible(b is button)
        self._recheck.setVisible(not busy and s is not None and not s.connected)
        self._privacy.setVisible(s is not None and not s.connected or bool(busy))


class DownloadRow(QWidget):
    """One model or voice (a downloads.ITEMS key): its size and Stáhnout, progress and Zrušit, an error and Zkusit
    znovu, or that it's here. manager: onboarding.Downloads (None: the row stays empty)."""

    changed = Signal()  # it got downloaded

    def __init__(self, manager, key: str | None = None, present: str = "Stažený ✓"):
        super().__init__()
        self._manager, self._key, self._present = manager, None, present
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self._text = _label("", "dim", wrap=True)
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        self._bar.setFixedWidth(120)
        self._button = QPushButton()
        self._button.setProperty("role", "small")
        self._button.setCursor(Qt.PointingHandCursor)
        self._button.setAutoDefault(False)
        self._button.clicked.connect(self._clicked)
        row.addWidget(self._text, 1)
        row.addWidget(self._bar, 0, Qt.AlignVCenter)
        row.addWidget(self._button, 0, Qt.AlignVCenter)
        if manager is not None:  # bound methods, not lambdas: Qt drops them when this row is deleted
            manager.progress.connect(self._progress)
            manager.finished.connect(self._finished)
        self.set_key(key)

    def _progress(self, key: str, *_):
        if key == self._key:
            self._update()

    def set_key(self, key: str | None) -> None:
        self._key = key if key in downloads.ITEMS else None
        self._update()

    def _clicked(self):
        if self._manager.running(self._key):
            self._manager.cancel(self._key)
        else:
            self._manager.start(self._key)

    def _finished(self, key: str, error: str):
        if key == self._key:
            self._update()
            if not error:
                self.changed.emit()

    def _update(self):
        if self._key is None or self._manager is None:
            self.hide()
            return
        state, done, total, error = self._manager.state(self._key)
        if state == "present" and not self._present:
            self.hide()
            return
        self.show()
        self._bar.setVisible(state == "running")
        self._button.setVisible(state != "present")
        role = "dim"
        if state == "present":
            text, role = self._present, "ok"
        elif state == "running":
            self._bar.setValue(int(1000 * done / total) if total else 0)
            text = f"{100 * done / total if total else 0:.0f} % · {downloads.size_text(done)} z " \
                   f"{downloads.size_text(total)}"
            self._button.setText("Zrušit")
        elif state == "failed":
            text, role = error, "warn"
            self._button.setText("Zkusit znovu")
        else:
            text = f"Není stažený · {downloads.size_text(downloads.ITEMS[self._key].size)}"
            self._button.setText("Stáhnout")
        self._text.setText(text)
        _repolish(self._text, role=role)


class SettingsDialog(QDialog):
    capture_requested = Signal()
    agent_capture_requested = Signal()
    binding_refused = Signal(object)  # a captured dictation key that can't be used: back to this one
    mic_changed = Signal(object)
    voice_preview = Signal(str)

    def __init__(self, cfg: dict, mics: list[str], models: list[str], autostart: bool, level_source,
                 handsfree_mics: set, claude=None, downloads_=None):
        """claude: onboarding.ClaudeConnection, downloads_: onboarding.Downloads (None = unknown / no downloads)."""
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setObjectName("settings")
        self.setWindowTitle("Orbit – nastavení")
        self.setWindowIcon(mic_icon("idle"))
        self.setMinimumWidth(820)
        self._cfg = cfg
        self._claude = claude
        self._connected_at_open = self._connected()
        self._usage_before = cfg["show_usage"]

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        # Hero: the key you hold, and what the microphone hears right now.
        self.keymic = KeyAndMic(cfg["ptt"], cfg["mic"], mics, level_source, handsfree_mics, title="Drž a mluv")
        self.keymic.capture_requested.connect(self.capture_requested)
        self.keymic.mic_changed.connect(self.mic_changed)
        root.addWidget(self.keymic)

        rule = QFrame()
        rule.setProperty("role", "rule")
        root.addWidget(rule)

        body = QWidget()
        columns = QHBoxLayout(body)
        columns.setContentsMargins(0, 0, 12, 0)  # room for the scroll bar
        columns.setSpacing(40)

        transcript = QVBoxLayout()
        transcript.setSpacing(10)
        transcript.addWidget(_label("Přepis", "section"))
        self.model = _combo()  # every known model: one that isn't here yet gets downloaded (_label_models)
        for m in dict.fromkeys([*downloads.WHISPER_MODELS, *(models or []), cfg["model"]]):
            self.model.addItem(m, m)
        self.model.setCurrentIndex(max(0, self.model.findData(cfg["model"])))
        self.model_download = DownloadRow(downloads_, cfg["model"])
        self.model.currentIndexChanged.connect(lambda _: self.model_download.set_key(self.model.currentData()))
        model_box = _field("Model", self.model)
        model_box.addWidget(self.model_download)
        transcript.addLayout(model_box)

        # Slovník, with export/import (for another PC) in its title row
        vocab_title = QHBoxLayout()
        vocab_title.setSpacing(6)
        vocab_title.addWidget(_label("Slovník"), 1)
        self.vocabulary_size = _label("", "dim")  # "41/300": Whisper keeps only so many characters
        self.vocabulary_size.setToolTip(f"Whisper si ze slovníku pamatuje jen {vocab.MAX_CHARS} znaků.")
        vocab_title.addWidget(self.vocabulary_size)
        vocab_title.addSpacing(4)
        for text, tip, slot in (
                ("Exportovat…", "Uloží slovník a opravy do souboru, třeba pro jiný počítač.", self.export_vocabulary),
                ("Importovat…", "Načte slovník a opravy ze souboru: z jiného Orbitu, nebo seznam slov "
                                "(co řádek, to slovo).", self.import_vocabulary)):
            button = QPushButton(text)
            button.setProperty("role", "small")
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            vocab_title.addWidget(button)
        self.vocabulary = QPlainTextEdit(cfg["vocabulary"])
        self.vocabulary.setPlaceholderText("např. jména kolegů, firmy, odborné výrazy")
        self.vocabulary.setFixedHeight(64)
        self.vocabulary_hint = _label("", "dim", wrap=True)
        self.vocabulary.textChanged.connect(self._show_vocabulary_size)
        vocab_box = QVBoxLayout()
        vocab_box.setSpacing(5)
        vocab_box.addLayout(vocab_title)
        vocab_box.addWidget(self.vocabulary)
        vocab_box.addWidget(self.vocabulary_hint)
        transcript.addLayout(vocab_box)
        self.replacements = QPlainTextEdit("\n".join(f"{w} → {r}" for w, r in cfg["replacements"]))
        self.replacements.setPlaceholderText("comgit → Comgate")
        self.replacements.setFixedHeight(64)
        transcript.addLayout(_field("Opravy", self.replacements, "Co řádek, to oprava: špatně → správně."))
        self.import_note = _label("", "dim", wrap=True)  # what an import did
        self.import_note.hide()
        transcript.addWidget(self.import_note)
        self._show_vocabulary_size()

        self.name = QLineEdit(cfg["name"])
        self.name.setMaxLength(config.NAME_MAX)
        self.name.setPlaceholderText("např. Jana")
        self.name.setToolTip("Agent tě zná pod tímhle jménem a podepisuje jím zprávy, které za tebe posílá relacím.")
        self.about = QLineEdit(cfg["about"])
        self.about.setMaxLength(config.ABOUT_MAX)
        self.about.setPlaceholderText("např. pracuju v e-shopu s textilem")
        self.about.setToolTip("Jedna věta o tom, čím se zabýváš. Pomůže Claudovi, když se učí slovník z diktátů.")
        you = QHBoxLayout()
        you.setSpacing(12)
        you.addLayout(_field("Jméno", self.name), 2)
        you.addLayout(_field("O mně", self.about), 5)
        transcript.addLayout(you)
        self.learn = _OptionRow("Učit se z diktátů", "Po 10 diktátech pošle jejich text (ne zvuk) Claudovi a ten "
                                "doplní slovník. Čerpá z tvých limitů.", cfg["learn_vocabulary"])
        transcript.addWidget(self.learn)
        self.live = _OptionRow("Přepisovat už během mluvení", "Dlouhý diktát je hotový skoro hned po puštění, "
                               "občas o chlup méně přesně.", cfg["live_transcribe"])
        self.commands = _OptionRow("Hlasové povely", "„Nový řádek“, „nový odstavec“. Věta „Odešli.“ na konci "
                                   "zmáčkne Enter, samotné „Stop.“ zmáčkne Esc.", cfg["voice_commands"])
        self.keep = _OptionRow("Ukládat nahrávky", "Posledních 30 do složky recordings, pro ladění přesnosti.",
                               cfg["keep_recordings"])
        self.keep.setToolTip(str(config.RECORDINGS_DIR))
        transcript.addWidget(self.live)
        transcript.addWidget(self.commands)
        transcript.addWidget(self.keep)
        transcript.addStretch(1)

        behaviour = QVBoxLayout()
        behaviour.setSpacing(10)
        behaviour.addWidget(_label("Chování", "section"))
        self.mode = _combo()
        self.mode.addItem("Přes schránku (doporučeno)", "paste")
        self.mode.addItem("Psaním znaků", "type")
        self.mode.setCurrentIndex(max(0, self.mode.findData(cfg["insert_mode"])))
        behaviour.addLayout(_field("Vkládání textu", self.mode))
        self.trailing = _OptionRow("Mezera za textem", None, cfg["trailing_space"])
        self.sounds = _OptionRow("Pípnout při nahrávání", "Na začátku a na konci.", cfg["sounds"])
        self.show_btn = _OptionRow("Plovoucí tlačítko", None, cfg["show_button"])
        self.autostart = _OptionRow("Spouštět s Windows", None, autostart)
        for row in (self.trailing, self.sounds, self.show_btn, self.autostart):
            behaviour.addWidget(row)

        # Claude: the connection, then what needs it (off and greyed out until it's connected)
        behaviour.addSpacing(6)
        behaviour.addWidget(_label("Claude", "section"))
        behaviour.addWidget(ClaudeBox(claude))
        self.show_usage = _OptionRow("Využití Clauda nad tlačítkem", "5hodinový a týdenní limit. Čte je ze "
                                     "stavového řádku, který přidá do Claude Code (tvůj vlastní zůstane vidět)."
                                     if cfg["usage_source"] == "statusline" else "5hodinový a týdenní limit.",
                                     cfg["show_usage"])
        hooks = cfg["claude_hooks"]  # the overview and the artifacts need Orbit's hooks, which need consent
        self.show_sessions = _OptionRow("Přehled relací Claude Code", "Co která dělá, jestli čeká na tebe a kolik "
                                        "má kontextu. Přidá do nastavení Claude Code hooky Orbitu.",
                                        cfg["show_sessions"] and hooks)
        self.speak = _OptionRow("Předčítat hotové odpovědi", "Když relace doběhne, přečtu nahlas začátek "
                                "odpovědi. Jen lokálně.", cfg["speak_answers"])
        self.artifacts = _OptionRow("Předčítat souhrn artefaktů", "Když relace zveřejní artefakt, Claude ho shrne "
                                    "do 7 vět a já je přečtu. Čerpá z tvých limitů.", cfg["read_artifacts"] and hooks)
        self.agent = _OptionRow("Hlasový agent pro relace", "Drž jeho tlačítko a mluv, nebo klikni. Ptej se na relace "
                                "a nech ho do nich psát, vždy se nejdřív zeptá.", cfg["agent"])
        for row in (self.show_usage, self.show_sessions, self.speak, self.artifacts, self.agent):
            behaviour.addWidget(row)
        # the agent's own button (it takes it over system-wide, so it can't be the dictation's)
        self._agent_binding = dict(cfg["agent_ptt"])
        agent_key = QHBoxLayout()
        agent_key.setSpacing(8)
        self.agent_key_label = _label("Tlačítko agenta", "dim")
        self.agent_key = QPushButton()
        self.agent_key.setProperty("role", "small")
        self.agent_key.setCursor(Qt.PointingHandCursor)
        self.agent_key.setAutoDefault(False)
        self.agent_key.setToolTip("Klikni a stiskni klávesu nebo tlačítko myši pro agenta. Esc zruší změnu.")
        self.agent_key.clicked.connect(self._capture_agent_key)
        agent_key.addWidget(self.agent_key_label)
        agent_key.addWidget(self.agent_key)
        agent_key.addStretch(1)
        behaviour.addLayout(agent_key)
        self.agent_key_hint = _label("", "warn", wrap=True)
        self.agent_key_hint.hide()
        behaviour.addWidget(self.agent_key_hint)
        self.agent.toggle.toggled.connect(lambda _: self._check_keys())
        self._show_agent_key()
        self._claude_rows = (self.learn, self.show_sessions, self.speak, self.artifacts, self.agent,
                             self.agent_key_label, self.agent_key)

        self.voice = _combo()
        self.voice.currentIndexChanged.connect(lambda _: self._show_voice_note())
        self.listen = QPushButton("Poslechnout")
        self.listen.setProperty("role", "ghost")
        self.listen.setCursor(Qt.PointingHandCursor)
        self.listen.setAutoDefault(False)
        self.listen.clicked.connect(lambda: self.voice_preview.emit(self.voice.currentData()))
        voice_row = QHBoxLayout()
        voice_row.setSpacing(8)
        voice_row.addWidget(self.voice, 1)
        voice_row.addWidget(self.listen)
        voice_box = QVBoxLayout()
        voice_box.setSpacing(5)
        voice_box.addWidget(_label("Hlas pro předčítání"))
        voice_box.addLayout(voice_row)
        self.voice_note = _label("", "warn", wrap=True)  # the chosen voice isn't on this PC
        voice_box.addWidget(self.voice_note)
        self.voice_download = DownloadRow(downloads_, present="")
        self.voice_download.changed.connect(self._fill_voices)
        voice_box.addWidget(self.voice_download)
        self._fill_voices(cfg["voice"])
        behaviour.addLayout(voice_box)
        behaviour.addStretch(1)

        self.model_download.changed.connect(self._label_models)
        self._label_models()
        columns.addLayout(transcript, 1)
        columns.addLayout(behaviour, 1)
        self._scroll = scrolling(body)
        root.addWidget(self._scroll, 1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addWidget(_label(f"Orbit {VERSION}", "dim"), 0, Qt.AlignVCenter)
        data = QPushButton("Složka s daty")
        data.setProperty("role", "small")
        data.setCursor(Qt.PointingHandCursor)
        data.setAutoDefault(False)
        data.setToolTip(f"Nastavení, log, nahrávky a stažené modely: {config.DATA_DIR}")
        data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.DATA_DIR))))
        footer.addWidget(data, 0, Qt.AlignVCenter)
        footer.addStretch(1)
        cancel = QPushButton("Zrušit")
        cancel.setProperty("role", "ghost")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Uložit")
        save.setProperty("role", "primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(save)
        root.addLayout(footer)
        if claude is not None:
            claude.changed.connect(self._claude_changed)
            claude.busy_changed.connect(self._claude_busy)
        self._claude_changed()

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self)
        fit_to_screen(self, self._scroll)

    def _claude_busy(self, busy: str):
        """Installing and logging in happen in other windows (PowerShell, the browser): stay on top no more, or this
        window would cover them."""
        if busy and self.isVisible():
            # SetWindowPos(HWND_NOTOPMOST, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
            ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(int(self.winId())), ctypes.c_void_p(-2), 0, 0, 0, 0,
                                              0x13)

    def on_captured(self, binding):
        """The dictation key was captured; the agent's button can't be it while the agent is on."""
        refused = ""
        if binding and binding == self._agent_binding and self.agent.isChecked():
            refused = "Tohle tlačítko má hlasový agent. Vyber jiné, nebo agentovi dej jiné."
            self.binding_refused.emit(self.keymic.binding)
        self.keymic.on_captured(binding, refused)
        self._check_keys()

    # -- the agent's button ---------------------------------------------------------------------

    def _capture_agent_key(self):
        self.agent_key.setText("Stiskni klávesu nebo tlačítko myši…")
        self.agent_key.setEnabled(False)
        self.agent_key_hint.hide()
        self.agent_capture_requested.emit()

    def on_agent_captured(self, binding):
        self.agent_key.setEnabled(self._connected())
        if binding and binding == self.keymic.binding:
            self._show_agent_key("Tohle je klávesa pro diktování, agent potřebuje jiné tlačítko.")
            return
        if binding:
            self._agent_binding = dict(binding)
        self._show_agent_key()

    def _show_agent_key(self, problem: str = ""):
        self.agent_key.setText(hotkey.binding_name(self._agent_binding))
        self.agent_key_hint.setText(problem)
        self.agent_key_hint.setVisible(bool(problem))

    def _keys_clash(self) -> bool:
        return self.agent.isChecked() and self._agent_binding == self.keymic.binding

    def _check_keys(self):
        self._show_agent_key("Diktování a agent mají stejné tlačítko. Změň jedno z nich, jinak agent zůstane "
                             "vypnutý." if self._keys_clash() else "")

    # -- Claude, models, voices ---------------------------------------------------------------

    def _connected(self) -> bool:
        return self._claude is not None and self._claude.connected is True

    def _claude_changed(self, *_):
        """What needs Claude works only once it's connected (connecting can happen right here)."""
        connected = self._connected()
        for row in self._claude_rows:
            row.setEnabled(connected)
            row.setToolTip("" if connected else "Potřebuje připojeného Clauda (výš v sekci Claude).")

    def _label_models(self):
        advice = downloads.advise()
        for i in range(self.model.count()):
            m = self.model.itemData(i)
            label = MODEL_LABELS.get(m, m) + (" · doporučeno" if m == advice.model else "")
            if not config.model_present(m) and m in downloads.ITEMS:
                label += " · ke stažení"  # the size is in the row below
            self.model.setItemText(i, label)

    def _fill_voices(self, choice: str | None = None):
        """Jakub (marked when Windows lacks him) and the Piper voices, downloaded or not."""
        choice = choice or self.voice.currentData()
        self.voice.blockSignals(True)
        self.voice.clear()
        for key in voice.choices():
            label = voice.VOICES[key]
            if key == voice.JAKUB and not voice.windows_czech():
                label = "Jakub (ve Windows chybí)"
            elif key != voice.JAKUB and not voice.downloaded(key) and key in downloads.ITEMS:
                label += f" · stáhnout {downloads.size_text(downloads.ITEMS[key].size)}"
            self.voice.addItem(label, key)
            if key in voice.CREDITS:  # the voice's licence asks for its author to be named
                self.voice.setItemData(self.voice.count() - 1, voice.CREDITS[key], Qt.ToolTipRole)
        self.voice.setCurrentIndex(max(0, self.voice.findData(choice)))
        self.voice.blockSignals(False)
        self._show_voice_note()

    # -- vocabulary: size, export, import ----------------------------------------------------

    def _vocabulary_now(self) -> tuple[str, list[list[str]]]:
        """What the fields hold now (maybe not saved yet)."""
        return (self.vocabulary.toPlainText().strip(),
                vocab.clean_replacements(vocab.parse_replacement_lines(self.replacements.toPlainText())))

    def _show_vocabulary_size(self):
        size = len(vocab.join_words(vocab.parse_words(self.vocabulary.toPlainText())))
        over = size > vocab.MAX_CHARS
        self.vocabulary_size.setText(f"{size}/{vocab.MAX_CHARS}")
        _repolish(self.vocabulary_size, role="warn" if over else "dim")
        self.vocabulary_hint.setText(f"Slovník je moc dlouhý, Whisper si pamatuje jen {vocab.MAX_CHARS} znaků. "
                                     "Slova na začátku pak nebude znát, nějaká uber." if over else
                                     "Jména a značky, které má psát přesně takhle. Odděl je čárkou.")
        _repolish(self.vocabulary_hint, role="warn" if over else "dim")

    def _note_import(self, text: str, warn: bool = False):
        self.import_note.setText(text)
        _repolish(self.import_note, role="warn" if warn else "dim")
        self.import_note.show()

    def export_vocabulary(self):
        path = export_vocabulary(self, *self._vocabulary_now())
        if path:
            self._note_import(f"Slovník je uložený v {path}.")

    def import_vocabulary(self):
        """Fills the fields; the import takes effect when the settings are saved."""
        result = import_vocabulary(self, *self._vocabulary_now())
        if result is None:
            return
        merged, message = result
        self.vocabulary.setPlainText(merged.vocabulary)
        self.replacements.setPlainText("\n".join(f"{w} → {r}" for w, r in merged.replacements))
        self._note_import(f"{message} Projeví se po uložení.", warn=bool(merged.left_out))

    def _show_voice_note(self):
        """The chosen voice can't read on this PC (Jakub on a Windows without Czech, a Piper voice not downloaded)."""
        key = self.voice.currentData()
        piper = key not in (None, voice.JAKUB)
        self.voice_download.set_key(key if piper else None)
        self.listen.setEnabled(key is not None and voice.effective(key) == key)
        if key is None or voice.effective(key) == key:
            self.voice_note.hide()
            return
        if piper:
            text = "Hlas se stáhne, až nastavení uložíš (nebo hned tady)."
        elif voice.piper_installed():
            text = "Ve Windows chybí český hlas. Vyber si Jirku nebo Kasandru, stáhnou se."
        else:
            text = voice.missing_text()
        self.voice_note.setText(text)
        self.voice_note.show()

    def values(self) -> dict:
        """What to save. Without Claude connected, what needs it stays as it was (its rows are greyed out)."""
        vocabulary, replacements = self._vocabulary_now()
        values = {
            "ptt": self.keymic.binding,
            "mic": self.keymic.mic_choice(),
            "model": self.model.currentData() or self._cfg["model"],
            "insert_mode": self.mode.currentData(),
            "name": config.clean_name(self.name.text()),
            "about": config.clean_about(self.about.text()),
            "vocabulary": vocabulary,
            "replacements": replacements,
            "live_transcribe": self.live.isChecked(),
            "voice_commands": self.commands.isChecked(),
            "keep_recordings": self.keep.isChecked(),
            "trailing_space": self.trailing.isChecked(),
            "sounds": self.sounds.isChecked(),
            "show_button": self.show_btn.isChecked(),
            "show_usage": self.show_usage.isChecked(),
            "voice": self.voice.currentData() or self._cfg["voice"],
            "autostart": self.autostart.isChecked(),
        }
        if self._connected():
            sessions_on, artifacts_on = self.show_sessions.isChecked(), self.artifacts.isChecked()
            values.update(learn_vocabulary=self.learn.isChecked(), show_sessions=sessions_on,
                          speak_answers=self.speak.isChecked(), read_artifacts=artifacts_on,
                          agent=self.agent.isChecked() and not self._keys_clash(), agent_ptt=self._agent_binding,
                          claude_hooks=sessions_on or artifacts_on)
        # the status line for the limits: a yes when switched on here (or Claude got connected here with it on); the
        # OAuth source (an older config.json) doesn't need it
        usage = self.show_usage.isChecked()
        if self._cfg["usage_source"] != "statusline":
            pass
        elif usage != self._usage_before:
            values["claude_statusline"] = usage
        elif usage and self._connected() and not self._connected_at_open:
            values["claude_statusline"] = True
        return values
