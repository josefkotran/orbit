import ctypes
import math
from datetime import datetime, timezone

from PySide6.QtCore import QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QIcon, QPainter, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QToolTip, QVBoxLayout, QWidget)

from . import hotkey
from .claude_usage import Usage, countdown, reset_text
from .config import MODEL_LABELS
from .sessions import STATE_LABELS, Session
from .theme import GLYPH_KEYBOARD, GLYPH_MOUSE, LISTEN, TEXT, LevelWave, Toggle, glyph_icon, style_titlebar

MIC_GLYPH = ""  # "Microphone" in Segoe Fluent Icons / Segoe MDL2 Assets
REFRESH_GLYPH = chr(0xE72C)  # "Refresh" in Segoe Fluent Icons / Segoe MDL2 Assets

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


def _icon_font() -> str:
    families = set(QFontDatabase.families())
    return next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), "Segoe UI Symbol")


def paint_mic(p: QPainter, rect: QRectF, state: str) -> None:
    bg, fg = COLORS[state]
    p.setPen(QPen(QColor(0, 0, 0, 60), max(1.0, rect.width() / 40)))
    p.setBrush(QColor(bg))
    p.drawEllipse(rect)
    font = QFont(_icon_font())
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
    return QColor("#E5484D" if percent >= 90 else "#F5A524" if percent >= 70 else "#5B9DFF")


