"""The Autopilot window (autopilot.py; the phone above the panel, "Autopilot…" in Orbit's menu). On top the calls:
the user's phone number, Bland AI's key (kept encrypted), the voice, no calls at night, a test call. On the left the
Claude Code sessions running now, each in its folder's colour like the panel; the chosen one on the right: what it
should work on and how often it may call, "Pustit na autopilota"; once it's on, what it's doing, its last report and
the last call (summary, transcript, price), "Zavolat teď" and "Vypnout autopilota". main.py does what's asked
(signals) and keeps the window current (show_state)."""
from PySide6.QtCore import QRect, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QGridLayout, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QVBoxLayout, QWidget)

from . import autopilot, bland, colors, theme
from .autopilot import INTERVALS, RESULTS, Pilot, clock_text
from .sessions import STATE_LABELS
from .theme import Toggle, style_titlebar
from .ui import _combo, _label, _repolish, mic_icon

ID = Qt.UserRole
ROW_H = 50


class _RowDelegate(QStyledItemDelegate):
    """A running session: a stripe in its folder's colour, its name, and below it its folder (in its colour), what it
    does and, on the Autopilot, its round or the next call (in the accent colour)."""

    def __init__(self, window: "AutopilotWindow"):
        super().__init__(window.list)
        self.window = window

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        s = self.window.sessions.get(index.data(ID))
        if s is None:
            return
        r, color = option.rect, QColor(self.window.color_of(s))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(r.left() + 5, r.top() + 9, 3, r.height() - 18), 1.5, 1.5)
        x, width = r.left() + 17, r.width() - 26
        font = QFont(theme.TEXT_FONT)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(QRect(x, r.top() + 6, width, 20), Qt.AlignLeft | Qt.AlignVCenter,
                         QFontMetrics(font).elidedText(s.name, Qt.ElideRight, width))
        font.setPixelSize(12)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        parts = [(s.folder, color.name()), (f" · {STATE_LABELS.get(s.state, s.state)}", theme.DIM)]
        pilot = self.window.pilots.get(s.id)
        if pilot:
            parts.append((f" · autopilot: {pilot.label()}", theme.ACCENT))
        end = x + width
        for text, ink in parts:
            left = end - x
            if left <= 0:
                break
            painter.setPen(QColor(ink))
            text = metrics.elidedText(text, Qt.ElideRight, left)
            painter.drawText(QRect(x, r.top() + 26, left, 18), Qt.AlignLeft | Qt.AlignVCenter, text)
            x += metrics.horizontalAdvance(text)
        painter.restore()


