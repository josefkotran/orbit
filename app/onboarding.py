"""First run: the setup wizard (shown when there is no config.json yet, or again from the tray menu), and the two
helpers it shares with the settings: the Claude connection and the downloads.

Pages: Vítej (name) → Mikrofon a klávesa → Model (download by the graphics card) → Claude (install, log in) →
Co smí Orbit (consents) → Hotovo. The wizard only collects values; main applies them (Dictation._apply_values).
"""
import logging
import threading
import time

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import claude_setup, config, downloads, hotkey, theme
from .theme import style_titlebar
from .ui import ClaudeBox, DownloadRow, KeyAndMic, _field, _label, _OptionRow, _repolish, mic_icon, scrolling

log = logging.getLogger(__name__)

CANCELLED = "zrušeno"


class ClaudeConnection(QObject):
    """Is Claude Code here and logged in (claude_setup.status in a worker thread), and Anthropic's own install and
    login: started in a window the user watches, then checked every 2 s until done or the window is closed."""

    changed = Signal(object)  # claude_setup.Status, after every check
    busy_changed = Signal(str)  # "", "installing", "login"
    _checked = Signal(object)
    POLL_MS = 2000
    RECHECK_MS = 5 * 60_000  # not connected: look again now and then (installed or logged in from a terminal)
    # The check failed or claude.exe was missing before it ever worked in this run (a slow start of Windows, Claude
    # Code updating itself): soon again, not only in 5 minutes with sessions, limits and the agent off till then
    QUICK_RECHECK_MS = (15_000, 30_000, 60_000)

    def __init__(self):
        super().__init__()
        self.status: claude_setup.Status | None = None
        self.busy = ""
        self.message = ""  # how the last install or login ended when it didn't work
        self._proc = None
        self._inflight = False
        self._quick = 0  # quick rechecks used (QUICK_RECHECK_MS)
        self._checked.connect(self._on_checked)
        self._poll = QTimer(self, interval=self.POLL_MS)
        self._poll.timeout.connect(self.refresh)
        self._recheck = QTimer(self, interval=self.RECHECK_MS)
        self._recheck.timeout.connect(self.refresh)

    @property
    def connected(self) -> bool | None:
        """None until the first check is done."""
        return None if self.status is None else self.status.connected

    def refresh(self) -> None:
        if self._inflight:
            return
        self._inflight = True
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self) -> None:
        try:
            s = claude_setup.status()
        except Exception as e:
            log.exception("Zjištění stavu Claude Code selhalo")
            s = claude_setup.Status(installed=True, error=str(e))
        self._checked.emit(s)

    def _on_checked(self, s: claude_setup.Status) -> None:
        self._inflight = False
        before = self.status
        if s.error and before is not None and before.connected:
            s = before  # a hiccup (Claude Code updating itself): keep what worked a moment ago
        self.status = s
        if self.busy:
            done = s.installed if self.busy == "installing" else s.logged_in
            ended = self._proc is None or self._proc.poll() is not None
            if done or ended:
                if not done:
                    self.message = ("Okno instalace se zavřelo a Claude Code pořád nevidím. Zkus to znovu, nebo "
                                    f"postupuj podle {claude_setup.SETUP_DOCS}." if self.busy == "installing" else
                                    "Přihlášení se nedokončilo. Zkus to znovu.")
                self._proc = None
                self._set_busy("")
        if s.connected:
            self._recheck.stop()
            self._quick = len(self.QUICK_RECHECK_MS)  # it worked once: a later hiccup keeps that state (above)
        elif (s.error or not s.installed) and self._quick < len(self.QUICK_RECHECK_MS):
            self._recheck.start(self.QUICK_RECHECK_MS[self._quick])
            self._quick += 1
        elif not self._recheck.isActive() or self._recheck.interval() != self.RECHECK_MS:
            self._recheck.start(self.RECHECK_MS)
        if before is None or (before.installed, before.logged_in, before.method) != (s.installed, s.logged_in,
                                                                                     s.method):
            log.info("Claude Code: %s", "nenainstalovaný" if not s.installed else
                     f"{s.version or '?'}, přihlášený ({s.method}, {s.plan or '-'})" if s.logged_in else
                     f"{s.version or '?'}, nepřihlášený" + (f" ({s.error})" if s.error else ""))
        self.changed.emit(s)

    def _set_busy(self, busy: str) -> None:
        self.busy = busy
        if busy:
            self._poll.start()
        else:
            self._poll.stop()
        self.busy_changed.emit(busy)

    def install(self) -> None:
        self._launch("installing", claude_setup.install)

    def login(self) -> None:
        self._launch("login", lambda: claude_setup.login(self.status.exe if self.status else None))

    def _launch(self, busy: str, start) -> None:
        if self.busy:
            return
        self.message = ""
        try:
            self._proc = start()
        except OSError as e:
            log.exception("Claude Code: %s nejde spustit", busy)
            self.message = f"Nejde to spustit: {e}"
            self.changed.emit(self.status)
            return
        self._set_busy(busy)