class FloatingButton(QWidget):
    """Always-on-top round mic button that never takes keyboard focus from the window you type into.

    Optionally shows a small Claude usage panel above (or below, near the top of the screen) the button.
    """

    pressed = Signal()
    released = Signal()
    cancelled = Signal()
    moved = Signal(QPoint)  # new top-left of the button area, in screen coordinates
    menu_requested = Signal(QPoint)
    session_clicked = Signal(str)

    DIAMETER = 52
    MARGIN = 10
    PANEL_W = 224
    PAD = 8
    HEADER_H = 16
    ROW_H = 18
    SEP_H = 9  # gap with a hairline between the limits and the sessions
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
        self._dragging = False
        self._hovered = False

        self._show_usage = False
        self._usage: Usage | None = None
        self._usage_error: str | None = None
        self._forecast: datetime | None = None
        self._sessions: list[Session] = []
        self._session_rows: list[tuple[QRectF, Session]] = []
        self._attention = False  # a session waits for Pepa – don't fade out
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
        return self.DIAMETER + 2 * self.MARGIN

    @property
    def _has_panel(self) -> bool:
        return self._show_usage or bool(self._sessions)

    def _panel_height(self) -> int:
        h = self.PAD + self.HEADER_H + self.PAD - 2
        if self._show_usage:
            h += (len(self._usage.limits) if self._usage and self._usage.limits else 1) * self.ROW_H
        if self._sessions:
            h += (self.SEP_H if self._show_usage else 0) + len(self._sessions) * self.ROW_H
        return h

    def _relayout(self, keep_button_in_place: bool = True) -> None:
        anchor = self.button_pos()
        side = self._side
        if not self._has_panel:
            self._panel = QRectF()
            self._btn_off = QPoint(0, 0)
            self.setFixedSize(side, side)
        else:
            ph = self._panel_height()
            if self._align == "center":
                w = max(self.PANEL_W, side)
                bx, px = (w - side) // 2, (w - self.PANEL_W) // 2
            else:
                w = self.PANEL_W + self.MARGIN
                bx, px = (w - side, 0) if self._align == "right" else (0, self.MARGIN)
            by, py = (0, side) if self._below else (ph, 0)
            self._btn_off = QPoint(bx, by)
            self._panel = QRectF(px, py, self.PANEL_W, ph)
            self.setFixedSize(w, ph + side)
        if keep_button_in_place:
            self.move(anchor - self._btn_off)
        self.update()

    def button_pos(self) -> QPoint:
        return self.pos() + self._btn_off

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
        below = self.button_pos().y() - self._panel_height() < geo.top()
        if (align, below) != (self._align, self._below):
            self._align, self._below = align, below
            self._relayout()

    def _button_center(self) -> QPointF:
        return QPointF(self._btn_off.x() + self._side / 2, self._btn_off.y() + self._side / 2)

    # -- state ------------------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        # WS_EX_NOACTIVATE: clicking the button must not steal focus from the target window.
        user32 = ctypes.windll.user32
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        hwnd = ctypes.c_void_p(int(self.winId()))
        ex = user32.GetWindowLongPtrW(hwnd, -20)
        user32.SetWindowLongPtrW(hwnd, -20, ex | 0x08000000 | 0x00000080 | 0x00000008)

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.update()
            self._wake()
        animate = state in ("recording", "busy", "loading")
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

    def _stale(self) -> bool:
        if self._usage is None:
            return True
        age = (datetime.now(timezone.utc) - self._usage.fetched_at).total_seconds()
        return age > self.STALE_AFTER_S

    def _tick(self):
        self._phase = (self._phase + 0.12) % (2 * math.pi)
        target = self._level_source() if self._state == "recording" else 0.0
        self._level += (target - self._level) * 0.45
        self.update()

    # -- fading out when nothing happens ----------------------------------------------------

    def wake(self) -> None:
        """Something happened worth a look – full opacity for a moment."""
        self._wake()

    def _wake(self) -> None:
        """Fully visible now; when idle, fade out again after IDLE_FADE_MS."""
        self._animate_opacity(1.0, 150)
        if self._state == "idle" and not self._hovered and not self._attention:
            self._fade_timer.start()
        else:
            self._fade_timer.stop()

    def _fade_out(self) -> None:
        if QApplication.activePopupWidget():  # our context menu is open
            self._fade_timer.start()
        elif self._state == "idle" and not self._hovered and not self._attention and self._press_global is None:
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

    def _paint_panel(self, p: QPainter) -> None:
        rect = self._panel
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.setBrush(QColor(24, 27, 34, 235))
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
        if self._show_usage:
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
            self._paint_sessions(p, x, right, y, font, bold, text, dim)

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
            icon_font = QFont(_icon_font())
            icon_font.setPixelSize(12)
            p.setFont(icon_font)
            p.setPen(text)
            text_w = QFontMetricsF(font).horizontalAdvance(note)
            p.drawText(QRectF(header.right() - text_w - 18, header.top(), 14, header.height()),
                       Qt.AlignCenter, REFRESH_GLYPH)

    def _paint_limits(self, p: QPainter, x: float, right: float, y: float, font: QFont, bold: QFont, text: QColor,
                      dim: QColor) -> float:
        if not self._usage or not self._usage.limits:
            p.setPen(dim)
            p.setFont(font)
            msg = "Načítám…" if not self._usage_error else "Nedostupné – najeď myší"
            p.drawText(QRectF(x, y, right - x, self.ROW_H), Qt.AlignLeft | Qt.AlignVCenter, msg)
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
                        text: QColor, dim: QColor) -> None:
        """One row per Claude Code session: status dot, project, what it's doing, how full its context is."""
        pct_w, state_w = 34, 78
        for s in self._sessions:
            row = QRectF(x, y, right - x, self.ROW_H)
            self._session_rows.append((row.adjusted(-6, 0, 6, 0), s))
            p.setPen(Qt.NoPen)
            p.setBrush(SESSION_COLORS[s.state])
            p.drawEllipse(QPointF(row.left() + 4, row.center().y()), 3.5, 3.5)
            p.setFont(bold)
            p.setPen(text)
            name_rect = QRectF(row.left() + 13, row.top(), row.width() - 13 - state_w - pct_w, row.height())
            p.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetricsF(bold).elidedText(s.name, Qt.ElideRight, name_rect.width()))
            p.setFont(font)
            p.setPen(SESSION_COLORS[s.state] if s.state in ("waiting", "error") else dim)
            p.drawText(QRectF(row.right() - pct_w - state_w, row.top(), state_w, row.height()),
                       Qt.AlignRight | Qt.AlignVCenter, STATE_LABELS[s.state])
            if s.context is not None:
                p.setPen(QColor("#F5A524") if s.context >= 0.8 else dim)
                p.drawText(QRectF(row.right() - pct_w, row.top(), pct_w, row.height()),
                           Qt.AlignRight | Qt.AlignVCenter, f"{s.context * 100:.0f} %")
            y += self.ROW_H

    def _session_at(self, pos: QPointF) -> Session | None:
        return next((s for rect, s in self._session_rows if rect.contains(pos)), None)

    def _usage_tooltip(self) -> str:
        lines = []
        if self._usage:
            local = self._usage.fetched_at.astimezone()
            lines.append(f"Využití Clauda (aktualizováno v {local.hour}:{local.minute:02d})")
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
            session = self._session_at(pos)
            on_panel = self._has_panel and self._panel.contains(pos)
            tip = session.tooltip() if session else self._usage_tooltip() if on_panel else self._button_tip
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
            self._press_on_button = math.hypot(d.x(), d.y()) <= self._side / 2
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
        elif session := self._session_at(event.position()):
            self.session_clicked.emit(session.id)


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