def _button(text: str, role: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("role", role)
    button.setAutoDefault(False)
    button.setCursor(Qt.PointingHandCursor)
    return button


def _box(minimum: int = 70) -> QPlainTextEdit:
    box = QPlainTextEdit()
    box.setReadOnly(True)
    box.setMinimumHeight(minimum)
    return box


def money(usd: float) -> str:
    return f"{usd:.2f} $".replace(".", ",")


class AutopilotWindow(QDialog):
    settings_saved = Signal(dict)  # {"phone", "key" (None = unchanged), "voice", "quiet"}
    test_requested = Signal()
    start_requested = Signal(str, str, int)  # session id, goal, interval in seconds
    stop_requested = Signal(str)
    call_requested = Signal(str)  # "Zavolat teď", or "Pokračovat" when it stands

    def __init__(self, cfg: dict, folder_colors):
        """cfg: Orbit's config as it is now (the phone, whether there's a key, the voice, the nights); folder_colors:
        () -> config folder_colors now."""
        super().__init__(None, Qt.Window)
        self.setObjectName("autopilot")
        self.setWindowTitle("Autopilot – Orbit")
        self.setWindowIcon(mic_icon("idle"))
        self.resize(1040, 700)
        self._folder_colors = folder_colors
        self.sessions: dict = {}  # running sessions by id, in the list's order
        self.pilots: dict[str, Pilot] = {}
        self._current = ""  # the chosen session's id
        self._look: tuple = ()
        self._has_key = bool(cfg.get("autopilot_key"))

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)
        root.addWidget(_label("Autopilot", "section"))
        root.addWidget(_label("Relace pracuje sama po kolech. Po každém kole ti zavolá na telefon, co udělala, co "
                              "navrhuje a na co se ptá, a tvoje odpověď v hovoru je její další zadání. Volá nejvýš "
                              "jednou za zvolenou dobu; když to nezvedneš, počká a zkusí to znovu.", "dim", wrap=True))

        calls = QGridLayout()
        calls.setHorizontalSpacing(10)
        calls.setVerticalSpacing(5)
        calls.addWidget(_label("Tvoje číslo", "step"), 0, 0)
        calls.addWidget(_label("Klíč Bland AI", "step"), 0, 1)
        calls.addWidget(_label("Hlas (nepovinné)", "step"), 0, 2)
        self.phone = QLineEdit(cfg.get("autopilot_phone", ""))
        self.phone.setPlaceholderText("+420 602 123 456")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.voice = QLineEdit(cfg.get("autopilot_voice", ""))
        self.voice.setPlaceholderText("výchozí hlas Blandu")
        self.voice.setToolTip("Jméno nebo ID hlasu z knihovny Bland AI. Prázdné = jeho výchozí.")
        calls.addWidget(self.phone, 1, 0)
        calls.addWidget(self.key, 1, 1)
        calls.addWidget(self.voice, 1, 2)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.quiet = Toggle(bool(cfg.get("autopilot_quiet", True)))
        row.addWidget(self.quiet)
        row.addWidget(_label("V noci (22–7 h) nevolat, hovor počká do rána"))
        row.addStretch(1)
        self.where = _button("Kde vzít klíč", "small")
        self.where.setToolTip(f"Otevře {bland.KEY_PAGE}: založ si účet a vytvoř API key. Hovory do Česka chtějí "
                              "nákup kreditu aspoň za 5 $.")
        self.where.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(bland.KEY_PAGE)))
        self.save = _button("Uložit", "ghost")
        self.save.clicked.connect(self._save)
        self.test = _button("Zkusit hovor", "ghost")
        self.test.setToolTip("Bland AI ti hned zavolá krátký zkušební hovor (stojí pár korun).")
        self.test.clicked.connect(self.test_requested.emit)
        for button in (self.where, self.save, self.test):
            row.addWidget(button)
        calls.addLayout(row, 2, 0, 1, 3)
        self.calls_status = _label("", "dim", wrap=True)
        calls.addWidget(self.calls_status, 3, 0, 1, 3)
        root.addLayout(calls)
        self._key_placeholder()

        main = QHBoxLayout()
        main.setSpacing(22)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(_label("Běžící relace", "step"))
        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setItemDelegate(_RowDelegate(self))
        self.list.currentItemChanged.connect(lambda item, _: self._select(item))
        left.addWidget(self.list, 1)
        holder = QWidget()
        holder.setLayout(left)
        holder.setFixedWidth(380)
        main.addWidget(holder)

        self.detail = QWidget()
        right = QVBoxLayout(self.detail)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        self.title = _label("", "section", wrap=True)
        right.addWidget(self.title)
        self.meta = _label("", "dim", wrap=True)
        right.addWidget(self.meta)
        # not on the autopilot: what to work on, how often to call
        self.setup = QWidget()
        setup = QVBoxLayout(self.setup)
        setup.setContentsMargins(0, 4, 0, 0)
        setup.setSpacing(6)
        setup.addWidget(_label("Na čem má pracovat", "step"))
        self.goal = QPlainTextEdit()
        self.goal.setPlaceholderText("Co má relace vyřešit? Prázdné = pokračovat v tom, na čem teď pracuje.")
        setup.addWidget(self.goal, 1)
        every = QHBoxLayout()
        every.setSpacing(8)
        every.addWidget(_label("Volat nejvýš jednou za"))
        self.interval = _combo()
        self.interval.setMinimumContentsLength(8)
        for seconds, text in INTERVALS.items():
            self.interval.addItem(text, seconds)
        self.interval.setCurrentIndex(self.interval.findData(autopilot.DEFAULT_INTERVAL))
        every.addWidget(self.interval)
        every.addStretch(1)
        self.start = _button("Pustit na autopilota", "primary")
        self.start.clicked.connect(self._start)
        every.addWidget(self.start)
        setup.addLayout(every)
        right.addWidget(self.setup, 1)
        # on it: what it's doing, the last report and call
        self.running = QWidget()
        running = QVBoxLayout(self.running)
        running.setContentsMargins(0, 4, 0, 0)
        running.setSpacing(6)
        self.state = _label("", None, wrap=True)
        running.addWidget(self.state)
        self.goal_shown = _label("", "dim", wrap=True)
        running.addWidget(self.goal_shown)
        running.addWidget(_label("Poslední hlášení", "step"))
        self.report = _box()
        running.addWidget(self.report, 1)
        self.call_head = _label("Poslední hovor", "step")
        running.addWidget(self.call_head)
        self.call_meta = _label("", "dim", wrap=True)
        running.addWidget(self.call_meta)
        self.transcript = _box(90)
        running.addWidget(self.transcript, 2)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.call = _button("Zavolat teď", "primary")
        self.call.clicked.connect(lambda: self._current and self.call_requested.emit(self._current))
        self.off = _button("Vypnout autopilota", "ghost")
        self.off.clicked.connect(lambda: self._current and self.stop_requested.emit(self._current))
        buttons.addWidget(self.call)
        buttons.addWidget(self.off)
        buttons.addStretch(1)
        running.addLayout(buttons)
        right.addWidget(self.running, 1)
        self.status = _label("", "dim", wrap=True)
        right.addWidget(self.status)
        main.addWidget(self.detail, 1)
        self.empty = _label("Teď neběží žádná relace Claude Code. Spusť ji (třeba plusem nad panelem) a vrať se sem.",
                            "dim", wrap=True)
        self.empty.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        main.addWidget(self.empty, 1)
        root.addLayout(main, 1)
        root.addWidget(_label("Hovory jdou přes Bland AI: hlášení relace a to, co do telefonu řekneš, projde jejich "
                              "servery. Klíč je v počítači zašifrovaný pro tvůj účet Windows. Relace potřebuje mod "
                              "orbit-mozek 0.4 nebo novější.", "dim", wrap=True))
        self.show_state([], {})

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self)

    def color_of(self, s) -> str:
        return colors.accent(colors.color_for(s.cwd or s.folder, self._folder_colors()))

    # -- the calls ---------------------------------------------------------------------------------------------

    def _key_placeholder(self) -> None:
        self.key.setPlaceholderText("uložený (nový sem vlož jen při změně)" if self._has_key else
                                    "API key z v2.app.bland.ai")

    def _save(self) -> None:
        phone = self.phone.text().strip()
        number = bland.normalize_phone(phone) if phone else ""
        if number is None:
            self.say_calls("Tohle číslo neznám. Napiš ho třeba jako +420 602 123 456.", warn=True)
            return
        key = self.key.text().strip()
        self.phone.setText(number)
        self.key.clear()
        self._has_key = self._has_key or bool(key)
        self._key_placeholder()
        self.settings_saved.emit({"phone": number, "key": key or None, "voice": self.voice.text().strip(),
                                  "quiet": self.quiet.isChecked()})

    def key_saved(self, has_key: bool) -> None:
        self._has_key = has_key
        self._key_placeholder()

    def say_calls(self, text: str, warn: bool = False, ok: bool = False) -> None:
        self.calls_status.setText(text)
        _repolish(self.calls_status, role="warn" if warn else "ok" if ok else "dim")

    def say(self, text: str, warn: bool = False) -> None:
        self.status.setText(text)
        _repolish(self.status, role="warn" if warn else "dim")

    # -- the sessions ------------------------------------------------------------------------------------------

    def show_state(self, running: list, pilots: dict[str, Pilot]) -> None:
        """The running sessions (the panel's order) and who's on the Autopilot; repaints only what changed."""
        look = (tuple((s.id, s.name, s.folder, s.state) for s in running),
                tuple((sid, p.stage, p.round, p.label(), p.note, p.report, len(p.calls),
                       p.calls[-1].result if p.calls else "") for sid, p in pilots.items()),
                tuple(sorted(self._folder_colors().items())))
        if look == self._look:
            return
        self._look = look
        self.sessions = {s.id: s for s in running}
        self.pilots = dict(pilots)
        keep = self._current
        self.list.blockSignals(True)
        self.list.clear()
        chosen = None
        for s in running:
            item = QListWidgetItem()
            item.setData(ID, s.id)
            item.setToolTip(f"{s.name}\n{s.cwd}")
            self.list.addItem(item)
            if s.id == keep:
                chosen = item
        self.list.blockSignals(False)
        has = self.list.count() > 0
        self.detail.setVisible(has)
        self.empty.setVisible(not has)
        self.list.setCurrentItem(chosen or self.list.item(0))
        self._select(self.list.currentItem())

    def choose(self, session_id: str) -> None:
        """That session chosen (a click on an Autopilot bubble), now or once the list has it."""
        self._current = session_id
        for i in range(self.list.count()):
            if self.list.item(i).data(ID) == session_id:
                self.list.setCurrentRow(i)

    def _select(self, item: QListWidgetItem | None) -> None:
        sid = item.data(ID) if item else ""
        s = self.sessions.get(sid)
        if s is None:
            self._current = ""
            return
        if sid != self._current:
            self.say("")
            self.goal.clear()
        self._current = sid
        self.title.setText(s.name)
        self.meta.setText(f"{s.cwd} · {STATE_LABELS.get(s.state, s.state)}")
        pilot = self.pilots.get(sid)
        self.setup.setVisible(pilot is None)
        self.running.setVisible(pilot is not None)
        if pilot is None:
            return
        self.state.setText(pilot.describe())
        self.goal_shown.setText(f"Cíl: {pilot.goal}" if pilot.goal else "Cíl: pokračovat v tom, na čem pracuje.")
        report = pilot.report or "Zatím žádné: první kolo ještě běží."
        if self.report.toPlainText() != report:
            self.report.setPlainText(report)
        call = pilot.calls[-1] if pilot.calls else None
        self.call_head.setVisible(call is not None)
        self.call_meta.setVisible(call is not None)
        self.transcript.setVisible(call is not None)
        if call is not None:
            parts = [f"{clock_text(call.at)}, kolo {call.round}: {RESULTS.get(call.result, call.result)}"]
            if call.minutes:
                parts.append(f"{call.minutes:.1f} min".replace(".", ","))
            if call.price:
                parts.append(money(call.price))
            total = sum(c.price for c in pilot.calls)
            if total and len(pilot.calls) > 1:
                parts.append(f"celkem {money(total)} za {len(pilot.calls)} hovorů")
            self.call_meta.setText(" · ".join(parts) + (f"\n{call.error}" if call.error else ""))
            text = "\n\n".join(t for t in (f"Shrnutí: {call.summary}" if call.summary else "", call.transcript) if t)
            text = text or "(bez přepisu)"
            if self.transcript.toPlainText() != text:
                self.transcript.setPlainText(text)
        stands = pilot.stage == "paused"
        self.call.setText("Pokračovat" if stands else "Zavolat teď")
        self.call.setEnabled(pilot.stage in ("waiting", "paused"))
        self.call.setToolTip("Zkusí znovu, na čem autopilot stojí." if stands else
                             "Hned zavolá s posledním hlášením, i v noci a bez čekání na interval.")

    def _start(self) -> None:
        if self._current:
            self.start_requested.emit(self._current, self.goal.toPlainText(), self.interval.currentData())