class Downloads(QObject):
    """Downloads of models and voices (downloads.ITEMS keys), each in its own worker thread, going on while the
    windows that started them are long closed."""

    progress = Signal(str, object, object)  # key, bytes done, bytes in all (more than a 32-bit int)
    finished = Signal(str, str)  # key, error ("" = it's here, CANCELLED = the user stopped it)
    _step = Signal(str, object, object)
    _end = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._jobs: dict[str, dict] = {}  # key -> cancel event, done, total
        self._errors: dict[str, str] = {}
        self._step.connect(self._on_step)
        self._end.connect(self._on_end)

    def running(self, key: str | None) -> bool:
        return key in self._jobs

    def any_running(self) -> bool:
        return bool(self._jobs)

    def state(self, key: str) -> tuple[str, int, int, str]:
        """("present" | "running" | "failed" | "missing", bytes done, bytes in all, error)."""
        item = downloads.ITEMS[key]
        if job := self._jobs.get(key):
            return "running", job["done"], job["total"], ""
        if item.present():
            return "present", item.size, item.size, ""
        if key in self._errors:
            return "failed", 0, item.size, self._errors[key]
        return "missing", 0, item.size, ""

    def percent(self, key: str) -> int:
        _, done, total, _ = self.state(key)
        return int(100 * done / total) if total else 0

    def start(self, key: str | None) -> None:
        if key not in downloads.ITEMS or key in self._jobs or downloads.ITEMS[key].present():
            return
        cancel = threading.Event()
        self._jobs[key] = {"cancel": cancel, "done": 0, "total": downloads.ITEMS[key].size}
        self._errors.pop(key, None)
        log.info("Stahuji %s", key)
        threading.Thread(target=self._run, args=(key, cancel), daemon=True).start()
        self.progress.emit(key, 0, downloads.ITEMS[key].size)

    def cancel(self, key: str | None) -> None:
        if job := self._jobs.get(key):
            job["cancel"].set()

    def cancel_all(self) -> None:
        for job in self._jobs.values():
            job["cancel"].set()

    def _run(self, key: str, cancel: threading.Event) -> None:
        last = 0.0

        def step(done, total):
            nonlocal last
            if time.monotonic() - last >= 0.25 or done >= total:
                last = time.monotonic()
                self._step.emit(key, done, total)

        try:
            downloads.download(key, step, cancel)
            error = ""
        except downloads.Cancelled:
            error = CANCELLED
        except downloads.DownloadError as e:
            error = str(e)
        except Exception as e:
            log.exception("Stahování %s selhalo", key)
            error = f"Stahování se nepovedlo: {e}"
        self._end.emit(key, error)

    def _on_step(self, key: str, done, total) -> None:
        if job := self._jobs.get(key):
            job["done"], job["total"] = done, total
            self.progress.emit(key, done, total)

    def _on_end(self, key: str, error: str) -> None:
        self._jobs.pop(key, None)
        if error and error != CANCELLED:
            self._errors[key] = error
            log.warning("Stahování %s: %s", key, error)
        self.finished.emit(key, error)


# --- the wizard ------------------------------------------------------------------------------------

class _Steps(QWidget):
    """Thin segments at the top, one per page, lit up to the current one."""

    def __init__(self, count: int):
        super().__init__()
        self._count, self._current = count, 0
        self.setFixedHeight(4)

    def set_current(self, index: int) -> None:
        self._current = index
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        gap = 6
        w = (self.width() - gap * (self._count - 1)) / self._count
        p.setPen(Qt.NoPen)
        for i in range(self._count):
            p.setBrush(QColor(theme.ACCENT) if i <= self._current else QColor(theme.LINE))
            p.drawRoundedRect(QRectF(i * (w + gap), 0, w, self.height()), 2, 2)