def _field(title: str, widget: QWidget, hint: str | None = None) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(5)
    box.addWidget(_label(title))
    box.addWidget(widget)
    if hint:
        box.addWidget(_label(hint, "dim", wrap=True))
    return box


def _parse_replacements(text: str) -> list[list[str]]:
    pairs = []
    for line in text.splitlines():
        wrong, sep, right = line.replace("->", "→").partition("→")
        if sep and wrong.strip() and right.strip():
            pairs.append([wrong.strip(), right.strip()])
    return pairs


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
        if event.button() == Qt.LeftButton:
            self.toggle.toggle()

    def isChecked(self) -> bool:
        return self.toggle.isChecked()


class SettingsDialog(QDialog):
    capture_requested = Signal()
    mic_changed = Signal(object)

    def __init__(self, cfg: dict, mics: list[str], models: list[str], autostart: bool, first_run: bool,
                 level_source):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setObjectName("settings")
        self.setWindowTitle("Orbit – nastavení")
        self.setWindowIcon(mic_icon("idle"))
        self.setMinimumWidth(820)
        self._binding = dict(cfg["ptt"])

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        # Hero: the key you hold, and what the microphone hears right now.
        hero = QHBoxLayout()
        hero.setSpacing(32)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(_label("Drž a mluv", "hero"))
        if first_run:
            left.addWidget(_label("Vítej! Vyber si klávesu, kterou budeš držet při mluvení. "
                                  "Až ji pustíš, text se vloží tam, kde máš kurzor.", "dim", wrap=True))
        self.keycap = QPushButton()
        self.keycap.setObjectName("keycap")
        self.keycap.setIconSize(QSize(22, 22))
        self.keycap.setCursor(Qt.PointingHandCursor)
        self.keycap.clicked.connect(self._start_capture)
        left.addWidget(self.keycap)
        self.key_hint = _label("", "dim", wrap=True)
        left.addWidget(self.key_hint)
        left.addStretch(1)
        hero.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(LevelWave(level_source))
        right.addWidget(_label("Řekni něco a sleduj, jestli tě mikrofon slyší.", "dim"))
        self.mic = QComboBox()
        self.mic.addItem("Výchozí mikrofon Windows", None)
        for name in mics:
            self.mic.addItem(name, name)
        if cfg["mic"] and cfg["mic"] not in mics:
            self.mic.addItem(f"{cfg['mic']} (odpojeno)", cfg["mic"])
        self.mic.setCurrentIndex(max(0, self.mic.findData(cfg["mic"])))
        self.mic.currentIndexChanged.connect(lambda _: self.mic_changed.emit(self.mic.currentData()))
        right.addWidget(self.mic)
        right.addWidget(_label("Mikrofon je zapnutý jen při držení klávesy a tady v nastavení. "
                               "Mluv, až pípne nebo tlačítko zčervená.", "dim", wrap=True))
        right.addStretch(1)
        hero.addLayout(right, 6)
        root.addLayout(hero)

        rule = QFrame()
        rule.setProperty("role", "rule")
        root.addWidget(rule)

        columns = QHBoxLayout()
        columns.setSpacing(40)

        transcript = QVBoxLayout()
        transcript.setSpacing(10)
        transcript.addWidget(_label("Přepis", "section"))
        self.model = QComboBox()
        for m in models:
            self.model.addItem(MODEL_LABELS.get(m, m), m)
        self.model.setCurrentIndex(max(0, self.model.findData(cfg["model"])))
        transcript.addLayout(_field("Model", self.model))
        self.vocabulary = QPlainTextEdit(cfg["vocabulary"])
        self.vocabulary.setPlaceholderText("např. Hommel Hercules, M-tex, HHW")
        self.vocabulary.setFixedHeight(64)
        transcript.addLayout(_field("Slovník", self.vocabulary,
                                    "Jména a značky, které má psát přesně takhle. Odděl je čárkou."))
        self.replacements = QPlainTextEdit("\n".join(f"{w} → {r}" for w, r in cfg["replacements"]))
        self.replacements.setPlaceholderText("comgit → Comgate")
        self.replacements.setFixedHeight(64)
        transcript.addLayout(_field("Opravy", self.replacements, "Co řádek, to oprava: špatně → správně."))
        self.learn = _OptionRow("Učit se z diktátů", "Po každých 10 diktátech pošle jejich text (ne zvuk) Claudovi "
                                "a ten doplní slovník a opravy.", cfg["learn_vocabulary"])
        transcript.addWidget(self.learn)
        self.live = _OptionRow("Přepisovat už během mluvení", "Dlouhý diktát je hotový skoro hned po puštění, "
                               "občas o chlup méně přesně.", cfg["live_transcribe"])
        self.commands = _OptionRow("Hlasové povely", "„Nový řádek“, „nový odstavec“. Věta „Odešli.“ na konci "
                                   "zmáčkne Enter, samotné „Stop.“ zmáčkne Esc.", cfg["voice_commands"])
        self.keep = _OptionRow("Ukládat nahrávky", "Posledních 30 do složky recordings, pro ladění přesnosti.",
                               cfg["keep_recordings"])
        transcript.addWidget(self.live)
        transcript.addWidget(self.commands)
        transcript.addWidget(self.keep)
        transcript.addStretch(1)

        behaviour = QVBoxLayout()
        behaviour.setSpacing(10)
        behaviour.addWidget(_label("Chování", "section"))
        self.mode = QComboBox()
        self.mode.addItem("Přes schránku (doporučeno)", "paste")
        self.mode.addItem("Psaním znaků", "type")
        self.mode.setCurrentIndex(max(0, self.mode.findData(cfg["insert_mode"])))
        behaviour.addLayout(_field("Vkládání textu", self.mode))
        self.trailing = _OptionRow("Mezera za textem", None, cfg["trailing_space"])
        self.sounds = _OptionRow("Pípnout při nahrávání", "Na začátku a na konci.", cfg["sounds"])
        self.show_btn = _OptionRow("Plovoucí tlačítko", None, cfg["show_button"])
        self.show_usage = _OptionRow("Využití Clauda nad tlačítkem", "5 h, týden a Fable.", cfg["show_usage"])
        self.show_sessions = _OptionRow("Přehled relací Claude Code", "Co která dělá, jestli čeká na tebe a kolik "
                                        "má kontextu. Klik přepne do terminálu.", cfg["show_sessions"])
        self.speak = _OptionRow("Předčítat hotové odpovědi", "Když relace doběhne, hlas Jakub přečte začátek "
                                "odpovědi. Jen lokálně.", cfg["speak_answers"])
        self.autostart = _OptionRow("Spouštět s Windows", None, autostart)
        for row in (self.trailing, self.sounds, self.show_btn, self.show_usage, self.show_sessions, self.speak,
                    self.autostart):
            behaviour.addWidget(row)
        behaviour.addStretch(1)

        columns.addLayout(transcript, 1)
        columns.addLayout(behaviour, 1)
        root.addLayout(columns)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("Zrušit")
        cancel.setProperty("role", "ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Uložit")
        save.setProperty("role", "primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(save)
        root.addLayout(footer)
        self._show_binding()

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self)

    def _start_capture(self):
        self.keycap.setText("Stiskni klávesu nebo tlačítko myši…")
        self.keycap.setIcon(glyph_icon(GLYPH_KEYBOARD, LISTEN, 22))
        self.keycap.setEnabled(False)
        _repolish(self.keycap, capturing=True)
        self.key_hint.setText("Esc zruší změnu.")
        _repolish(self.key_hint, role="dim")
        self.capture_requested.emit()

    def on_captured(self, binding):
        if binding:
            self._binding = binding
        self.keycap.setEnabled(True)
        _repolish(self.keycap, capturing=False)
        self._show_binding()

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

    def values(self) -> dict:
        return {
            "ptt": self._binding,
            "mic": self.mic.currentData(),
            "model": self.model.currentData(),
            "insert_mode": self.mode.currentData(),
            "vocabulary": self.vocabulary.toPlainText().strip(),
            "replacements": _parse_replacements(self.replacements.toPlainText()),
            "learn_vocabulary": self.learn.isChecked(),
            "live_transcribe": self.live.isChecked(),
            "voice_commands": self.commands.isChecked(),
            "keep_recordings": self.keep.isChecked(),
            "trailing_space": self.trailing.isChecked(),
            "sounds": self.sounds.isChecked(),
            "show_button": self.show_btn.isChecked(),
            "show_usage": self.show_usage.isChecked(),
            "show_sessions": self.show_sessions.isChecked(),
            "speak_answers": self.speak.isChecked(),
            "autostart": self.autostart.isChecked(),
        }
