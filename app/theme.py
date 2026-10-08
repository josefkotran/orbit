"""Visual theme: "night signal" – deep ink blue, signal blue accent, red only for listening states.
The colour can be switched to violet or teal (set_theme): the accent changes and the ink takes on its hue."""
import collections
import ctypes
import functools
import logging

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from .config import CACHE_DIR

log = logging.getLogger(__name__)

BG = "#121826"  # window
SURFACE = "#1A2233"  # fields, keycap
LINE = "#2A3550"  # borders
TEXT = "#E7ECF5"
DIM = "#8B96AD"
ACCENT = "#5B9DFF"  # signal blue – same as the usage bars
ON_ACCENT = "#0B1424"
LISTEN = "#E5484D"  # red – same as the recording mic

THEMES = {  # name: (label, accent); the dark surfaces take on the accent's hue, red/orange/green keep theirs
    "blue": ("Modrá", "#5B9DFF"),
    "violet": ("Fialová", "#A78BFA"),
    "teal": ("Tyrkysová", "#2DD4BF"),
}
current = "blue"
_hue_shift = 0  # how far the current theme's hue is from the blue design's
_BLUE = {"BG": BG, "SURFACE": SURFACE, "LINE": LINE, "ON_ACCENT": ON_ACCENT}  # set_theme turns these

DISPLAY_FONT = "Bahnschrift"
TEXT_FONT = "Segoe UI Variable Text"
ICON_FONT = "Segoe Fluent Icons"  # Windows 11; Windows 10 has the same glyphs in Segoe MDL2 Assets (see icon_font)

GLYPH_KEYBOARD = chr(0xE765)
GLYPH_MOUSE = chr(0xE962)
GLYPH_CHEVRON = chr(0xE70D)


def tint(color: str) -> QColor:
    """A colour of the blue design in the current theme: its hue turned, saturation and lightness kept."""
    c = QColor(color)
    if _hue_shift and c.hslHue() >= 0:
        c.setHsl((c.hslHue() + _hue_shift) % 360, c.hslSaturation(), c.lightness(), c.alpha())
    return c


def set_theme(name: str) -> None:
    """Switch the colour theme. apply() then restyles the widgets; painted ones read the colours as they paint."""
    global current, _hue_shift, ACCENT
    current = name if name in THEMES else "blue"
    ACCENT = THEMES[current][1]
    _hue_shift = QColor(ACCENT).hslHue() - QColor(THEMES["blue"][1]).hslHue()
    globals().update({key: tint(value).name() for key, value in _BLUE.items()})


@functools.cache
def icon_font() -> str:
    """The installed icon font (needs the QApplication). Neither Segoe UI nor Segoe UI Symbol has these glyphs."""
    families = set(QFontDatabase.families())
    return next((f for f in (ICON_FONT, "Segoe MDL2 Assets") if f in families), "Segoe UI Symbol")


def glyph_pixmap(glyph: str, color: str, size: int) -> QPixmap:
    ratio = QApplication.primaryScreen().devicePixelRatio() if QApplication.primaryScreen() else 1.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    font = QFont(icon_font())
    font.setPixelSize(int(size * 0.8))
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, glyph)
    p.end()
    return pm


def glyph_icon(glyph: str, color: str, size: int = 20) -> QIcon:
    return QIcon(glyph_pixmap(glyph, color, size))


@functools.cache
def _chevron_path() -> str:
    """The combo box arrow as an image file (QSS wants one), made once per run: a copy made without the icon font
    (Windows 10 before the fallback, an offscreen test) would otherwise stay. "" when it can't be written."""
    path = CACHE_DIR / "chevron.png"
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if glyph_pixmap(GLYPH_CHEVRON, DIM, 12).save(str(path)):
            return path.as_posix()
    except OSError:
        pass
    log.warning("Šipku pro rozbalovací seznamy nejde uložit do %s", path)
    return ""


