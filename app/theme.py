"""Visual theme: "night signal" – deep ink blue, signal blue accent, red only for listening states."""
import collections
import ctypes

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from .config import ASSETS_DIR

BG = "#121826"  # window
SURFACE = "#1A2233"  # fields, keycap
LINE = "#2A3550"  # borders
TEXT = "#E7ECF5"
DIM = "#8B96AD"
ACCENT = "#5B9DFF"  # signal blue – same as the usage bars
ON_ACCENT = "#0B1424"
LISTEN = "#E5484D"  # red – same as the recording mic

DISPLAY_FONT = "Bahnschrift"
TEXT_FONT = "Segoe UI Variable Text"
ICON_FONT = "Segoe Fluent Icons"

GLYPH_KEYBOARD = chr(0xE765)
GLYPH_MOUSE = chr(0xE962)
GLYPH_CHEVRON = chr(0xE70D)


def glyph_pixmap(glyph: str, color: str, size: int) -> QPixmap:
    ratio = QApplication.primaryScreen().devicePixelRatio() if QApplication.primaryScreen() else 1.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    font = QFont(ICON_FONT)
    font.setPixelSize(int(size * 0.8))
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, glyph)
    p.end()
    return pm


def glyph_icon(glyph: str, color: str, size: int = 20) -> QIcon:
    return QIcon(glyph_pixmap(glyph, color, size))


def _chevron_path() -> str:
    path = ASSETS_DIR / "chevron.png"
    if not path.exists():
        ASSETS_DIR.mkdir(exist_ok=True)
        glyph_pixmap(GLYPH_CHEVRON, DIM, 12).save(str(path))
    return path.as_posix()


def stylesheet() -> str:
    return f"""
    QDialog#settings {{ background: {BG}; }}
    QDialog#settings QLabel {{ color: {TEXT}; font-family: "{TEXT_FONT}"; font-size: 13px; }}
    QDialog#settings QLabel[role="section"] {{ font-family: "{DISPLAY_FONT}"; font-size: 17px; font-weight: 600;
        color: {TEXT}; padding-bottom: 2px; }}
    QDialog#settings QLabel[role="hero"] {{ font-family: "{DISPLAY_FONT}"; font-size: 22px; font-weight: 600; }}
    QDialog#settings QLabel[role="dim"] {{ color: {DIM}; font-size: 12px; }}
    QDialog#settings QLabel[role="warn"] {{ color: #F5A524; font-size: 12px; }}
    QDialog#settings QFrame[role="rule"] {{ background: #202A3F; max-height: 1px; min-height: 1px; border: none; }}

    QPushButton#keycap {{ font-family: "{DISPLAY_FONT}"; font-size: 19px; font-weight: 600; color: {TEXT};
        background: {SURFACE}; border: 1px solid #33405E; border-bottom: 4px solid #33405E; border-radius: 10px;
        padding: 12px 18px; text-align: left; }}
    QPushButton#keycap:hover {{ border-color: {ACCENT}; }}
    QPushButton#keycap:focus {{ border-color: {ACCENT}; }}
    QPushButton#keycap[capturing="true"] {{ border-color: {LISTEN}; color: #FFC2C4; }}

    QComboBox, QPlainTextEdit {{ font-family: "{TEXT_FONT}"; font-size: 13px; color: {TEXT}; background: {SURFACE};
        border: 1px solid {LINE}; border-radius: 8px; padding: 6px 10px;
        selection-background-color: #2B4A80; selection-color: {TEXT}; }}
    QComboBox:hover, QPlainTextEdit:hover {{ border-color: #3A4A6E; }}
    QComboBox:focus, QPlainTextEdit:focus, QComboBox:on {{ border-color: {ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url({_chevron_path()}); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE};
        selection-background-color: #24365A; outline: none; padding: 4px; }}

    QPushButton[role="primary"], QPushButton[role="ghost"] {{ font-family: "{TEXT_FONT}"; font-size: 13px;
        font-weight: 600; border-radius: 8px; padding: 8px 20px; min-width: 84px; }}
    QPushButton[role="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; border: 1px solid {ACCENT}; }}
    QPushButton[role="primary"]:hover {{ background: #78AFFF; border-color: #78AFFF; }}
    QPushButton[role="primary"]:focus {{ border: 2px solid {TEXT}; }}
    QPushButton[role="ghost"] {{ background: transparent; color: {TEXT}; border: 1px solid {LINE}; }}
    QPushButton[role="ghost"]:hover {{ border-color: #3A4A6E; background: #182033; }}
    QPushButton[role="ghost"]:focus {{ border-color: {ACCENT}; }}

    QMenu {{ background: #161D2C; color: {TEXT}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px;
        font-family: "{TEXT_FONT}"; font-size: 13px; }}
    QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: #24365A; }}
    QMenu::item:disabled {{ color: {DIM}; }}
    QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 6px; }}
    QMenu::indicator {{ width: 14px; height: 14px; }}

    QToolTip {{ background: #161D2C; color: {TEXT}; border: 1px solid {LINE}; padding: 6px 8px;
        font-family: "{TEXT_FONT}"; font-size: 12px; }}
    QMessageBox {{ background: {BG}; }}
    QMessageBox QLabel {{ color: {TEXT}; }}
    """


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())


