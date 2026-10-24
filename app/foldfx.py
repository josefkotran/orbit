"""The fold and unfold animation (Pepa, 16 Oct: "ať to udělá nějakou mega cool animaci", folding Orbit into its icon
and unfolding it again): a window of its own over the button for under a second, transparent to the mouse. The button
changes at once (its layout, its place, what a click does) and shows nothing until the animation is over, so none of
its logic waits for it; the animation's first frame is what was on the screen and its last one what the button then
shows.

Folding, the panel breathes in and swirls into the planet like into a black hole, its stars spiral in after it, and
the icon pops out with its moon whipping round and a shock wave. Unfolding, the icon charges up with the moon
speeding round, bursts, and the panel unwinds out of it while its stars fly to their places and a wave of light runs
across it (it loads). Only with Windows' animation effects on (Settings › Accessibility › Visual effects)."""
import ctypes
import math
import random
import time
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import theme

FOLD_MS = 800  # the panel into the icon
UNFOLD_MS = 740  # the icon into the panel
PAD = 64  # room around the window's picture for the shock waves (whole device pixels at 125, 150, 175 and 200 %)
STARS = 56
PANEL_END = 0.68  # folding: the panel is gone by then
FADE_IN_MS = 150  # from the button's faded opacity to full, like its own wake
MOON_REST = math.atan2(2.7 / 4.2, 9 / 11.8)  # where the icon's moon sits on its orbit (the favicon's)


def animations_on() -> bool:
    """Windows' "Animation effects" (SPI_GETCLIENTAREAANIMATION); not known = on."""
    value = ctypes.c_int(1)
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0):
            return bool(value.value)
    except (AttributeError, OSError):
        pass
    return True


def _clamp(t: float) -> float:
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def _smooth(a: float, b: float, t: float) -> float:
    t = _clamp((t - a) / (b - a))
    return t * t * (3 - 2 * t)


def _out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def _in_back(t: float, k: float) -> float:
    """Back a little first, then in (k: how far back)."""
    return (k + 1) * t ** 3 - k * t * t


def _out_back(t: float, k: float) -> float:
    """Out past the end, then back to it (k: how far past)."""
    t -= 1
    return 1 + (k + 1) * t ** 3 + k * t * t


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * t, a.greenF() + (b.greenF() - a.greenF()) * t,
                           a.blueF() + (b.blueF() - a.blueF()) * t)


def _fold_pose(a: float) -> tuple[float, float]:
    """Folding: the panel's size and turn (degrees, clockwise) at a, its part of the animation (0–1): a breath in
    (+4 %), then faster and faster into the planet."""
    a = _clamp(a)
    return max(0.015, 1 - 0.985 * _in_back(a, 1.0)), 80 * a ** 3


def _unfold_pose(g: float) -> tuple[float, float]:
    """Unfolding: the panel's size and turn at g: out of the planet, a little past its size and back, unwinding."""
    g = _clamp(g)
    return 0.03 + 0.97 * _out_back(g, 1.25), -40 * (1 - _out_cubic(g))


@dataclass
class _Star:
    r: float  # where on the picture it belongs: its distance from the icon's centre
    th: float  # and its angle (radians, clockwise from the right)
    start: float  # when it sets off (share of the animation)
    length: float  # how long it flies
    spin: float  # how far round it goes before the spiral tightens (radians)
    size: float
    color: QColor