def stylesheet() -> str:
    t = lambda color: tint(color).name()
    hover = QColor(ACCENT).lighter(112).name()
    chevron = _chevron_path()
    arrow = f"QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}" if chevron else ""
    d = lambda sel: ", ".join(f"QDialog#{name} {sel}".rstrip() for name in ("settings", "wizard", "notebook"))  # all three
    return f"""
    {d("")} {{ background: {BG}; }}
    {d("QLabel")} {{ color: {TEXT}; font-family: "{TEXT_FONT}"; font-size: 13px; }}
    {d("QLabel:disabled")} {{ color: {DIM}; }}
    {d('QLabel[role="section"]')} {{ font-family: "{DISPLAY_FONT}"; font-size: 17px; font-weight: 600;
        color: {TEXT}; padding-bottom: 2px; }}
    {d('QLabel[role="hero"]')} {{ font-family: "{DISPLAY_FONT}"; font-size: 22px; font-weight: 600; }}
    {d('QLabel[role="dim"]')} {{ color: {DIM}; font-size: 12px; }}
    {d('QLabel[role="warn"]')} {{ color: #F5A524; font-size: 12px; }}
    {d('QLabel[role="ok"]')} {{ color: #3DD68C; font-size: 12px; }}
    {d('QLabel[role="step"]')} {{ color: {DIM}; font-family: "{DISPLAY_FONT}"; font-size: 12px;
        font-weight: 600; letter-spacing: 1px; }}
    {d('QLabel[role="bullet"]')} {{ color: {TEXT}; font-size: 13px; padding-left: 2px; }}
    {d('QFrame[role="rule"]')} {{ background: {t('#202A3F')}; max-height: 1px; min-height: 1px;
        border: none; }}
    {d('QFrame[role="card"]')} {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px; }}
    {d('QFrame[role="card"]:hover')} {{ border-color: {t('#3A4A6E')}; }}
    {d('QFrame[role="card"][selected="true"]')} {{ border: 2px solid {ACCENT}; }}
    {d('QFrame[role="card"] QLabel')} {{ background: transparent; }}
    {d('QScrollArea#scroll')} {{ background: transparent; border: none; }}
    {d('QWidget#scrollBody')} {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t('#3A4A6E')}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    {d("QTreeWidget")}, {d("QListWidget")} {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE};
        border-radius: 8px; padding: 4px; font-family: "{TEXT_FONT}"; font-size: 13px; outline: none; }}
    {d("QTreeWidget::item")} {{ padding: 4px 6px; }}
    {d("QListWidget::item")} {{ padding: 4px 2px; border-radius: 5px; }}
    {d("QTreeWidget::item:hover")}, {d("QListWidget::item:hover")} {{ background: {t('#1E2A40')}; }}
    {d("QTreeWidget::item:selected")}, {d("QListWidget::item:selected")} {{ background: {t('#24365A')};
        color: {TEXT}; }}
    {d("QTreeWidget::branch")}, {d("QTreeWidget::branch:selected")}, {d("QTreeWidget::branch:hover")} {{
        background: transparent; border-image: none; image: none; }}
    {d('QPushButton[role="small"][selected="true"]')} {{ color: {TEXT}; border-color: {ACCENT};
        background: {t('#1E2D4A')}; }}
    QProgressBar {{ background: {LINE}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

    QPushButton#keycap {{ font-family: "{DISPLAY_FONT}"; font-size: 19px; font-weight: 600; color: {TEXT};
        background: {SURFACE}; border: 1px solid {t('#33405E')}; border-bottom: 4px solid {t('#33405E')};
        border-radius: 10px; padding: 12px 18px; text-align: left; }}
    QPushButton#keycap:hover {{ border-color: {ACCENT}; }}
    QPushButton#keycap:focus {{ border-color: {ACCENT}; }}
    QPushButton#keycap[capturing="true"] {{ border-color: {LISTEN}; color: #FFC2C4; }}

    QComboBox, QPlainTextEdit, QLineEdit {{ font-family: "{TEXT_FONT}"; font-size: 13px; color: {TEXT};
        background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 10px;
        selection-background-color: {t('#2B4A80')}; selection-color: {TEXT}; }}
    QComboBox:hover, QPlainTextEdit:hover, QLineEdit:hover {{ border-color: {t('#3A4A6E')}; }}
    QComboBox:focus, QPlainTextEdit:focus, QLineEdit:focus, QComboBox:on {{ border-color: {ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    {arrow}
    QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE};
        selection-background-color: {t('#24365A')}; outline: none; padding: 4px; }}

    QPushButton[role="primary"], QPushButton[role="ghost"] {{ font-family: "{TEXT_FONT}"; font-size: 13px;
        font-weight: 600; border-radius: 8px; padding: 8px 20px; min-width: 84px; }}
    QPushButton[role="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; border: 1px solid {ACCENT}; }}
    QPushButton[role="primary"]:hover {{ background: {hover}; border-color: {hover}; }}
    QPushButton[role="primary"]:focus {{ border: 2px solid {TEXT}; }}
    QPushButton[role="ghost"] {{ background: transparent; color: {TEXT}; border: 1px solid {LINE}; }}
    QPushButton[role="ghost"]:hover {{ border-color: {t('#3A4A6E')}; background: {t('#182033')}; }}
    QPushButton[role="ghost"]:focus {{ border-color: {ACCENT}; }}
    QPushButton[role="small"] {{ font-family: "{TEXT_FONT}"; font-size: 12px; color: {DIM}; background: transparent;
        border: 1px solid {LINE}; border-radius: 6px; padding: 1px 10px; }}
    QPushButton[role="small"]:hover {{ color: {TEXT}; border-color: {t('#3A4A6E')}; background: {t('#182033')}; }}
    QPushButton[role="small"]:focus {{ border-color: {ACCENT}; }}

    QMenu {{ background: {t('#161D2C')}; color: {TEXT}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px;
        font-family: "{TEXT_FONT}"; font-size: 13px; }}
    QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {t('#24365A')}; }}
    QMenu::item:disabled {{ color: {DIM}; }}
    QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 6px; }}
    QMenu::indicator {{ width: 14px; height: 14px; }}

    QToolTip {{ background: {t('#161D2C')}; color: {TEXT}; border: 1px solid {LINE}; padding: 6px 8px;
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
        for attr, color in ((35, BG), (36, TEXT), (34, tint("#243049").name())):  # caption, text, border colour
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
        if not self.isEnabled():  # e.g. needs Claude, which isn't connected
            p.setOpacity(0.35)
        track = QRectF(1, 1, self.width() - 2, self.height() - 2)
        off, on = QColor(LINE), QColor(ACCENT)
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
