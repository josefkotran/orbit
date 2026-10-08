"""The dictation history window (history.py): the last dictations, newest first, and the chosen one on the right with
what can be done with it: insert it again where the user was (this window goes away first, so Windows brings that
window back), copy it, listen to its recording, transcribe it again, correct it (the correction goes to vocabulary
learning: editing.word_changes) or delete it."""
import time
import winsound
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from . import history
from .theme import style_titlebar
from .ui import _label, _repolish, mic_icon

ID = Qt.UserRole
OUTCOMES = {history.INSERTED: "vloženo", history.CLIPBOARD: "ve schránce", history.FAILED: "přepis selhal"}


def when(at: float) -> str:
    """"14:32" today, "8. 10. 14:32" before."""
    t, now = time.localtime(at), time.localtime()
    clock = f"{t.tm_hour}:{t.tm_min:02d}"
    return clock if t[:3] == now[:3] else f"{t.tm_mday}. {t.tm_mon}. {clock}"


def first_line(text: str, limit: int = 40) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


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
        self._playing = QTimer(self, singleShot=True)  # when the recording that plays ends
        self._playing.timeout.connect(self._played)

        root = QHBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(_label("Historie diktátů", "section"))
        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # first_line() keeps the rows short
        self.list.currentItemChanged.connect(lambda item, _: self._select(item))
        self.list.itemDoubleClicked.connect(lambda _: self._insert())
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
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.insert = QPushButton("Vložit")
        self.insert.setProperty("role", "primary")
        self.insert.setToolTip("Vloží text do okna, které bylo vpředu před otevřením historie. Dvojklik na diktát "
                               "dělá totéž.")
        self.insert.clicked.connect(self._insert)
        self.copy = QPushButton("Kopírovat")
        self.copy.setProperty("role", "ghost")
        self.copy.clicked.connect(lambda: self._emit(self.copy_requested, "Zkopírováno, vlož ho Ctrl+V."))
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
        self.empty = _label("Zatím tu nic není. Každý diktát se sem zapíše, i když skončí ve schránce.", "dim",
                            wrap=True)
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
        self.list.blockSignals(True)
        self.list.clear()
        chosen = None
        for entry in reversed(self.history.items):
            where = entry.app or "?"
            outcome = OUTCOMES.get(entry.outcome, "")
            head = f"{when(entry.at)} · {where}" + (f" · {outcome}" if entry.outcome != history.INSERTED else "")
            if entry.instruction:
                head += " · úprava"
            item = QListWidgetItem(f"{head}\n{first_line(entry.best) or '(bez textu)'}")
            item.setData(ID, entry.id)
            item.setToolTip(entry.best[:500])
            self.list.addItem(item)
            if entry.id == keep:
                chosen = item
        self.list.blockSignals(False)
        has = self.list.count() > 0
        self.detail.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            self.count.setText("")
        elif self.history.persist:
            self.count.setText(f"Jen v tomhle počítači, nejvýš {history.MAX_ITEMS} posledních.")
        else:
            self.count.setText("Historie se neukládá (Nastavení), tady je jen poslední diktát.")
        self.list.setCurrentItem(chosen or self.list.item(0))
        self._select(self.list.currentItem())
        if status:
            self._say(status)

    def _select(self, item: QListWidgetItem | None) -> None:
        self._stop_playing()
        entry = self.history.get(item.data(ID)) if item else None
        self._current = entry
        if entry is None:
            return
        parts = [when(entry.at)]
        if entry.app:
            parts.append(entry.app)
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
        self.text.blockSignals(True)
        self.text.setPlainText(entry.best)
        self.text.blockSignals(False)
        has_audio = bool(entry.recording) and self._wav(entry).is_file()
        self.play.setVisible(has_audio)
        self.again.setVisible(has_audio)
        self.play.setText("Přehrát nahrávku")
        self._text_changed()
        self.status.setText("")

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
