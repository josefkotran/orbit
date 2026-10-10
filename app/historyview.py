"""The dictation history window (history.py; the speech bubble next to the notebook above the panel, and Orbit's
menu): every dictation, and what was said to the voice agent Orbit (since 10 Oct: a stripe in the accent colour,
"Agent Orbit", its answer and what it sent on the right), newest first, each copied with one click on the icon at its
row's end (or a double click), a search and Všechno / Diktáty / Agent Orbit above them; the chosen one on the right
with the rest of what can be done with it: insert it again where the user was (this window goes away first, so
Windows brings that window back), listen to its recording, transcribe it again, correct it (the correction goes to
vocabulary learning: editing.word_changes) or delete it."""
import time
import unicodedata
import winsound
from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QVBoxLayout, QWidget)

from . import history, theme
from .theme import style_titlebar
from .ui import _combo, _label, _repolish, mic_icon

ID = Qt.UserRole
HEAD = Qt.UserRole + 1  # a row's first line: when, where it went
AGENT_LABEL = "Agent Orbit"
SHOW = [("", "Všechno"), ("dictation", "Diktáty"), (history.AGENT, AGENT_LABEL)]  # the filter above the list
ROW_H = 46
EMPTY = ("Zatím tu nic není. Každý diktát se sem zapíše, i když skončí ve schránce, a taky to, co řekneš agentovi "
         "Orbit.")
OUTCOMES = {history.INSERTED: "vloženo", history.CLIPBOARD: "ve schránce", history.FAILED: "přepis selhal"}
COPY_GLYPH, CHECK_GLYPH = chr(0xE8C8), chr(0xE73E)  # "Copy", "CheckMark" in Segoe Fluent Icons
COPY_ZONE = 34  # px at a row's right end: its copy icon
COPIED_MS = 1500  # the tick stays this long after a copy


def when(at: float) -> str:
    """"14:32" today, "8. 10. 14:32" before."""
    t, now = time.localtime(at), time.localtime()
    clock = f"{t.tm_hour}:{t.tm_min:02d}"
    return clock if t[:3] == now[:3] else f"{t.tm_mday}. {t.tm_mon}. {clock}"


def first_line(text: str, limit: int = 36) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


def _fold(text: str) -> str:
    """For the search: lower case without diacritics ("dalsi" finds "další")."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


class _RowDelegate(QStyledItemDelegate):
    """A row: when and where it went (dim; "Agent Orbit" in the accent colour, with a stripe of it on the left, for
    what was said to the agent), its text, and a copy icon at its right end (a green tick for a moment after it was
    copied)."""

    def __init__(self, view):
        super().__init__(view)
        self.copied = ""  # the entry just copied
        self.agent: set[str] = set()  # the rows said to the agent

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""  # the background (hover, selection) as the style sheet has it; the text below
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        r, agent = option.rect, index.data(ID) in self.agent
        x, width = r.left() + (16 if agent else 8), r.width() - COPY_ZONE - (16 if agent else 8)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if agent:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.ACCENT))
            painter.drawRoundedRect(QRectF(r.left() + 5, r.top() + 8, 3, r.height() - 16), 1.5, 1.5)
        font = QFont(theme.TEXT_FONT)
        font.setPixelSize(12)
        painter.setFont(font)
        head, metrics = index.data(HEAD) or "", QFontMetrics(font)
        if agent:  # "dnes 12:30 · " dim, then "Agent Orbit" in the accent colour
            when = head.removesuffix(AGENT_LABEL)
            painter.setPen(QColor(theme.DIM))
            painter.drawText(QRect(x, r.top() + 5, width, 18), Qt.AlignLeft | Qt.AlignVCenter, when)
            painter.setPen(QColor(theme.ACCENT))
            painter.drawText(QRect(x + metrics.horizontalAdvance(when), r.top() + 5, width, 18),
                             Qt.AlignLeft | Qt.AlignVCenter, AGENT_LABEL)
        else:
            painter.setPen(QColor(theme.DIM))
            painter.drawText(QRect(x, r.top() + 5, width, 18), Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(head, Qt.ElideRight, width))
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(QRect(x, r.top() + 23, width, 19), Qt.AlignLeft | Qt.AlignVCenter,
                         QFontMetrics(font).elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, width))
        painter.restore()
        zone = QRect(option.rect.right() - COPY_ZONE + 1, option.rect.top(), COPY_ZONE, option.rect.height())
        done = index.data(ID) == self.copied
        hovered = bool(option.state & QStyle.State_MouseOver)
        painter.save()
        font = QFont(theme.icon_font())
        font.setPixelSize(15)
        painter.setFont(font)
        painter.setPen(QColor("#3DD68C" if done else theme.TEXT if hovered else theme.DIM))
        painter.drawText(zone, Qt.AlignCenter, CHECK_GLYPH if done else COPY_GLYPH)
        painter.restore()


class _Rows(QListWidget):
    """The dictations: a click on a row's copy icon, or Ctrl+C, copies it (copy(entry id))."""
    copy = Signal(str)

    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if (event.button() == Qt.LeftButton and index.isValid()
                and event.position().x() >= self.visualRect(index).right() - COPY_ZONE):
            self.copy.emit(index.data(ID))
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy) and self.currentItem():
            self.copy.emit(self.currentItem().data(ID))
            return
        super().keyPressEvent(event)


