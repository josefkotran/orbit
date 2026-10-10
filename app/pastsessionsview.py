"""The session history window (pastsessions.py; the clock above the panel, "Historie relací…" in Orbit's menu): the
user's past Claude Code sessions as `claude --resume` offers them, newest first, each in its folder's colour like the
sessions in the panel; a search (diacritics not needed) and a folder above them. The chosen one on the right with its
first and newest prompt, and "Pokračovat v relaci" (also a double click or Enter): claude --resume in its folder, in a
window of its own (main: favorites.start_session). One that runs right now shows "běží" and its window comes to the
front instead of the session opening a second time. Read again every few seconds while the window is open, in a
thread of its own (the first read of all transcripts takes a second or two)."""
import os
import threading

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
                               QVBoxLayout, QWidget)

from . import colors, favorites, pastsessions, theme
from .theme import style_titlebar
from .ui import _combo, _label, _repolish, mic_icon

ID = Qt.UserRole
ROW_H = 50
REFRESH_MS = 5000  # read again this often while the window is open (only changed transcripts are read)
RUNNING = "#3DD68C"  # "běží", the panel's green


def count_text(n: int) -> str:
    return f"{n} relace" if 1 <= n <= 4 else f"{n} relací"


class _RowDelegate(QStyledItemDelegate):
    """A session: a stripe in its folder's colour, its name, and dim below it when it was last worked on, its folder
    (in its colour) and "běží" when it runs right now."""

    def __init__(self, window: "SessionHistory"):
        super().__init__(window.list)
        self.window = window

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""  # the background (hover, selection) as the style sheet has it, the text below
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        past = self.window.shown.get(index.data(ID))
        if past is None:
            return
        r, color = option.rect, QColor(self.window.color_of(past))
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
                         QFontMetrics(font).elidedText(past.name, Qt.ElideRight, width))
        font.setPixelSize(12)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        parts = [(f"{pastsessions.when(past.modified)} · ", theme.DIM), (past.folder, color.name())]
        if past.id in self.window.running:
            parts.append((" · běží", RUNNING))
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


