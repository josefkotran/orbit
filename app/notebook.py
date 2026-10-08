"""Orbit's notebook: the user's own tasks (tasks.py) in four sections, Aktivní, V plánu, Poznámky and Hotovo, and the
chosen one on the right: its title, folder, context and notes added over time. Every change is saved straight away.
A task moves by dragging it (also to another section), with the arrows, or with the section buttons. Orbit offers the
active ones every half hour (main.Dictation._check_tasks); "Začít teď" asks right away."""
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import colors, tasks
from .theme import style_titlebar
from .ui import _combo, _label, _repolish

ID = Qt.UserRole  # a row's task id, or a section's status


class _Tree(QTreeWidget):
    """The sections and their tasks; a drag moves a task (within a section or to another one), nothing else."""
    moved = Signal()

    def dropEvent(self, event):
        super().dropEvent(event)
        QTimer.singleShot(0, self.moved.emit)  # rebuilt once the drag is over (it still holds the rows)


class Notebook(QDialog):
    changed = Signal()  # the tasks changed (and are saved): Orbit's badge
    start_requested = Signal(str)  # "Začít teď": the task's id

    def __init__(self, items: list[tasks.Task], folders: list[str], folder_colors: dict, next_check):
        """items: Orbit's own list (changed in place); next_check(): when Orbit looks at the active ones next."""
        super().__init__(None, Qt.Window)
        self.setObjectName("notebook")
        self.setWindowTitle("Poznámky – Orbit")
        self.tasks, self._folders, self._folder_colors, self._next_check = items, folders, folder_colors, next_check
        self._current: tasks.Task | None = None
        self._loading = False
        self._save_timer = QTimer(self, singleShot=True, interval=500)  # typing: saved half a second after
        self._save_timer.timeout.connect(self._save)

        root = QHBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(_label("Poznámky", "section"))
        head.addStretch(1)
        add = QPushButton("+ Nový úkol")
        add.setProperty("role", "primary")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._add)
        head.addWidget(add)
        left.addLayout(head)
        self.tree = _Tree()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(0)  # the sections are told by their bold grey titles
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)  # the title takes what the folder leaves
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.invisibleRootItem().setFlags(Qt.ItemIsEnabled)  # tasks only go into a section
        self.tree.moved.connect(self._dropped)
        self.tree.currentItemChanged.connect(lambda item, _: self._select(item))
        left.addWidget(self.tree, 1)
        arrows = QHBoxLayout()
        arrows.setSpacing(6)
        for text, step, tip in (("↑", -1, "Výš (dřív na řadě)"), ("↓", 1, "Níž")):
            button = QPushButton(text)
            button.setProperty("role", "small")
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, s=step: self._shift(s))
            arrows.addWidget(button)
        arrows.addStretch(1)
        left.addLayout(arrows)
        self.check_note = _label("", "dim", wrap=True)
        left.addWidget(self.check_note)
        holder = QWidget()
        holder.setLayout(left)
        holder.setFixedWidth(340)
        root.addWidget(holder)

        self.editor = QWidget()
        right = QVBoxLayout(self.editor)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Název úkolu")
        self.title.textEdited.connect(self._edited)
        title_font = QFont(self.title.font())
        title_font.setPixelSize(16)
        self.title.setFont(title_font)
        right.addWidget(self.title)
        self.status_buttons: dict[str, QPushButton] = {}
        statuses = QHBoxLayout()
        statuses.setSpacing(6)
        for status, label in tasks.STATUSES.items():
            button = QPushButton(label)
            button.setProperty("role", "small")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, s=status: self._move_to(s))
            statuses.addWidget(button)
            self.status_buttons[status] = button
        statuses.addStretch(1)
        right.addLayout(statuses)
        right.addWidget(_label("Složka (tam se otevře relace)"))
        self.folder = _combo()
        self.folder.addItem("Vyber složku…", "")
        for f in folders:
            self.folder.addItem(Path(f).name, f)
            self.folder.setItemData(self.folder.count() - 1, f, Qt.ToolTipRole)
        self.folder.currentIndexChanged.connect(lambda _: self._folder_changed())
        right.addWidget(self.folder)
        right.addWidget(_label("Kontext"))
        self.context = QPlainTextEdit()
        self.context.setPlaceholderText("Co má Claude vědět: o co jde, odkazy, soubory, jak poznat, že je hotovo…")
        self.context.textChanged.connect(self._edited)
        right.addWidget(self.context, 2)
        right.addWidget(_label("Poznámky"))
        self.notes = QListWidget()
        self.notes.setWordWrap(True)
        self.notes.setToolTip("Pravý klik smaže poznámku.")
        self.notes.setContextMenuPolicy(Qt.CustomContextMenu)
        self.notes.customContextMenuRequested.connect(self._note_menu)
        right.addWidget(self.notes, 1)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Přidat poznámku a Enter")
        self.note.returnPressed.connect(self._add_note)
        right.addWidget(self.note)
        self.info = _label("", "dim", wrap=True)
        right.addWidget(self.info)
        bottom = QHBoxLayout()
        self.start = QPushButton("Začít teď")
        self.start.setProperty("role", "ghost")
        self.start.setCursor(Qt.PointingHandCursor)
        self.start.setToolTip("Orbit se tě hned zeptá, jestli pro úkol otevřít novou relaci v jeho složce.")
        self.start.clicked.connect(self._start)
        bottom.addWidget(self.start)
        bottom.addStretch(1)
        delete = QPushButton("Smazat úkol")
        delete.setProperty("role", "small")
        delete.clicked.connect(self._delete)
        bottom.addWidget(delete)
        right.addLayout(bottom)
        root.addWidget(self.editor, 1)

        self.resize(960, 640)
        self.refresh()
        style_titlebar(self)

    # -- the list ----------------------------------------------------------------------------

    def refresh(self, select: str | None = None) -> None:
        """Rebuilds the sections from the tasks (Orbit changed one: started, turned down)."""
        select = select or (self._current.id if self._current else None)
        self._loading = True
        self.tree.clear()
        selected = None
        for status, label in tasks.STATUSES.items():
            mine = [t for t in self.tasks if t.status == status]
            section = QTreeWidgetItem([f"{label}  {len(mine)}", ""])
            section.setData(0, ID, status)
            section.setFlags(Qt.ItemIsEnabled | Qt.ItemIsDropEnabled)
            font = QFont(self.tree.font())
            font.setBold(True)
            section.setFont(0, font)
            section.setForeground(0, QColor("#8B96AD"))
            self.tree.addTopLevelItem(section)
            for t in mine:
                item = QTreeWidgetItem([t.title or "Bez názvu", Path(t.folder).name if t.folder else ""])
                item.setData(0, ID, t.id)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
                if t.folder:
                    color = colors.color_for(t.folder, self._folder_colors)
                    item.setForeground(1, QColor(colors.accent(color)))
                if t.started:
                    item.setToolTip(0, f"Relace založená {tasks.when(t.started)}")
                section.addChild(item)
                if t.id == select:
                    selected = item
            section.setExpanded(status != "done" or (selected is not None and selected.parent() is section))
        self._loading = False
        if selected:
            self.tree.setCurrentItem(selected)
        else:
            self._select(None)
        nxt = self._next_check()
        self.check_note.setText("Aktivní úkoly kontroluju každou půlhodinu" + (f", další kontrola v {nxt}." if nxt
                                                                               else "."))

    def _task(self, task_id) -> tasks.Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def _dropped(self) -> None:
        """A drag ended: the order and sections as the tree shows them now."""
        order = []
        for i in range(self.tree.topLevelItemCount()):
            section = self.tree.topLevelItem(i)
            status = section.data(0, ID)
            for j in range(section.childCount()):
                t = self._task(section.child(j).data(0, ID))
                if t and t not in order:
                    if status == "active" and t.status != "active":
                        t.declined = t.started = 0.0  # moved to the active ones again: may be offered again
                    t.status = status
                    order.append(t)
        order += [t for t in self.tasks if t not in order]  # (never lost, whatever a drag did)
        self.tasks[:] = order
        self._save()
        self.refresh()

    def _shift(self, step: int) -> None:
        t = self._current
        if not t:
            return
        same = [x for x in self.tasks if x.status == t.status]
        i = same.index(t)
        if not 0 <= i + step < len(same):
            return
        other = same[i + step]
        a, b = self.tasks.index(t), self.tasks.index(other)
        self.tasks[a], self.tasks[b] = other, t
        self._save()
        self.refresh(t.id)

    def _move_to(self, status: str) -> None:
        t = self._current
        if not t or t.status == status:
            return
        if status == "active":
            t.declined = t.started = 0.0  # back among the active ones: offered (and started) again
        t.status = status
        self.tasks.remove(t)
        firsts = [i for i, x in enumerate(self.tasks) if x.status == status]
        self.tasks.insert(firsts[-1] + 1 if firsts else len(self.tasks), t)  # at the end of its new section
        self._save()
        self.refresh(t.id)

    def _add(self) -> None:
        t = tasks.new()
        self.tasks.insert(0, t)  # the top of Poznámky
        self._save()
        self.refresh(t.id)
        self.title.setFocus()

    def _delete(self) -> None:
        t = self._current
        if not t:
            return
        box = QMessageBox(QMessageBox.Question, "Orbit", f"Smazat úkol „{t.title or 'Bez názvu'}“?",
                          QMessageBox.Yes | QMessageBox.No, self)
        box.button(QMessageBox.Yes).setText("Smazat")
        box.button(QMessageBox.No).setText("Nechat")
        box.setDefaultButton(QMessageBox.No)
        _repolish(box.button(QMessageBox.No), role="primary")
        style_titlebar(box)
        if box.exec() == QMessageBox.Yes:
            self.tasks.remove(t)
            self._current = None
            self._save()
            self.refresh()

    # -- the chosen task ---------------------------------------------------------------------

    def _select(self, item) -> None:
        t = self._task(item.data(0, ID)) if item is not None else None
        if self._loading:
            return
        self._flush()
        self._current = t
        self._loading = True
        self.editor.setEnabled(t is not None)
        self.title.setText(t.title if t else "")
        self.context.setPlainText(t.context if t else "")
        index = self.folder.findData(t.folder) if t else 0
        if t and t.folder and index < 0:  # a folder that isn't in the list any more
            self.folder.addItem(f"{Path(t.folder).name} (není v seznamu)", t.folder)
            index = self.folder.count() - 1
        self.folder.setCurrentIndex(max(0, index))
        self._show_notes()
        self._show_status()
        self._loading = False

    def _show_notes(self) -> None:
        self.notes.clear()
        for n in (self._current.notes if self._current else []):
            item = QListWidgetItem(f"{tasks.when(n.get('at', 0))}  {n['text']}")
            self.notes.addItem(item)
        self.notes.scrollToBottom()

    def _show_status(self) -> None:
        t = self._current
        for status, button in self.status_buttons.items():
            _repolish(button, selected=bool(t and t.status == status))
        if not t:
            self.info.setText("Vyber úkol vlevo, nebo založ nový.")
        elif t.started:
            self.info.setText(f"Pro tenhle úkol běží relace založená {tasks.when(t.started)}, proto je v Hotovo. "
                              "Když ho přesuneš do Aktivních, Orbit ho nabídne znovu.")
        elif t.status == "active" and not t.folder:
            self.info.setText("Bez složky ho nespustím: vyber, kde má relace pracovat.")
        elif t.status == "active" and t.declined:
            self.info.setText(f"Spuštění bylo odmítnuto ({tasks.when(t.declined)}), samo se už nenabídne. Začni ho "
                              "tlačítkem Začít teď, nebo ho přesuň jinam a zpátky do Aktivních.")
        elif t.status == "active":
            nxt = self._next_check()
            self.info.setText("Při další kontrole" + (f" ({nxt})" if nxt else "") + " se tě zeptám, jestli pro něj "
                              "otevřít novou relaci, pokud bude první na řadě.")
        else:
            self.info.setText("Až ho přesuneš do Aktivních, při kontrole se tě zeptám, jestli ho začít.")
        self.start.setEnabled(bool(t and t.folder))

    def _edited(self) -> None:
        if not self._loading and self._current:
            self._current.title = self.title.text().strip()
            self._current.context = self.context.toPlainText()
            self._save_timer.start()
            item = self.tree.currentItem()
            if item is not None:
                item.setText(0, self._current.title or "Bez názvu")

    def _flush(self) -> None:
        """Typing that waits for its save: saved now (another task is chosen, the window closes)."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save()

    def _folder_changed(self) -> None:
        if not self._loading and self._current:
            self._current.folder = self.folder.currentData() or ""
            self._save()
            self.refresh(self._current.id)

    def _add_note(self) -> None:
        text = self.note.text().strip()
        if not (text and self._current):
            return
        self._current.notes.append({"at": time.time(), "text": text})
        self.note.clear()
        self._save()
        self._show_notes()

    def _note_menu(self, pos) -> None:
        row = self.notes.row(self.notes.itemAt(pos)) if self.notes.itemAt(pos) else -1
        if row < 0 or not self._current:
            return
        menu = QMenu(self)
        menu.addAction("Smazat poznámku", lambda: (self._current.notes.pop(row), self._save(), self._show_notes()))
        menu.exec(self.notes.mapToGlobal(pos))

    def _start(self) -> None:
        if self._current:
            self._flush()
            self.start_requested.emit(self._current.id)

    def _save(self) -> None:
        try:
            tasks.save(self.tasks)
        except OSError as e:
            self.info.setText(f"Úkoly nejde uložit: {e}")
            return
        self.changed.emit()
        if self._current:
            self._show_status()

    def closeEvent(self, event):
        self._flush()
        super().closeEvent(event)
