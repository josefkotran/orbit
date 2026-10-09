"""The windows behind the + above the panel (favorites.py): "Vybrat složky a barvy…" (which folders the + offers: the
favourites and the folders Claude Code has run in, each with a switch and its colour dot, and any other folder) and
"Nové repo…" (a new folder, git init in it; Orbit then adds it to the favourites and opens a session in it)."""
import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLineEdit, QMenu, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)

from . import colors, favorites, theme
from .theme import style_titlebar
from .ui import _field, _label, _OptionRow, color_icon, fill_color_menu, mic_icon, scrolling


def _button(text: str, role: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("role", role)
    button.setAutoDefault(False)
    button.setCursor(Qt.PointingHandCursor)
    return button


class FavoritesDialog(QDialog):
    saved = Signal(list)  # the folders the + offers now
    # a folder's dot was clicked and a colour chosen ("" = automatic): it applies at once, like in the panel
    color_chosen = Signal(str, str)

    def __init__(self, chosen: list[str], known: list[str], folder_colors: dict):
        """chosen: the favourites now; known: the folders Claude Code has run in (agent.project_folders)."""
        super().__init__(None, Qt.Window)
        self.setObjectName("favorites")
        self.setWindowTitle("Oblíbené složky – Orbit")
        self.setWindowIcon(mic_icon("idle"))
        self.resize(560, 620)
        self._colors = dict(folder_colors)
        self._rows: list[tuple[str, _OptionRow]] = []
        self._dots: list[tuple[str, QToolButton]] = []
        self._color_menu: QMenu | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(10)
        root.addWidget(_label("Oblíbené složky", "section"))
        root.addWidget(_label("Zapnuté složky nabídne plusko nad panelem. Klikneš na složku a otevře se v ní nová "
                              "relace Claude Code. Na barevnou tečku klikni a vybereš složce barvu (v panelu, pod "
                              "pluskem i u jejích relací).", "dim", wrap=True))
        body = QWidget()
        self._list = QVBoxLayout(body)
        self._list.setContentsMargins(0, 4, 8, 4)
        self._list.setSpacing(0)
        others = [f for f in favorites.ordered(known) if not favorites.contains(chosen, f)]
        self._mine = QVBoxLayout()  # the favourites (and folders added here) come first
        self._mine.setSpacing(0)
        self._list.addLayout(self._mine)
        for folder in favorites.ordered(chosen):
            self._add_row(folder, True, self._mine)
        if others:
            heading = _label("Další složky, ve kterých běžel Claude Code", "step")
            heading.setContentsMargins(0, 14, 0, 4)
            self._list.addWidget(heading)
            for folder in others:
                self._add_row(folder, False, self._list)
        self._empty = _label("Zatím tu žádná složka není. Přidej ji tlačítkem „Přidat složku…“ dole.", "dim",
                             wrap=True)
        self._empty.setVisible(not self._rows)
        self._list.addWidget(self._empty)
        self._list.addStretch(1)
        root.addWidget(scrolling(body), 1)
        self.status = _label("", "warn", wrap=True)
        self.status.hide()
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        add = _button("Přidat složku…", "small")
        add.setToolTip("Kterákoli místní složka, i taková, ve které Claude Code ještě neběžel.")
        add.clicked.connect(self._pick)
        buttons.addWidget(add)
        buttons.addStretch(1)
        cancel = _button("Zrušit", "ghost")
        cancel.clicked.connect(self.reject)
        save = _button("Uložit", "primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self)

    def _add_row(self, folder: str, on: bool, layout: QVBoxLayout, at: int = -1) -> _OptionRow:
        missing = not os.path.isdir(folder)
        row = _OptionRow(Path(folder).name or folder, folder + (" (složka teď neexistuje)" if missing else ""), on)
        dot = QToolButton()
        dot.setObjectName("folderDot")
        dot.setIcon(self._dot(folder))
        dot.setIconSize(QSize(16, 16))
        dot.setCursor(Qt.PointingHandCursor)
        dot.setToolTip("Barva složky: klikni a vyber jinou")
        dot.setStyleSheet(f"QToolButton#folderDot {{ border: none; background: transparent; padding: 4px; "
                          f"border-radius: 12px; }} QToolButton#folderDot:hover {{ background: "
                          f"{theme.tint('#24365A').name()}; }}")
        dot.clicked.connect(lambda _=False, f=folder, d=dot: self._pick_color(f, d))
        self._dots.append((folder, dot))
        row.layout().insertWidget(0, dot, 0, Qt.AlignVCenter)
        row.layout().setSpacing(8)
        if at >= 0:
            layout.insertWidget(at, row)
        else:
            layout.addWidget(row)
        self._rows.append((folder, row))
        return row

    def _dot(self, folder: str):
        return color_icon(colors.accent(colors.color_for(folder, self._colors)))

    def _pick_color(self, folder: str, dot: QToolButton):
        menu = self._color_menu = QMenu(self)
        fill_color_menu(menu, folder, self._colors, lambda color: self.color_chosen.emit(folder, color or ""))
        menu.popup(dot.mapToGlobal(dot.rect().bottomLeft()))

    def set_colors(self, folder_colors: dict):
        """The folder colours now (after a choice here or elsewhere): every dot, the automatic ones may move too."""
        self._colors = dict(folder_colors)
        for folder, dot in self._dots:
            dot.setIcon(self._dot(folder))

    def _pick(self):
        start = next((f for f, row in self._rows if row.isChecked()), "") or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Vyber složku", str(Path(start).parent))
        if not folder:
            return
        folder = os.path.normpath(folder)
        if folder.startswith(("\\\\", "//")):
            self.status.setText("Složka na síťovém disku (\\\\server\\…) nejde, relaci otevřu jen v místní složce.")
            self.status.show()
            return
        self.status.hide()
        self.include(folder)

    def include(self, folder: str):
        """folder switched on: its row, or a new one at the top."""
        row = next((row for f, row in self._rows if favorites.contains([f], folder)), None)
        if row is None:
            row = self._add_row(folder, True, self._mine, 0)
        row.setChecked(True)
        self._empty.hide()

    def folders(self) -> list[str]:
        return favorites.clean([f for f, row in self._rows if row.isChecked()])

    def _save(self):
        self.saved.emit(self.folders())
        self.accept()


class NewRepoDialog(QDialog):
    created = Signal(str, str)  # the new folder, what went wrong with git ("" = nothing)

    def __init__(self, parent_folder: str):
        super().__init__(None, Qt.Window)
        self.setObjectName("favorites")
        self.setWindowTitle("Nové repo – Orbit")
        self.setWindowIcon(mic_icon("idle"))
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)
        root.addWidget(_label("Nové repo", "section"))
        root.addWidget(_label("Založí složku, přidá ji pod plusko a otevře v ní novou relaci Claude Code.", "dim",
                              wrap=True))
        self.name = QLineEdit()
        self.name.setPlaceholderText("třeba ondra")
        self.name.textChanged.connect(self._update)
        root.addLayout(_field("Název složky", self.name))
        where = QWidget()
        row = QHBoxLayout(where)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.parent_edit = QLineEdit(parent_folder)
        self.parent_edit.textChanged.connect(self._update)
        row.addWidget(self.parent_edit, 1)
        browse = _button("Změnit…", "small")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        root.addLayout(_field("Kde", where))
        has_git = bool(favorites.git_exe())
        self.git = _OptionRow("Git repozitář", "Spustí v nové složce git init." if has_git else
                              "Git tu není nainstalovaný, složka bude bez gitu.", has_git)
        self.git.setEnabled(has_git)
        root.addWidget(self.git)
        self.preview = _label("", "dim", wrap=True)
        root.addWidget(self.preview)
        self.error = _label("", "warn", wrap=True)
        self.error.hide()
        root.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        cancel = _button("Zrušit", "ghost")
        cancel.clicked.connect(self.reject)
        self.create = _button("Založit a otevřít", "primary")
        self.create.setDefault(True)
        self.create.clicked.connect(self._create)
        buttons.addWidget(cancel)
        buttons.addWidget(self.create)
        root.addLayout(buttons)
        self._update()

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self)
        self.name.setFocus()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Kde založit nové repo", self.parent_edit.text())
        if folder:
            self.parent_edit.setText(os.path.normpath(folder))

    def _update(self):
        name, parent = self.name.text().strip(), self.parent_edit.text().strip()
        problem = favorites.name_problem(name) if name else ""
        self.preview.setText(f"Vznikne {Path(parent) / name}" if name and parent and not problem else "")
        self.preview.setVisible(bool(self.preview.text()))
        self.error.setText(problem)
        self.error.setVisible(bool(problem))
        self.create.setEnabled(bool(name) and not problem)

    def _create(self):
        if not self.create.isEnabled():
            return
        try:
            path, warning = favorites.create(self.parent_edit.text(), self.name.text(), self.git.isChecked())
        except ValueError as e:
            self.error.setText(str(e))
            self.error.show()
            return
        self.created.emit(path, warning)
        self.accept()