class _ModelCard(QFrame):
    """One Whisper model to choose: what it is, its size, and its download (which goes on in the background)."""

    clicked = Signal(str)

    def __init__(self, key: str, title: str, text: str, recommended: bool, manager):
        super().__init__()
        self.key = key
        self.setProperty("role", "card")
        self.setCursor(Qt.PointingHandCursor)
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(10)
        name = _label(title, "section")
        head.addWidget(name)
        if recommended:
            badge = QLabel("doporučeno")
            badge.setStyleSheet(f"color: {theme.ON_ACCENT}; background: {theme.ACCENT}; border-radius: 8px; "
                                "padding: 1px 8px; font-size: 11px; font-weight: 600;")
            head.addWidget(badge, 0, Qt.AlignVCenter)
        head.addStretch(1)
        box.addLayout(head)
        box.addWidget(_label(text, "dim", wrap=True))
        self.download = DownloadRow(manager, key)
        box.addWidget(self.download)

    def set_selected(self, on: bool) -> None:
        _repolish(self, selected=on)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.key)


class Wizard(QDialog):
    """Collects the values; main applies them when it closes (finished or not: what was set so far counts, and
    consents only once the user went on from their page with Další)."""

    capture_requested = Signal()
    mic_changed = Signal(object)
    monitor = Signal(bool)  # the mic page is (not) on screen: its live meter needs the mic open
    model_chosen = Signal(str)  # left the model page: Orbit uses that model from now (and tries it on the last page)
    binding_refused = Signal(object)  # a captured dictation key that can't be used: back to this one
    PAGES =("welcome", "mic", "model", "claude", "consent", "done")
    WIDTH, HEIGHT = 700, 640

    def __init__(self, cfg: dict, mics: list[str], handsfree_mics: set, level_source, claude: ClaudeConnection,
                 manager: Downloads, autostart: bool, first_run: bool, start: str = "welcome"):
        super().__init__(None)
        self.setObjectName("wizard")
        self.setWindowTitle("Orbit – průvodce nastavením")
        self.setWindowIcon(mic_icon("idle"))
        self.setMinimumSize(620, 520)
        self.resize(self.WIDTH, self.HEIGHT)
        self._cfg, self._claude, self._manager = cfg, claude, manager
        self._mics, self._handsfree, self._level_source = mics, handsfree_mics, level_source
        self._autostart, self._first_run = autostart, first_run
        self._visited: set[str] = set()
        self._consented = False  # left the consent page with Další: closing the window there is no yes
        self._was_connected: bool | None = None
        self._advice = advice = downloads.advise()
        self._model = cfg["model"]
        if first_run:  # the advice, unless a model is here already (a copied data folder)
            here = [m for m in (advice.model, cfg["model"], *downloads.WHISPER_MODELS) if config.model_present(m)]
            self._model = here[0] if here else advice.model

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 22)
        root.setSpacing(14)
        self._step = _label("", "step")
        root.addWidget(self._step)
        self._steps = _Steps(len(self.PAGES))
        root.addWidget(self._steps)
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)
        for build in (self._page_welcome, self._page_mic, self._page_model, self._page_claude, self._page_consent,
                      self._page_done):
            self._stack.addWidget(scrolling(build()))

        footer = QHBoxLayout()
        self._back = QPushButton("Zpět")
        self._back.setProperty("role", "ghost")
        self._back.setAutoDefault(False)
        self._back.clicked.connect(lambda: self._go(self._stack.currentIndex() - 1))
        self._next = QPushButton("Další")
        self._next.setProperty("role", "primary")
        self._next.setDefault(True)
        self._next.clicked.connect(self._forward)
        footer.addWidget(self._back)
        footer.addStretch(1)
        footer.addWidget(self._next)
        root.addLayout(footer)

        claude.changed.connect(self._claude_changed)
        manager.finished.connect(self._show_model_state)  # a bound method: dropped when the wizard is deleted
        self._claude_changed()
        self._go(self.PAGES.index(start) if start in self.PAGES else 0)

    # -- pages --------------------------------------------------------------------------------

    @staticmethod
    def _page(title: str, lead: str | None = None) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 4, 8, 4)
        box.setSpacing(12)
        box.addWidget(_label(title, "hero"))
        if lead:
            box.addWidget(_label(lead, "dim", wrap=True))
        return page, box

    def _page_welcome(self) -> QWidget:
        page, box = self._page("Vítej v Orbitu", "Orbit přepisuje, co řekneš, do jakékoli aplikace: podržíš "
                               "klávesu, mluvíš, pustíš a text je tam, kde máš kurzor. Řeč se rozpoznává přímo na tvém "
                               "počítači, zvuk nikam neodchází.")
        box.addSpacing(6)
        self.name = QLineEdit(self._cfg["name"])
        self.name.setMaxLength(config.NAME_MAX)
        self.name.setPlaceholderText("např. Jana")
        box.addLayout(_field("Jak ti mám říkat?", self.name, "Stačí křestní jméno. Hlasový agent tě tak bude znát "
                             "a podepíše jím zprávy, které za tebe pošle."))
        self.about = QLineEdit(self._cfg["about"])
        self.about.setMaxLength(config.ABOUT_MAX)
        self.about.setPlaceholderText("např. pracuju v e-shopu s textilem")
        box.addLayout(_field("O mně (nepovinné)", self.about, "Jedna věta, čím se zabýváš. Claude podle ní líp "
                             "doplní slovník, třeba o názvy firem a odborné výrazy."))
        box.addStretch(1)
        box.addWidget(_label("Průvodce zabere pár minut. Všechno půjde později změnit v nastavení.", "dim", wrap=True))
        return page

    def _page_mic(self) -> QWidget:
        page, box = self._page("Mikrofon a klávesa", "Vyber klávesu nebo tlačítko myši, které budeš při mluvení "
                               "držet. Až ho pustíš, text se vloží tam, kde máš kurzor.")
        self.keymic = KeyAndMic(self._cfg["ptt"], self._cfg["mic"], self._mics, self._level_source,
                                self._handsfree, stacked=True)
        self.keymic.capture_requested.connect(self.capture_requested)
        self.keymic.mic_changed.connect(self.mic_changed)
        box.addWidget(self.keymic)
        box.addStretch(1)
        return page

    def _page_model(self) -> QWidget:
        page, box = self._page("Rozpoznávání řeči")
        gpu = _label(self._advice.text, "warn" if self._advice.slow else "dim", wrap=True)
        box.addWidget(gpu)
        texts = {"ggml-large-v3.bin": ("large-v3", "Nejpřesnější. Chce grafiku aspoň se 6 GB paměti."),
                 "ggml-large-v3-turbo.bin": ("large-v3-turbo", "Dvakrát rychlejší, o něco víc chyb. Pro slabší "
                                             "grafiku nebo jen procesor.")}
        self._cards = []
        for key in downloads.WHISPER_MODELS:
            title, text = texts[key]
            card = _ModelCard(key, title, f"{text} Stáhne se {downloads.size_text(downloads.ITEMS[key].size)}.",
                              key == self._advice.model, self._manager)
            card.clicked.connect(self._choose_model)
            card.download.changed.connect(self._show_model_state)
            box.addWidget(card)
            self._cards.append(card)
        self._choose_model(self._model)
        box.addWidget(_label("Model se stahuje z Hugging Face (ggerganov/whisper.cpp) a ověří se. Klidně pokračuj, "
                             "stahování poběží dál a Orbit začne model používat, jakmile bude hotový.", "dim",
                             wrap=True))
        box.addStretch(1)
        return page

    def _page_claude(self) -> QWidget:
        page, box = self._page("Claude", "S předplatným Claude (Pro nebo Max) toho Orbit umí víc. Stačí mít Claude "
                               "Code, oficiální program od Anthropicu, a být v něm přihlášený:")
        bullets = QVBoxLayout()
        bullets.setSpacing(4)
        for line in ("Limity předplatného nad tlačítkem (5 hodin, týden)",
                     "Přehled relací Claude Code: co dělají a kdy čekají na tebe",
                     "Hlasový agent, kterému řekneš, co má kterým relacím napsat",
                     "Předčítání souhrnů artefaktů, které relace zveřejní",
                     "Slovník, který se sám učí z tvých diktátů"):
            bullets.addWidget(_label(f"•  {line}", "bullet", wrap=True))
        box.addLayout(bullets)
        box.addSpacing(10)
        box.addWidget(ClaudeBox(self._claude))
        box.addStretch(1)
        self._no_claude = _label("Nemáš Claude? Klikni na Teď ne, diktování funguje i bez něj.", "dim", wrap=True)
        box.addWidget(self._no_claude)
        return page

    def _page_consent(self) -> QWidget:
        page, box = self._page("Co smí Orbit", "Zapni si, co chceš. Nic z toho není nutné a všechno půjde změnit "
                               "v nastavení.")
        cfg, hooks = self._cfg, self._cfg["claude_hooks"]
        agent_key = hotkey.in_sentence(hotkey.binding_name(cfg["agent_ptt"]))
        # what each switch proposes once Claude is connected: what's set now, and where nothing was agreed to yet
        # (hooks never allowed: a first run, or Claude connected only later) the overview, which sends nothing anywhere
        self.sessions = _OptionRow("Přehled relací Claude Code", "Přidá do nastavení Claude Code hooky Orbitu: "
                                   "pozná z nich, co která relace dělá a kdy čeká na tebe.", False)
        self.limits = _OptionRow("Limity Clauda nad tlačítkem", "Přidá do Claude Code stavový řádek, ze kterého "
                                 "Orbit čte, kolik ti zbývá z 5hodinového a týdenního limitu."
                                 if cfg["usage_source"] == "statusline" else "Kolik ti zbývá z 5hodinového a "
                                 "týdenního limitu.", False)
        self.learn = _OptionRow("Učit se slovník z diktátů", "Po 10 diktátech pošle jejich text (ne zvuk) Claudovi "
                                "a ten doplní slovník. Čerpá z tvých limitů.", False)
        self.artifacts = _OptionRow("Předčítat souhrny artefaktů", "Když relace zveřejní artefakt, Claude ho shrne "
                                    "do 7 vět a Orbit je přečte. Taky přes hooky, čerpá z tvých limitů.", False)
        self.agent = _OptionRow("Hlasový agent", f"Zabere {agent_key}: podržíš ho a mluvíš o relacích, agent jim "
                                "umí psát (vždy se nejdřív zeptá).", False)
        self._proposed = {
            self.sessions: cfg["show_sessions"] if hooks else True,
            self.limits: cfg["show_usage"],
            self.learn: cfg["learn_vocabulary"],
            self.artifacts: cfg["read_artifacts"] and hooks,
            self.agent: cfg["agent"],
        }
        for row in self._proposed:
            box.addWidget(row)
        self._agent_clash = _label("Agent by měl stejné tlačítko jako diktování, tak zůstane vypnutý. Změň klávesu "
                                   "pro diktování (krok 2) nebo tlačítko agenta v nastavení.", "warn", wrap=True)
        self._agent_clash.hide()
        box.addWidget(self._agent_clash)
        self.agent.toggle.toggled.connect(lambda _: self._show_clash())
        self.autostart = _OptionRow("Spouštět s Windows", "Orbit naběhne sám po přihlášení do Windows.",
                                    True if self._first_run else self._autostart)
        box.addWidget(self.autostart)
        self._consent_note = _label("Možnosti s Claudem zapneš, až ho připojíš (v předchozím kroku, nebo později "
                                    "v nastavení).", "warn", wrap=True)
        box.addWidget(self._consent_note)
        box.addStretch(1)
        return page

    def _page_done(self) -> QWidget:
        page, box = self._page("Hotovo")
        self._howto = _label("", "bullet", wrap=True)
        box.addWidget(self._howto)
        box.addSpacing(4)
        self._model_state = _label("", "dim", wrap=True)
        box.addWidget(self._model_state)
        self._done_download = DownloadRow(self._manager, self._model, present="")
        box.addWidget(self._done_download)
        self._try = QPlainTextEdit()
        self._try.setPlaceholderText("Klikni sem, drž klávesu a řekni něco…")
        self._try.setFixedHeight(76)
        box.addWidget(self._try)
        box.addStretch(1)
        return page

    # -- what's on them -------------------------------------------------------------------------

    def _choose_model(self, key: str) -> None:
        self._model = key
        for card in self._cards:
            card.set_selected(card.key == key)

    def _connected(self) -> bool:
        return self._claude.connected is True

    def _claude_changed(self, *_) -> None:
        """The Claude switches work only with Claude connected; the Claude page's button says Teď ne until then."""
        connected = self._connected()
        if connected != self._was_connected:  # not on every check: the user's choice stays
            self._was_connected = connected
            for row, proposed in self._proposed.items():
                row.setEnabled(connected)
                row.setChecked(proposed and connected)
        self._consent_note.setVisible(not connected)
        self._no_claude.setVisible(not connected)
        self._update_buttons()

    def _show_model_state(self, *_) -> None:
        if not hasattr(self, "_model_state"):
            return
        present = config.model_present(self._model)
        running = self._manager.running(self._model)
        self._model_state.setText(
            "Model je připravený. Vyzkoušej si to:" if present else
            "Model se ještě stahuje. Diktovat půjde, až bude hotový, dám ti vědět." if running else
            "Model pro rozpoznávání řeči není stažený, bez něj Orbit nepřepisuje. Stáhni ho tady nebo v nastavení.")
        _repolish(self._model_state, role="dim" if present or running else "warn")
        self._done_download.set_key(self._model)
        self._try.setVisible(present)

    def _show_howto(self) -> None:
        key = hotkey.in_sentence(hotkey.binding_name(self.keymic.binding))
        lines = [f"•  Drž {key} a mluv. Až pustíš, text se vloží tam, kde máš kurzor.",
                 "•  Totéž umí plovoucí tlačítko s mikrofonem: drž ho a mluv. Přetažením ho přesuneš, pravým "
                 "tlačítkem otevřeš menu.",
                 "•  Ikona Orbitu u hodin: klik otevře nastavení. V menu najdeš i tenhle průvodce."]
        if self._connected() and self.agent.isChecked():
            lines.append(f"•  {hotkey.binding_name(self._cfg['agent_ptt'])}: drž a mluv s agentem o relacích.")
        self._howto.setText("\n\n".join(lines))

    # -- moving around ----------------------------------------------------------------------------

    def _go(self, index: int) -> None:
        index = max(0, min(index, len(self.PAGES) - 1))
        name = self.PAGES[index]
        self._visited.add(name)
        self._stack.setCurrentIndex(index)
        self._steps.set_current(index)
        self._step.setText(f"KROK {index + 1} Z {len(self.PAGES)}")
        self.monitor.emit(name == "mic")
        if name == "done":
            self._show_howto()
            self._show_model_state()
        self._update_buttons()

    def _update_buttons(self) -> None:
        name = self.PAGES[self._stack.currentIndex()]
        self._back.setVisible(self._stack.currentIndex() > 0)
        self._next.setText("Začít" if name == "done" else
                           "Teď ne" if name == "claude" and not self._connected() else "Další")

    def _forward(self) -> None:
        name = self.PAGES[self._stack.currentIndex()]
        if name == "model":
            if not config.model_present(self._model):
                self._manager.start(self._model)  # nothing works without it: no extra click needed
            self.model_chosen.emit(self._model)
        if name == "consent":
            self._consented = True
        if name == "done":
            self.accept()
        else:
            self._go(self._stack.currentIndex() + 1)

    def _clash(self) -> bool:
        """The agent would be on with the dictation's key (it takes its button over system-wide)."""
        return self._connected() and self.agent.isChecked() and self.keymic.binding == self._cfg["agent_ptt"]

    def _show_clash(self) -> None:
        self._agent_clash.setVisible(self._clash())

    def on_captured(self, binding) -> None:
        refused = ""
        if binding and binding == self._cfg["agent_ptt"] and self._connected() and self.agent.isChecked():
            refused = "Tohle tlačítko má hlasový agent. Vyber jiné."
            self.binding_refused.emit(self.keymic.binding)
        self.keymic.on_captured(binding, refused)
        self._show_clash()

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self)
        screen = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        if self.frameGeometry().height() > screen.height() - 20:  # a small laptop screen: the pages scroll
            self.resize(self.width(), screen.height() - 60)
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.left(), max(screen.top() + 8, frame.top()))

    def values(self) -> dict:
        """What to apply: everything from the pages; the consents (and autostart) only once their page was left with
        Další (closing the window there says no to all of them)."""
        values = {"name": config.clean_name(self.name.text()), "about": config.clean_about(self.about.text()),
                  "ptt": self.keymic.binding, "mic": self.keymic.mic_choice()}
        if "model" in self._visited:  # (a model that isn't here gets downloaded: only once its size was shown)
            values["model"] = self._model
        if self._consented:
            values["autostart"] = self.autostart.isChecked()
            if self._connected():
                sessions_on, artifacts_on, limits_on = (self.sessions.isChecked(), self.artifacts.isChecked(),
                                                        self.limits.isChecked())
                values.update(show_sessions=sessions_on, read_artifacts=artifacts_on,
                              claude_hooks=sessions_on or artifacts_on, show_usage=limits_on,
                              learn_vocabulary=self.learn.isChecked(), agent=self.agent.isChecked() and not self._clash())
                if self._cfg["usage_source"] == "statusline":  # the OAuth source (an older config.json) needs none
                    values["claude_statusline"] = limits_on
        return values