class SessionHistory(QDialog):
    resume_requested = Signal(str)  # a session's id: going on in its folder (or its window, when it runs)
    _scanned = Signal(object)  # the sessions read in the scan thread

    def __init__(self, index: pastsessions.Index, folder_colors, running):
        """folder_colors: () -> config folder_colors now; running: () -> ids of the sessions running now."""
        super().__init__(None, Qt.Window)
        self.setObjectName("pastsessions")
        self.setWindowTitle("Historie relací – Orbit")
        self.setWindowIcon(mic_icon("idle"))
        self.resize(980, 620)
        self.index, self._folder_colors, self._running_now = index, folder_colors, running
        self.sessions: list[pastsessions.Past] = []  # all of them, newest first
        self.shown: dict[str, pastsessions.Past] = {}  # the listed ones by id
        self.running: set[str] = set()
        self._current: pastsessions.Past | None = None
        self._loaded = False
        self._scanning = False
        self._look: tuple = ()  # what the list showed after the last scan (nothing new = no rebuild)
        self._scanned.connect(self._got)
        self._timer = QTimer(self, interval=REFRESH_MS)
        self._timer.timeout.connect(self.reload)

        root = QHBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(_label("Historie relací", "section"))
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat v názvech a zadáních…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.search, 1)
        self.folder = _combo()
        self.folder.setMinimumContentsLength(10)
        self.folder.setToolTip("Jen relace z jedné složky")
        self.folder.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.folder)
        left.addLayout(filters)
        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMouseTracking(True)
        self.list.setToolTip("Dvojklik nebo Enter: pokračovat v relaci.")
        self.list.setItemDelegate(_RowDelegate(self))
        self.list.currentItemChanged.connect(lambda item, _: self._select(item))
        self.list.itemActivated.connect(lambda item: self._resume())
        left.addWidget(self.list, 1)
        self.count = _label("", "dim", wrap=True)
        left.addWidget(self.count)
        holder = QWidget()
        holder.setLayout(left)
        holder.setFixedWidth(400)
        root.addWidget(holder)

        self.detail = QWidget()
        right = QVBoxLayout(self.detail)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        self.title = _label("", "section", wrap=True)
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addWidget(self.title)
        self.meta = _label("", "dim", wrap=True)
        self.meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addWidget(self.meta)
        self.first_head = _label("První zadání", "step")
        right.addSpacing(4)
        right.addWidget(self.first_head)
        self.first = self._prompt_box()
        right.addWidget(self.first, 1)
        self.last_head = _label("Poslední zadání", "step")
        right.addWidget(self.last_head)
        self.last = self._prompt_box()
        right.addWidget(self.last, 1)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.resume = QPushButton("Pokračovat v relaci")
        self.resume.setProperty("role", "primary")
        self.resume.clicked.connect(self._resume)
        self.copy = QPushButton("Kopírovat příkaz")
        self.copy.setProperty("role", "ghost")
        self.copy.clicked.connect(self._copy)
        self.open_folder = QPushButton("Otevřít složku")
        self.open_folder.setProperty("role", "small")
        self.open_folder.clicked.connect(self._open_folder)
        for button in (self.resume, self.copy, self.open_folder):
            button.setAutoDefault(False)
            button.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch(1)
        right.addLayout(buttons)
        self.status = _label("", "dim", wrap=True)
        right.addWidget(self.status)
        root.addWidget(self.detail, 1)
        self.empty = _label("Načítám relace…", "dim", wrap=True)
        self.empty.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        root.addWidget(self.empty, 1)
        self.refresh()

    @staticmethod
    def _prompt_box() -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setMinimumHeight(70)
        return box

    def color_of(self, past: pastsessions.Past) -> str:
        return colors.accent(colors.color_for(past.cwd, self._folder_colors()))

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self)
        self.reload()
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    # -- reading ---------------------------------------------------------------------------------

    def reload(self) -> None:
        """Reads the transcripts again in a thread (only what changed); the list follows when it's done."""
        if self._scanning:
            return
        self._scanning = True
        threading.Thread(target=lambda: self._scanned.emit(self.index.scan()), daemon=True).start()

    def _got(self, found: list) -> None:
        self._scanning = False
        self._loaded = True
        running = set(self._running_now())
        look = (tuple((p.id, p.modified, p.name) for p in found), frozenset(running),
                tuple(sorted(self._folder_colors().items())))
        if look == self._look:
            return
        self._look = look
        self.sessions, self.running = found, running
        self._fill_folders()
        self.refresh()

    def _fill_folders(self) -> None:
        """"Všechny složky", then each folder by name with how many sessions it has."""
        chosen = self.folder.currentData()
        counts: dict[str, int] = {}
        paths: dict[str, str] = {}
        for past in self.sessions:
            key = os.path.normcase(os.path.normpath(past.cwd))
            counts[key] = counts.get(key, 0) + 1
            paths.setdefault(key, past.cwd)
        names = favorites.labels(list(paths.values()))
        self.folder.blockSignals(True)
        self.folder.clear()
        self.folder.addItem("Všechny složky", "")
        for key in sorted(paths, key=lambda k: names[paths[k]].lower()):
            self.folder.addItem(f"{names[paths[key]]} ({counts[key]})", key)
        at = self.folder.findData(chosen) if chosen else 0
        self.folder.setCurrentIndex(max(at, 0))
        self.folder.blockSignals(False)

    # -- the list -------------------------------------------------------------------------------

    def refresh(self) -> None:
        keep = self._current.id if self._current else None
        scrolled = self.list.verticalScrollBar().value()
        query = pastsessions.fold(self.search.text().strip())
        folder = self.folder.currentData() or ""
        self.list.blockSignals(True)
        self.list.clear()
        self.shown, chosen = {}, None
        for past in self.sessions:
            if folder and os.path.normcase(os.path.normpath(past.cwd)) != folder:
                continue
            if query and not pastsessions.matches(past, query):
                continue
            item = QListWidgetItem()
            item.setData(ID, past.id)
            item.setToolTip(f"{past.name}\n{past.cwd}")
            self.list.addItem(item)
            self.shown[past.id] = past
            if past.id == keep:
                chosen = item
        self.list.blockSignals(False)
        has = self.list.count() > 0
        self.detail.setVisible(has)
        self.empty.setVisible(not has)
        if not self._loaded:
            self.empty.setText("Načítám relace…")
        elif self.sessions:
            self.empty.setText("Nic takového tu není.")
        else:
            self.empty.setText("Zatím tu žádná minulá relace Claude Code není. Každá relace, ve které něco "
                               "napíšeš, se sem zapíše sama.")
        if query or folder:
            self.count.setText(f"Nalezeno: {self.list.count()} z {len(self.sessions)}")
        elif self.sessions:
            self.count.setText(f"{count_text(len(self.sessions))}. Starší než {pastsessions.kept_days()} dní "
                               "Claude Code sám maže.")
        else:
            self.count.setText("")
        self.list.setCurrentItem(chosen or self.list.item(0))
        if chosen is not None:
            self.list.verticalScrollBar().setValue(scrolled)
        self._select(self.list.currentItem())

    def _select(self, item: QListWidgetItem | None) -> None:
        past = self.shown.get(item.data(ID)) if item else None
        changed = past is None or self._current is None or past.id != self._current.id
        self._current = past
        if past is None:
            return
        self.title.setText(past.name)
        when = f"Začala {pastsessions.when(past.created)}"
        if past.modified - past.created > 120:
            when += f", naposledy {pastsessions.when(past.modified)}"
        lines = [past.cwd + (f" · větev {past.branch}" if past.branch and past.branch != "HEAD" else ""),
                 when + (f" · {past.prompts} zadání" if past.prompts else "")]
        self.meta.setText("\n".join(lines))
        for box, text in ((self.first, past.first), (self.last, past.last)):
            if box.toPlainText() != text:
                box.setPlainText(text)
        same = " ".join(past.last.split()) == " ".join(past.first.split())
        self.last.setVisible(not same)
        self.last_head.setVisible(not same)
        self.first_head.setText("Zadání" if same else "První zadání")
        running = past.id in self.running
        self.resume.setText("Přepnout do relace" if running else "Pokračovat v relaci")
        self.resume.setToolTip("Relace právě běží: přenese její okno dopředu." if running else
                               f"Otevře relaci znovu v novém okně terminálu ve složce {past.folder} "
                               "(claude --resume), i s celou konverzací.")
        self.copy.setToolTip(f"Zkopíruje „claude --resume {past.id}“, spusť ho ve složce {past.cwd}.")
        self.open_folder.setEnabled(os.path.isdir(past.cwd))
        if changed:
            self.status.setText("")

    def say(self, text: str, warn: bool = False) -> None:
        self.status.setText(text)
        _repolish(self.status, role="warn" if warn else "dim")

    # -- what's done with one ----------------------------------------------------------------------

    def _resume(self) -> None:
        if self._current:
            self.resume_requested.emit(self._current.id)

    def _copy(self) -> None:
        if self._current:
            QGuiApplication.clipboard().setText(f"claude --resume {self._current.id}")
            self.say(f"Zkopírováno. Spusť to v terminálu ve složce {self._current.folder}.")

    def _open_folder(self) -> None:
        if self._current and os.path.isdir(self._current.cwd):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._current.cwd))