class FoldFx(QWidget):
    """The animation's window: the button's picture (folding what was on the screen, unfolding what it's about to
    show) with PAD around it. finished = its last frame is on the screen: the button shows itself again and closes
    this window (stop() ends it sooner)."""

    finished = Signal()

    def __init__(self, shot: QPixmap, shot_rect: QRect, center: QPointF, folding: bool, paint_icon,
                 icon_r: float, opacity: float = 1.0, seed: int | None = None):
        """shot: the button's window painted whole, shot_rect: where that window is (global), center: the icon's
        (the mic's) centre (global), paint_icon(painter, centre, scale, spin, moon): the button's icon, icon_r: its
        radius, opacity: the button's when the animation starts (it fades in from there)."""
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setGeometry(shot_rect.adjusted(-PAD, -PAD, PAD, PAD))
        self._shot, self._folding, self._paint_icon_cb = shot, folding, paint_icon
        self._at = QPoint(PAD, PAD)  # the picture's top left in this window
        self._shot_area = QRectF(self._at, shot_rect.size())
        self._c = QPointF(center) - QPointF(self.pos())
        self._icon_r = icon_r
        self._from = opacity
        self._ms = FOLD_MS if folding else UNFOLD_MS
        self._far = max(math.hypot(x - self._c.x(), y - self._c.y())  # the picture's corner furthest from the icon
                        for x in (self._shot_area.left(), self._shot_area.right())
                        for y in (self._shot_area.top(), self._shot_area.bottom()))
        self._stars = self._place_stars(random.Random(seed))
        self._u = 0.0
        self._t0 = 0.0
        self._timer = QTimer(self, interval=15, timerType=Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        """On the screen with its first frame (what's there now), before the button hides."""
        self._t0 = time.perf_counter()
        self.show()
        self.repaint()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if QGuiApplication.platformName() == "windows":  # never activated, topmost, a tool window, click-through
            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            hwnd = ctypes.c_void_p(int(self.winId()))
            ex = user32.GetWindowLongPtrW(hwnd, -20)
            user32.SetWindowLongPtrW(hwnd, -20, ex | 0x08000000 | 0x00000080 | 0x00000008 | 0x00000020)

    def _tick(self) -> None:
        self._u = min(1.0, (time.perf_counter() - self._t0) * 1000 / self._ms)
        if self._u < 1:
            self.update()
            return
        self._timer.stop()
        self.repaint()  # the last frame on the screen before the button takes over
        self.finished.emit()

    # -- the stars ---------------------------------------------------------------------------

    def _place_stars(self, rng: random.Random) -> list[_Star]:
        """Stars on the picture's opaque parts (the panel, its chips, the circles), not on the mic itself."""
        image = self._shot.toImage()
        ratio = self._shot.devicePixelRatio()
        accent, white = QColor(theme.ACCENT), QColor("#FFFFFF")
        stars = []
        for _ in range(STARS * 25):
            if len(stars) == STARS:
                break
            x, y = rng.uniform(0, self._shot_area.width()), rng.uniform(0, self._shot_area.height())
            px, py = min(image.width() - 1, int(x * ratio)), min(image.height() - 1, int(y * ratio))
            if image.pixelColor(px, py).alpha() < 120:
                continue
            dx, dy = self._at.x() + x - self._c.x(), self._at.y() + y - self._c.y()
            if math.hypot(dx, dy) < self._icon_r + 8:
                continue
            start, length = (rng.uniform(0.04, 0.46), rng.uniform(0.28, 0.42)) if self._folding else \
                (rng.uniform(0.28, 0.42), rng.uniform(0.34, 0.5))
            pick = rng.random()
            color = white if pick < 0.18 else _mix(accent, white, 0.5) if pick < 0.45 else QColor(accent)
            stars.append(_Star(math.hypot(dx, dy), math.atan2(dy, dx), start, length, rng.uniform(0.45, 0.95),
                               rng.uniform(1.6, 3.0), color))
        return stars

    def _fold_star(self, s: _Star, q: float) -> QPointF:
        """Folding, a star q of its way (0–1) in: off the panel where the panel had carried it, round and round
        into the planet, faster the closer it gets."""
        scale, turn = _fold_pose(s.start / PANEL_END)
        e = q ** 2.2
        r = s.r * scale * (1 - e)
        th = s.th + math.radians(turn) + s.spin * e / (1 - 0.7 * e)
        return QPointF(self._c.x() + r * math.cos(th), self._c.y() + r * math.sin(th))

    def _unfold_star(self, s: _Star, q: float) -> QPointF:
        """Unfolding, a star q of its way out: out of the planet fast, unwinding, slowing down onto its place."""
        e = 1 - (1 - q) ** 2.6
        th = s.th - s.spin * (1 - e) / (1 - 0.7 * (1 - e))
        return QPointF(self._c.x() + s.r * e * math.cos(th), self._c.y() + s.r * e * math.sin(th))

    @staticmethod
    def _star(p: QPainter, head: QPointF, tail: QPointF, size: float, color: QColor, alpha: float) -> None:
        """A star with its trail fading out behind it."""
        if alpha <= 0.01:
            return
        clear, bright = QColor(color), QColor(color)
        clear.setAlphaF(0)
        bright.setAlphaF(alpha * 0.7)
        trail = QLinearGradient(tail, head)
        trail.setColorAt(0, clear)
        trail.setColorAt(1, bright)
        p.setPen(QPen(QBrush(trail), size, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(tail, head)
        bright.setAlphaF(alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(bright)
        p.drawEllipse(head, size * 0.8, size * 0.8)

    def _stars_at(self, p: QPainter, u: float, base: float) -> None:
        for s in self._stars:
            q = (u - s.start) / s.length
            if not 0 < q < 1:
                continue
            if self._folding:
                alpha = min(1.0, q / 0.12) * (1 - _smooth(0.82, 1.0, q))
                head, tail = self._fold_star(s, q), self._fold_star(s, max(0.0, q - 0.08))
                size = s.size * (1 - 0.45 * q)
            else:
                alpha = min(1.0, q / 0.08) * (1 - _smooth(0.65, 1.0, q))
                head, tail = self._unfold_star(s, q), self._unfold_star(s, max(0.0, q - 0.08))
                size = s.size
            self._star(p, head, tail, size, s.color, base * alpha)

    # -- the pieces --------------------------------------------------------------------------

    def _picture(self, p: QPainter, scale: float, turn: float, opacity: float) -> None:
        """The button's picture, smaller or bigger and turned round the icon's centre."""
        if opacity <= 0.004 or scale <= 0.01:
            return
        p.save()
        p.setOpacity(opacity)
        if scale != 1 or turn:
            p.translate(self._c)
            p.rotate(turn)
            p.scale(scale, scale)
            p.translate(-self._c)
        p.drawPixmap(self._at, self._shot)
        p.restore()

    def _icon(self, p: QPainter, opacity: float, scale: float = 1.0, spin: float = 0.0,
              moon: float | None = None) -> None:
        if opacity <= 0.01 or scale <= 0.02:
            return
        p.save()
        p.setOpacity(opacity)
        self._paint_icon_cb(p, self._c, scale, spin, moon)
        p.restore()

    def _glow(self, p: QPainter, strength: float, radius: float) -> None:
        """A white-hot core in the accent's glow at the icon's centre."""
        if strength <= 0.01:
            return
        core, mid, edge = QColor("#FFFFFF"), QColor(theme.ACCENT), QColor(theme.ACCENT)
        core.setAlphaF(min(1.0, 0.95 * strength))
        mid.setAlphaF(0.55 * strength)
        edge.setAlphaF(0)
        glow = QRadialGradient(self._c, radius)
        glow.setColorAt(0, core)
        glow.setColorAt(0.22, mid)
        glow.setColorAt(1, edge)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(self._c, radius, radius)

    def _ring(self, p: QPainter, radius: float, width: float, alpha: float) -> None:
        """A shock wave."""
        if alpha <= 0.01:
            return
        color = _mix(QColor(theme.ACCENT), QColor("#FFFFFF"), 0.35)
        color.setAlphaF(alpha)
        p.setPen(QPen(color, width))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(self._c, radius, radius)

    def _shimmer(self, p: QPainter, s: float, base: float) -> None:
        """Unfolding: a wave of light runs over the panel from the mic outwards (it loads); only on the picture."""
        if not 0 < s < 1:
            return
        band = 54
        rho = band * 0.5 + (self._far + band) * _out_cubic(s)
        outer = rho + band
        light = _mix(QColor(theme.ACCENT), QColor("#FFFFFF"), 0.6)
        clear = QColor(light)
        clear.setAlphaF(0)
        light.setAlphaF(base * 0.3 * math.sin(math.pi * s) ** 0.6)
        wave = QRadialGradient(self._c, outer)
        wave.setColorAt(max(0.0, (rho - band) / outer), clear)
        wave.setColorAt(rho / outer, light)
        wave.setColorAt(1, clear)
        p.save()
        p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        p.fillRect(self._shot_area, wave)
        p.restore()

    # -- the frames --------------------------------------------------------------------------

    def _paint_fold(self, p: QPainter, u: float, base: float) -> None:
        a = u / PANEL_END
        if a < 1:
            fade = base * (1 - _smooth(0.62, 1.0, a))
            if a > 0.4:  # fast now: a blur of where it just was
                for lag, share in ((0.045, 0.12), (0.03, 0.2), (0.015, 0.32)):
                    self._picture(p, *_fold_pose(a - lag), fade * share)
            self._picture(p, *_fold_pose(a), fade)
        self._glow(p, base * _smooth(0.3, 0.62, u) * (1 - _smooth(0.64, 0.96, u)),
                   self._icon_r * (0.8 + 1.2 * _smooth(0.3, 0.7, u)))
        self._stars_at(p, u, base)
        # the icon pops out, turning into place, its moon whipping round (the last frame exactly the button's icon)
        b = _clamp((u - 0.55) / 0.45) if u < 1 else 1.0
        if b >= 1:
            self._icon(p, base)
        elif b > 0:
            turn = _out_cubic(b)
            self._icon(p, base * min(1.0, b * 5), _out_back(b, 2.6), -150 * (1 - turn),
                       MOON_REST - 4 * math.pi * (1 - turn))
        for start, grow, width in ((0.62, 34, 3.2), (0.72, 20, 1.6)):
            w = _clamp((u - start) / (1 - start))
            if 0 < w < 1:
                self._ring(p, self._icon_r + grow * _out_cubic(w), width * (1 - w) + 0.6,
                           base * 0.9 * (1 - w) ** 1.6)

    def _paint_unfold(self, p: QPainter, u: float, base: float) -> None:
        grow = _clamp((u - 0.3) / 0.66) if u < 1 else 1.0  # the panel out of the planet
        if grow >= 1:
            self._picture(p, 1, 0, base)
        elif grow > 0:
            alpha = base * _smooth(0, 0.28, grow)
            if grow < 0.5:  # still fast: a zoom blur of where it just was
                for lag, share in ((0.06, 0.1), (0.04, 0.18), (0.02, 0.3)):
                    if grow > lag:
                        self._picture(p, *_unfold_pose(grow - lag), alpha * share)
            self._picture(p, *_unfold_pose(grow), alpha)
        self._shimmer(p, _clamp((u - 0.5) / 0.5), base)
        self._glow(p, base * _smooth(0.04, 0.3, u) * (1 - _smooth(0.32, 0.62, u)),
                   self._icon_r * (1.0 + 1.6 * _smooth(0.1, 0.4, u)))
        h = _clamp(u / 0.34)  # the icon swells, its moon speeding round, then bursts
        if h < 1:
            scale = 1 + 0.16 * _out_cubic(h / 0.62) if h < 0.62 else 1.16 * (1 - _in_back((h - 0.62) / 0.38, 1.2))
            self._icon(p, base, scale, 110 * h ** 3, None if h == 0 else MOON_REST + 3 * math.pi * h * h)
        for start, grow_px, width in ((0.3, 70, 3.4), (0.37, 46, 1.8)):
            w = _clamp((u - start) / 0.5)
            if 0 < w < 1:
                self._ring(p, self._icon_r * 0.8 + grow_px * _out_cubic(w), width * (1 - w) + 0.5,
                           base * 0.9 * (1 - w) ** 1.5)
        self._stars_at(p, u, base)

    def _paint(self, p: QPainter, u: float) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        base = self._from + (1 - self._from) * _clamp(u * self._ms / FADE_IN_MS)
        (self._paint_fold if self._folding else self._paint_unfold)(p, u, base)

    def paintEvent(self, event):
        p = QPainter(self)
        self._paint(p, self._u)
        p.end()

    def frame(self, u: float) -> QImage:
        """The frame at u (0–1) as an image of this window (tests, a look at it)."""
        ratio = self._shot.devicePixelRatio()
        image = QImage(round(self.width() * ratio), round(self.height() * ratio), QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.transparent)
        p = QPainter(image)
        self._paint(p, u)
        p.end()
        return image