def style_titlebar(widget: QWidget) -> None:
    """Windows 11: dark title bar in the window colour, so the dialog reads as one surface."""
    def colorref(hex_color: str) -> ctypes.c_uint:
        c = QColor(hex_color)
        return ctypes.c_uint(c.red() | c.green() << 8 | c.blue() << 16)

    try:
        hwnd = ctypes.c_void_p(int(widget.winId()))
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)  # DWMWA_USE_IMMERSIVE_DARK_MODE
        for attr, color in ((35, BG), (36, TEXT), (34, "#243049")):  # caption, text, border colour
            value = colorref(color)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), 4)
    except Exception:
        pass


class Toggle(QAbstractButton):
    """On/off switch with a short slide; the knob lights up in the signal colour when on."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=140, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(42, 24)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _set_pos(self, value) -> None:
        self._pos = float(value)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, 1, self.width() - 2, self.height() - 2)
        off, on = QColor("#2A3550"), QColor(ACCENT)
        t = self._pos
        color = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        p.setPen(QPen(QColor(TEXT), 2) if self.hasFocus() else Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        d = track.height() - 8
        x = track.left() + 4 + t * (track.width() - 8 - d)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ON_ACCENT) if t > 0.5 else QColor(DIM))
        p.drawEllipse(QRectF(x, track.top() + 4, d, d))


class LevelWave(QWidget):
    """Live microphone meter: a scrolling row of mirrored bars, newest on the right, red when clipping."""

    BAR, GAP = 3, 3

    def __init__(self, level_source, parent=None):
        super().__init__(parent)
        self._level_source = level_source
        self._samples = collections.deque(maxlen=200)
        self._smooth = 0.0
        self.setMinimumHeight(56)
        self._timer = QTimer(self, interval=40)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        level = max(0.0, min(1.0, self._level_source()))
        self._smooth = level if level > self._smooth else self._smooth * 0.6 + level * 0.4
        self._samples.append(self._smooth)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h, mid = self.height(), self.height() / 2
        step = self.BAR + self.GAP
        count = max(1, self.width() // step)
        samples = list(self._samples)[-count:]
        samples = [0.0] * (count - len(samples)) + samples
        accent, listen = QColor(ACCENT), QColor(LISTEN)
        p.setPen(Qt.NoPen)
        for i, s in enumerate(samples):
            bar_h = max(2.0, s * (h - 4))
            color = QColor(listen if s > 0.92 else accent)
            color.setAlphaF(0.25 + 0.75 * (i + 1) / count)  # older samples fade out to the left
            p.setBrush(color)
            p.drawRoundedRect(QRectF(i * step, mid - bar_h / 2, self.BAR, bar_h), 1.5, 1.5)