class HistoryWindow(QDialog):
    insert_requested = Signal(str)  # an entry's id: into the window the user was in (this one has gone away)
    copy_requested = Signal(str)
    retranscribe_requested = Signal(str)
    correction_saved = Signal(str, str)  # an entry's id, the corrected text
    remove_requested = Signal(str)
    clear_requested = Signal()

    def __init__(self, items: history.History, recordings: Path):
        super().__init__(None, Qt.Window)
        self.setObjectName("history")
        self.setWindowTitle("Historie diktátů – Orbit")
        self.setWindowIcon(mic_icon("idle"))
        self.resize(900, 580)
        self.history, self._recordings = items, recordings
        self._current: history.Entry | None = None
        self._shown = ("", "")  # the entry whose text is on the right: its id and its text then
        self._playing = QTimer(self, singleShot=True)  # when the recording that plays ends
        self._playing.timeout.connect(self._played)

        root = QHBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(_label("Historie diktátů", "section"))
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat v diktátech…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.search, 1)
        self.show_kind = _combo()
        self.show_kind.setMinimumContentsLength(9)
        for value, label in SHOW:
            self.show_kind.addItem(label, value)
        self.show_kind.setToolTip("Diktáty do oken, nebo věty pro agenta Orbit")
        self.show_kind.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.show_kind)
        left.addLayout(filters)
        self.list = _Rows()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # first_line() keeps the rows short
        self.list.setMouseTracking(True)  # the copy icon lights up under the mouse
        self.list.setToolTip("Ikona vpravo, dvojklik nebo Ctrl+C diktát zkopíruje. S modrým proužkem: řečeno "
                             "agentovi Orbit.")
        self._rows = _RowDelegate(self.list)
        self.list.setItemDelegate(self._rows)
        self.list.currentItemChanged.connect(lambda item, _: self._select(item))
        self.list.itemDoubleClicked.connect(lambda item: self._copy_row(item.data(ID)))
        self.list.copy.connect(self._copy_row)
        self._copied_timer = QTimer(self, singleShot=True, interval=COPIED_MS)
        self._copied_timer.timeout.connect(self._copied_gone)
        left.addWidget(self.list, 1)
        self.count = _label("", "dim", wrap=True)
        left.addWidget(self.count)
        clear = QPushButton("Vymazat historii")
        clear.setProperty("role", "small")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._clear)
        bottom = QHBoxLayout()
        bottom.addWidget(clear)
        bottom.addStretch(1)
        left.addLayout(bottom)
        holder = QWidget()
        holder.setLayout(left)
        holder.setFixedWidth(330)
        root.addWidget(holder)

        self.detail = QWidget()
        right = QVBoxLayout(self.detail)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        self.meta = _label("", "dim", wrap=True)
        right.addWidget(self.meta)
        self.edit_info = _label("", "dim", wrap=True)  # an edit by voice: its instruction and the text before it
        self.edit_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addWidget(self.edit_info)
        self.text = QPlainTextEdit()
        self.text.setToolTip("Text můžeš opravit a uložit: Orbit se z opravy učí slovník.")
        self.text.textChanged.connect(self._text_changed)
        right.addWidget(self.text, 1)
        self.reply_head = _label("Odpověď agenta Orbit", "step")  # said to the agent: what came back
        right.addWidget(self.reply_head)
        self.reply = QPlainTextEdit()
        self.reply.setReadOnly(True)
        self.reply.setToolTip("Co agent odpověděl a co poslal do relace nebo otevřel.")
        right.addWidget(self.reply, 1)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.insert = QPushButton("Vložit")
        self.insert.setProperty("role", "primary")
        self.insert.setToolTip("Vloží text do okna, které bylo vpředu před otevřením historie.")
        self.insert.clicked.connect(self._insert)
        self.copy = QPushButton("Kopírovat")
        self.copy.setProperty("role", "ghost")
        self.copy.clicked.connect(lambda: self._current and self._copy_row(self._current.id))
        self.save = QPushButton("Uložit opravu")
        self.save.setProperty("role", "ghost")
        self.save.setToolTip("Uloží opravený text. Slova, která Whisper přeslechl, si Orbit zapamatuje pro učení "
                             "slovníku.")
        self.save.clicked.connect(self._save)
        for button in (self.insert, self.copy, self.save):
            button.setAutoDefault(False)
            button.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch(1)
        right.addLayout(buttons)
        more = QHBoxLayout()
        more.setSpacing(6)
        self.play = QPushButton("Přehrát nahrávku")
        self.again = QPushButton("Přepsat znovu")
        self.again.setToolTip("Přepíše nahrávku znovu (s dnešním slovníkem). Původní text se nahradí.")
        self.remove = QPushButton("Smazat")
        for button in (self.play, self.again, self.remove):
            button.setProperty("role", "small")
            button.setAutoDefault(False)
            button.setCursor(Qt.PointingHandCursor)
            more.addWidget(button)
        self.play.clicked.connect(self._play)
        self.again.clicked.connect(lambda: self._emit(self.retranscribe_requested, "Přepisuji…"))
        self.remove.clicked.connect(self._remove)
        more.addStretch(1)
        right.addLayout(more)
        self.status = _label("", "dim", wrap=True)
        right.addWidget(self.status)
        root.addWidget(self.detail, 1)
        self.empty = _label(EMPTY, "dim", wrap=True)
        root.addWidget(self.empty, 1)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self)

    def closeEvent(self, event):
        self._stop_playing()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._stop_playing()
        super().hideEvent(event)

    # -- the list -------------------------------------------------------------------------------

    def refresh(self, select: str | None = None, status: str = "") -> None:
        keep = select or (self._current.id if self._current else None)
        query = _fold(self.search.text().strip())
        show = self.show_kind.currentData() or ""
        scrolled = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        self._rows.agent = set()
        chosen = None
        for entry in reversed(self.history.items):
            agent = entry.kind == history.AGENT
            if show and (show == history.AGENT) != agent:
                continue
            words = f"{entry.best} {entry.app} {entry.instruction}" + (f" {AGENT_LABEL} {entry.reply} {entry.action}"
                                                                       if agent else "")
            if query and query not in _fold(words):
                continue
            if agent:
                head = f"{when(entry.at)} · {AGENT_LABEL}"
                self._rows.agent.add(entry.id)
            else:
                outcome = OUTCOMES.get(entry.outcome, "")
                head = f"{when(entry.at)} · {entry.app or '?'}" + (f" · {outcome}" if entry.outcome != history.INSERTED
                                                                   else "")
                if entry.instruction:
                    head += " · úprava"
            item = QListWidgetItem(first_line(entry.best, 80) or "(bez textu)")
            item.setData(ID, entry.id)
            item.setData(HEAD, head)
            item.setToolTip(("Pro agenta Orbit: " if agent else "") + entry.best[:500])
            self.list.addItem(item)
            if entry.id == keep:
                chosen = item
        self.list.blockSignals(False)
        has = self.list.count() > 0
        self.detail.setVisible(has)
        self.empty.setVisible(not has)
        self.empty.setText("Nic takového tu není." if (query or show) and self.history.items else EMPTY)
        if query or show:
            self.count.setText(f"Nalezeno: {self.list.count()} z {len(self.history.items)}")
        elif not has:
            self.count.setText("")
        elif self.history.persist:
            self.count.setText(f"Jen v tomhle počítači, nejvýš {history.MAX_ITEMS} posledních.")
        else:
            self.count.setText("Historie se neukládá (Nastavení), tady je jen poslední diktát.")
        self.list.setCurrentItem(chosen or self.list.item(0))
        if chosen is not None:  # (refreshed while the agent answers: the list stays where it was)
            self.list.verticalScrollBar().setValue(scrolled)
        self._select(self.list.currentItem())
        if status:
            self._say(status)

    def _select(self, item: QListWidgetItem | None) -> None:
        """The chosen entry on the right. The same one again (the list refreshed while the agent answers) keeps an
        unsaved correction, the cursor and a recording that plays."""
        entry = self.history.get(item.data(ID)) if item else None
        same = entry is not None and self._shown == (entry.id, entry.best)  # and its text didn't change meanwhile
        if not same:
            self._stop_playing()
        self._current = entry
        if entry is None:
            return
        agent = entry.kind == history.AGENT
        parts = [when(entry.at)]
        if agent:
            parts.append("pro agenta Orbit")
        elif entry.app:
            parts.append(entry.app)
        if not agent:
            parts.append(OUTCOMES.get(entry.outcome, entry.outcome))
        if entry.seconds:
            parts.append(f"{entry.seconds:.0f} s řeči".replace(".", ","))
        if entry.key == "send":
            parts.append("odesláno Enterem")
        if entry.corrected:
            parts.append("opraveno")
        self.meta.setText(" · ".join(parts))
        info = f"Pokyn: {entry.instruction}" if entry.instruction else ""
        if entry.instruction and entry.original:
            info += f"\nPůvodně: {first_line(entry.original, 300)}"
        self.edit_info.setText(info)
        self.edit_info.setVisible(bool(info))
        if not same:
            self.text.blockSignals(True)
            self.text.setPlainText(entry.best)
            self.text.blockSignals(False)
            self._shown = (entry.id, entry.best)
        answer = "\n\n".join(x for x in (entry.reply, entry.action) if x) or "(agent zatím neodpověděl)"
        if agent and self.reply.toPlainText() != answer:
            self.reply.setPlainText(answer)
        self.reply_head.setVisible(agent)
        self.reply.setVisible(agent)
        has_audio = bool(entry.recording) and self._wav(entry).is_file()
        self.play.setVisible(has_audio)
        self.again.setVisible(has_audio)
        if not same:
            self.play.setText("Přehrát nahrávku")
            self.status.setText("")
        self._text_changed()

    def _wav(self, entry: history.Entry) -> Path:
        return self._recordings / f"{entry.recording}.wav"

    def _text_changed(self) -> None:
        entry = self._current
        changed = bool(entry) and self.text.toPlainText().strip() != entry.best.strip()
        self.save.setEnabled(changed and bool(self.text.toPlainText().strip()))
        self.insert.setEnabled(bool(self.text.toPlainText().strip()))
        self.copy.setEnabled(bool(self.text.toPlainText().strip()))

    def _say(self, text: str, warn: bool = False) -> None:
        self.status.setText(text)
        _repolish(self.status, role="warn" if warn else "dim")

    # -- what's done with an entry ----------------------------------------------------------------

    def _emit(self, signal, status: str = "") -> None:
        if not self._current:
            return
        self._keep_edit()
        signal.emit(self._current.id)
        if status:
            self._say(status)

    def _copy_row(self, entry_id: str) -> None:
        """One click (or a double click, or Ctrl+C): the dictation on the clipboard, a tick on its row."""
        if self._current and self._current.id == entry_id:
            self._keep_edit()  # an edited text: the edited one
        self.copy_requested.emit(entry_id)
        self._rows.copied = entry_id
        self.list.viewport().update()
        self._copied_timer.start()
        self._say("Zkopírováno, vlož ho Ctrl+V.")

    def _copied_gone(self) -> None:
        self._rows.copied = ""
        self.list.viewport().update()

    def _keep_edit(self) -> None:
        """Inserting or copying an edited text uses the edited one: saved as the correction first."""
        if self._current and self.save.isEnabled():
            self._save()

    def _insert(self) -> None:
        """This window goes away first: Windows then brings back the one the user was in, and the text goes there."""
        if not self._current or not self.text.toPlainText().strip():
            return
        self._keep_edit()
        entry_id = self._current.id
        self.hide()
        QTimer.singleShot(250, lambda: self.insert_requested.emit(entry_id))

    def _save(self) -> None:
        entry = self._current
        text = self.text.toPlainText().strip()
        if entry and text and text != entry.best.strip():
            self.correction_saved.emit(entry.id, text)

    def _remove(self) -> None:
        if self._current:
            self.remove_requested.emit(self._current.id)

    def _clear(self) -> None:
        if not self.history.items:
            return
        box = QMessageBox(QMessageBox.Question, "Vymazat historii",
                          f"Smazat všechny diktáty z historie ({len(self.history.items)})? Nahrávky ve složce "
                          "recordings zůstanou.", QMessageBox.Yes | QMessageBox.No, self)
        box.button(QMessageBox.Yes).setText("Smazat")
        box.button(QMessageBox.No).setText("Nechat")
        box.setDefaultButton(QMessageBox.No)
        if box.exec() == QMessageBox.Yes:
            self.clear_requested.emit()

    # -- listening to the recording -------------------------------------------------------------

    def _play(self) -> None:
        if self._playing.isActive():
            self._stop_playing()
            return
        entry = self._current
        if not entry or not self._wav(entry).is_file():
            return
        try:
            winsound.PlaySound(str(self._wav(entry)),
                               winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except RuntimeError as e:
            self._say(f"Nahrávku nejde přehrát: {e}", warn=True)
            return
        self.play.setText("Zastavit")
        self._playing.start(int(max(entry.seconds, 0.5) * 1000) + 300)

    def _played(self) -> None:
        self.play.setText("Přehrát nahrávku")

    def _stop_playing(self) -> None:
        if self._playing.isActive():
            self._playing.stop()
            try:
                winsound.PlaySound(None, 0)
            except RuntimeError:
                pass
            self.play.setText("Přehrát nahrávku")
