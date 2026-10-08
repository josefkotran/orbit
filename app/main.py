import faulthandler
import logging
import os
import re
import sys
import threading
import time
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QPoint, QtMsgType, QTimer, QUrl, Signal, qInstallMessageHandler
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import (agent, artifacts, claude_cli, claude_settings, claude_usage, colors, config, downloads, editing,
               history, hotkey, inserter, learning, paths, rewrite, sessions, tasks, theme, vocab, voice, winutil)
from .historyview import HistoryWindow
from .inserter import Inserter
from .notebook import Notebook
from .onboarding import CANCELLED, ClaudeConnection, Downloads, Wizard
from .recorder import Recorder, input_devices, is_bluetooth_handsfree, is_silent
from .ui import (Bubble, FloatingButton, SettingsDialog, color_icon, export_vocabulary, import_vocabulary,
                 message_box, mic_icon)
from .version import VERSION
from .whisper_server import (SAMPLE_RATE, WhisperServer, apply_replacements, apply_voice_commands, build_prompt,
                             clean_text, terminal_command, to_wav)

log = logging.getLogger("orbit")

TAIL_MS = 250  # keep recording a moment after release – people let go while finishing the last word
KEEP_RECORDINGS = 30
LIVE_FALLBACK_MS = 600  # if the mic sends only exact zeros (e.g. muted), start anyway after this
USAGE_REFRESH_MS = 120_000  # the OAuth endpoint (it answers 429 when asked more often)
STATUS_REFRESH_MS = 5_000  # the status line's files (local, cheap)
SESSION_POLL_MS = 1000
NOTIFY_TURN_S = 20  # a finished turn is announced only if Claude worked at least this long (else Pepa watched it)
FORECAST_WARN = timedelta(minutes=60)  # warn when the 5-hour limit runs out sooner than this at the current pace
CONTEXT_CHARS = 150  # the end of the previous piece goes into the prompt; Whisper keeps only ~224 prompt tokens
CLICK_S = 0.35  # the agent's button let go sooner than this = a click: it listens until Pepa stops talking
LISTEN_MAX_MS = 30_000  # hands-free listening ends after this at the latest
CONFIRM_TIMEOUT_MS = 120_000  # a message for a session that Pepa doesn't confirm within this isn't sent
CONFIRM_MAX_CHARS = 500  # longer messages aren't confirmed by voice: the agent has to shorten them
CONFIRM_SEEN_S = 1.0  # a recording started this long after the question showed up in the panel answers it
FEED_KEEP_MS = 90_000  # the agent's part of the panel goes away after this long without anything new
AGENT_IDLE_CHECK_MS = 60_000  # how often a long-idle agent process is ended (agent.VoiceAgent.stop_if_idle)
MAX_RECORDING_S = 300  # a recording ends after this at the latest (a key-up the hook never saw)
WATCH_MS = 1000  # how often a running recording is checked (the key's release, the secure desktop, its length)
SILENT_TELL_S = 1.5  # a recording this long that had nothing in it gets a bubble saying why
REDICTATE_S = 60  # a dictation this soon after "Smaž to", into the same window, probably says the deleted one right
REDICTATE_SIMILAR = 0.5  # ... when it's at least this alike (editing.similar): its differences are corrections


class Take:
    """One push-to-talk recording. With live transcription it arrives in pieces cut at pauses, which are
    transcribed while the user keeps talking; the text is inserted once, after release."""

    def __init__(self, prompt: str, for_agent: bool = False):
        self.prompt = prompt
        self.agent = for_agent  # said to the voice agent, not typed into a window
        self.audio: list[np.ndarray] = []
        self.raw: list[str] = []
        self.texts: list[str] = []
        self.spoken = False  # at least one piece wasn't silence
        self.cancelled = False
        self.error: str | None = None
        self.released_at = 0.0
        self.target = 0  # the window in front when it ended: the text goes there only if it still is
        self.confirm_id: str | None = None  # for the agent: the "Mám to poslat?" already shown when it started
        # Ctrl or Shift held: what's said is an instruction for editing text (editing.py, rewrite.py)
        self.edit = False
        self.rewriter: rewrite.Rewriter | None = None  # its Claude, started while the user talks
        self.selection: str | None = None  # what was selected in the window (None = nothing)
        self.selection_done = False  # ... once that's known (inserter.copy_selection)
        self.probed_at = 0.0  # when the selection was read (a key or click after it: it may not be selected now)
        self.heard = False  # the instruction is transcribed
        self.edit_begun = False  # both are known and the edit is under way (_edit_ready runs it once)
        # what came out of it (_finish_take)
        self.text = ""  # after the replacements and the voice commands
        self.key = ""  # "send" / "stop" after it
        self.command: editing.Command | None = None  # the whole dictation is a command ("Smaž to")
        self.raw_text = ""
        self.seconds = 0.0
        self.stem = ""  # its recording in recordings/ ("" = not kept)

    def drop_rewriter(self) -> None:
        if self.rewriter:
            self.rewriter.cancel()
            self.rewriter = None


class Bridge(QObject):
    """Signals used to hop from hook/worker threads into the Qt main thread."""
    ptt_down = Signal()
    mic_live = Signal()
    piece_ready = Signal()
    ptt_up = Signal()
    captured = Signal(object)
    agent_captured = Signal(object)  # the agent's new button (settings), None = Esc
    server_ready = Signal(int)  # which start (a newer one makes an older one's result moot)
    server_failed = Signal(int, str)
    server_event = Signal(str, str)  # see WhisperServer: backend / restarting / restarted / failed
    dictated = Signal(object)  # a Take that's transcribed: its text, a command, or an instruction for an edit
    transcribe_failed = Signal(str, object)  # message, the Take
    input_seen = Signal()  # the user's own key or click after Orbit typed something (the hook, editing.Trail)
    rewritten = Signal(object, object)  # an edit by Claude is back: the Take, (scope, source, typed, rewrite.Result)
    rewrite_failed = Signal(object, str)  # the Take, the message
    retranscribed = Signal(str, object)  # a history entry transcribed again: its id, {"text", "raw"} or {"error"}
    usage_ready = Signal(object)
    usage_failed = Signal(str)
    learned = Signal(object)
    learn_failed = Signal(str)
    artifact_ready = Signal(object, object)  # artifacts.Published, artifacts.Summary
    artifact_failed = Signal(object, str)
    agent_down = Signal()
    agent_up = Signal()
    speech_over = Signal()  # hands-free listening: Pepa stopped talking
    agent_heard = Signal(str, object)  # text, the confirmation it may answer (Take.confirm_id)
    agent_event = Signal(str, object)  # see agent.VoiceAgent
    task_done = Signal(str, bool, str)  # a task's session: task id, opened, the message (tasks.start_session)


class Dictation:
    def __init__(self):
        first_run = config.is_first_run()
        self.cfg = config.load()
        # config.json couldn't be read, the defaults hold: they mustn't take Orbit's hooks or status line out of
        # Claude Code (the defaults say no to both) until the user saves settings themselves
        self._cfg_doubtful = bool(config.problem)
        if first_run:
            self.cfg["wizard_pending"] = True  # cleared when the wizard closes; a crash before that shows it again
        if "claude_hooks" in config.missing:
            # config.json from before the consents: the hooks this copy already has stay (Pepa's setup)
            self.cfg["claude_hooks"] = claude_settings.hooks_installed()
            log.info("Souhlas s hooky Claude Code převzat ze stávajícího nastavení: %s", self.cfg["claude_hooks"])
        if "usage_source" in config.missing:
            self.cfg["usage_source"] = "oauth"  # config.json from before the status line: its limits stay as they were
        if first_run or config.missing:
            config.save(self.cfg)
        theme.set_theme(self.cfg["theme"])
        theme.apply(QApplication.instance())
        self.server_state = "loading"  # loading / ready / error / nomodel (not downloaded yet)
        self._server_gen = 0
        self.pending = 0
        self.dialog: SettingsDialog | None = None
        self.wizard: Wizard | None = None
        self.claude = ClaudeConnection()  # checked in the background; what needs Claude waits for it
        self._claude_was: bool | None = None
        self.downloads = Downloads()
        self.usage: claude_usage.Usage | None = None
        self.usage_error: str | None = None
        self._usage_inflight = False
        self.take: Take | None = None
        self._retry_take: Take | None = None  # the last dictation whose transcription failed (Přepsat znovu)
        self._recording_since = 0.0
        self._desktop_ok = True  # the user's desktop was the input desktop when the recording started
        self._cpu_told = False  # told once that the transcription runs on the processor
        self._restart_told = False  # told once that Whisper died and comes back
        self._learning = False
        self._learn_retry_at = 0.0
        self.trail = editing.Trail()  # what Orbit typed last: "Smaž to", "Vyber to", edits of the last dictation
        self._watching = False  # the hook reports the user's next key or click (it ends the trail)
        self._edit_pending = 0  # instructions for an edit being transcribed (the button shows a pencil)
        self._rewriting = 0  # edits Claude is working on (the button shows it)
        self.history = history.History(self.cfg["keep_history"])
        self.history_window: HistoryWindow | None = None

        self.bridge = Bridge()
        self.server = WhisperServer(on_event=self.bridge.server_event.emit)
        self.recorder = Recorder(on_live=self.bridge.mic_live.emit, on_piece=self.bridge.piece_ready.emit,
                                 on_end=self.bridge.speech_over.emit)
        self.recorder.may_refresh = self._release_sound_card
        self.recorder.configure(self.cfg["mic"])
        self.recorder.split = self.cfg["live_transcribe"]
        self.live_timer = QTimer(singleShot=True, interval=LIVE_FALLBACK_MS)
        self.live_timer.timeout.connect(self.recorder.force_live)
        self.inserter = Inserter()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.stop_timer = QTimer(singleShot=True, interval=TAIL_MS)
        self.stop_timer.timeout.connect(self._finish_recording)
        self.watch_timer = QTimer(interval=WATCH_MS)
        self.watch_timer.timeout.connect(self._watch_recording)

        self.icons = {s: mic_icon(s) for s in ("idle", "loading", "recording", "busy", "error")}
        self.edit_icons = {s: mic_icon(s, editing=True) for s in ("recording", "busy")}  # a pencil: an edit
        self.button = FloatingButton(lambda: self.recorder.level)
        self.button.pressed.connect(self.start_recording)
        self.button.released.connect(self.stop_recording)
        self.button.cancelled.connect(self.cancel_recording)
        self.button.moved.connect(self._button_moved)
        self.button.menu_requested.connect(self._show_menu)
        self.button.folder_menu_requested.connect(self._show_folder_menu)
        self.button.set_folder_colors(self.cfg["folder_colors"])
        self._tinted: dict[int, str | None] = {}  # claude.exe PID -> the background its terminal got (colors.py)
        self.bubble: Bubble | None = None
        self.button.session_clicked.connect(self._focus_session)
        self.button.mute_toggled.connect(self._toggle_mute)
        self.button.theme_chosen.connect(self._set_theme)
        self.button.set_muted(self.cfg["muted"])
        self.tracker = sessions.SessionTracker()
        self.session_timer = QTimer(interval=SESSION_POLL_MS)
        self.session_timer.timeout.connect(self._poll_sessions)
        self.tts: QTextToSpeech | None = None
        self.piper: voice.PiperSpeaker | None = None
        self._speech: list[tuple[str, str]] = []  # (text, kind) waiting to be read (see _speak)
        self._speaking = False
        self._reading_artifact = False  # what's being read now is an artifact summary
        self._said_at = 0.0
        self.summarizer = artifacts.Summarizer()
        self._summary_lock = threading.Lock()  # one artifact after another
        self._artifact_speech = ""  # the last artifact summary, for reading it again
        self._usage_samples: list[tuple[datetime, float]] = []
        self._samples_window = None  # resets_at of the 5-hour window the samples belong to
        self._forecast_warned = None  # the 5-hour window we already warned about
        self.agent = agent.VoiceAgent(self.cfg["agent_model"], self.bridge.agent_event.emit, self.cfg["name"],
                                      bypass=self._sessions_bypass)
        self._no_voice_told = False  # told once that there's no voice to read Czech with
        self.agent_ptt: hotkey.PushToTalk | None = None
        self._agent_capture: hotkey.PushToTalk | None = None  # a hook capturing the agent's new button (settings)
        self._agent_capture_wait = 0
        self._agent_capture_timer = QTimer(interval=100)
        self._agent_capture_timer.timeout.connect(self._poll_agent_capture)
        self._agent_state = "idle"  # what its chip shows (listening comes from the recorder)
        self._agent_pressed_at = 0.0
        self._hands_free = False  # the agent listens until Pepa stops talking (a click, not a hold)
        self._feed: dict = {}  # the agent's last exchange, as shown in the panel
        self._confirm: dict | None = None  # a message the agent wants to send, waiting for Pepa's yes
        self.listen_timer = QTimer(singleShot=True, interval=LISTEN_MAX_MS)
        self.listen_timer.timeout.connect(self._speech_over)
        self.confirm_timer = QTimer(singleShot=True, interval=CONFIRM_TIMEOUT_MS)
        self.confirm_timer.timeout.connect(self._confirm_expired)
        self.feed_timer = QTimer(singleShot=True, interval=FEED_KEEP_MS)
        self.feed_timer.timeout.connect(self._feed_expired)
        self.agent_idle_timer = QTimer(interval=AGENT_IDLE_CHECK_MS)
        # in a thread: ending the process waits for it (up to 3 s), the UI mustn't
        self.agent_idle_timer.timeout.connect(
            lambda: threading.Thread(target=self.agent.stop_if_idle, daemon=True).start())
        self.agent_idle_timer.start()
        self.button.agent_clicked.connect(self._agent_clicked)
        # the user's own tasks (notebook.py): every half hour the first active one is offered as a new session
        self.tasks = tasks.load()
        if tasks.settle_started(self.tasks):  # started before a running session meant Hotovo
            try:
                tasks.save(self.tasks)
            except OSError:
                log.exception("Úkoly nejde uložit")
        self.notebook: Notebook | None = None
        self.tasks_timer = QTimer()
        self.tasks_timer.timeout.connect(self._check_tasks)
        self.tasks_timer.start(tasks.FIRST_CHECK_MS)  # then every CHECK_EVERY_MS (_check_tasks)
        # what a task's session says about it (the orbit-ukoly mod): a note, or "done"
        self.inbox_timer = QTimer(interval=tasks.INBOX_EVERY_MS)
        self.inbox_timer.timeout.connect(self._check_inbox)
        self.inbox_timer.start()
        self.bridge.task_done.connect(self._task_done)
        self.button.notes_clicked.connect(self.open_notebook)
        self.button.set_notes_count(sum(t.status == "active" for t in self.tasks))
        self.button.connect_clicked.connect(lambda: self.open_wizard("claude"))
        self.button.statusline_clicked.connect(self._enable_statusline)
        self.button.set_usage_visible(self.cfg["show_usage"])
        self.button.set_fade_after(self.cfg["fade_after_s"])
        self._place_button()
        self._watch_screens()

        self.menu = QMenu()
        self.hint_action = self.menu.addAction("")
        self.hint_action.setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction("Nastavení…", self.open_settings)
        self.menu.addAction("Průvodce nastavením…", self.open_wizard)
        self.menu.addAction("Poznámky…", self.open_notebook)
        self.toggle_action = QAction("Zobrazovat plovoucí tlačítko", self.menu, checkable=True)
        self.toggle_action.setChecked(self.cfg["show_button"])
        self.toggle_action.toggled.connect(self._set_button_visible)
        self.menu.addAction(self.toggle_action)
        self.menu.addAction("Historie diktátů…", self.open_history)
        self.menu.addAction("Vložit poslední diktát", lambda: self._paste_last(from_menu=True))
        self.menu.addAction("Kopírovat poslední diktát", self._copy_last)
        self.retry_action = self.menu.addAction("Přepsat znovu poslední diktát", self._retry_dictation)
        self.retry_action.setEnabled(False)
        self.menu.addAction("Obnovit využití Clauda", self._fetch_usage)
        self.menu.addAction("Naučit slovník z nových diktátů", lambda: self._maybe_learn(force=True))
        self.menu.addAction("Exportovat slovník…", self._export_vocabulary)
        self.menu.addAction("Importovat slovník…", self._import_vocabulary)
        self.reread_action = self.menu.addAction("Přečíst znovu poslední artefakt", self._reread_artifact)
        self.reread_action.setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction("Ukončit", QApplication.quit)
        self.tray = QSystemTrayIcon(self.icons["loading"])
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        b = self.bridge
        b.ptt_down.connect(self.start_recording)
        b.ptt_up.connect(self.stop_recording)
        b.mic_live.connect(self._mic_live)
        b.piece_ready.connect(self._take_pieces)
        b.server_ready.connect(self._server_ready)
        b.server_failed.connect(self._server_failed)
        b.server_event.connect(self._server_event)
        b.dictated.connect(self._dictated)
        b.transcribe_failed.connect(self._transcribe_failed)
        b.input_seen.connect(lambda: self.ptt.watch_clicks(False))
        b.rewritten.connect(self._rewritten)
        b.rewrite_failed.connect(self._rewrite_failed)
        b.retranscribed.connect(self._retranscribed)
        b.usage_ready.connect(self._usage_ready)
        b.usage_failed.connect(self._usage_failed)
        b.learned.connect(self._learned)
        b.learn_failed.connect(self._learn_failed)
        b.artifact_ready.connect(self._artifact_ready)
        b.artifact_failed.connect(self._artifact_failed)
        b.agent_down.connect(self._agent_down)
        b.agent_up.connect(self._agent_up)
        b.speech_over.connect(self._speech_over)
        b.agent_heard.connect(self._agent_heard)
        b.agent_event.connect(self._agent_event)
        b.captured.connect(self._key_captured)
        b.agent_captured.connect(self._agent_key_captured)
        self.usage_timer = QTimer(interval=USAGE_REFRESH_MS)
        self.usage_timer.timeout.connect(self._fetch_usage)
        self.claude.changed.connect(self._claude_changed)
        self.downloads.progress.connect(self._download_progress)
        self.downloads.finished.connect(self._download_finished)

        self.ptt = hotkey.PushToTalk(self.cfg["ptt"], b.ptt_down.emit, b.ptt_up.emit, on_input=self._user_input,
                                     own_point=inserter.own_point)
        self.ptt.start()
        self._start_server()
        self._set_button_visible(self.cfg["show_button"])
        # Claude's features (limits, sessions and their hooks, the agent) start once the check says it's connected
        self._apply_usage_setting()
        self._apply_sessions_setting()
        self._apply_agent_setting()
        self.claude.refresh()
        self._prepare_voice()
        self.refresh()
        if config.problem:
            QTimer.singleShot(0, lambda: self._notify(config.problem, error=True))
        if self.cfg["wizard_pending"]:
            QTimer.singleShot(0, self.open_wizard)

    # -- whisper server ---------------------------------------------------------------------

    def _start_server(self):
        """(Re)starts Whisper with the model from the settings. Without the model file (not downloaded yet) there is
        nothing to start: the button says so and dictation waits for the download."""
        self._server_gen += 1
        gen, model = self._server_gen, self.cfg["model"]
        if not config.model_present(model):
            log.info("Model %s není stažený, rozpoznávání čeká", model)
            # another model's server goes (in a thread: killing it can take a moment), unless a newer start came
            threading.Thread(target=lambda: gen == self._server_gen and self.server.stop(), daemon=True).start()
            self.server_state = "nomodel"
            self.refresh()
            return
        self.server_state = "loading"
        self.refresh()

        def run():
            try:
                self.server.start(model)
                self.bridge.server_ready.emit(gen)
            except Exception as e:
                log.exception("Start whisper serveru selhal")
                self.bridge.server_failed.emit(gen, str(e))

        threading.Thread(target=run, daemon=True).start()

    def _server_ready(self, gen: int):
        if gen == self._server_gen:
            self.server_state = "ready"
            self.refresh()

    def _server_failed(self, gen: int, msg):
        if gen != self._server_gen:  # a newer start (another model, a finished download) replaced this one
            return
        self.server_state = "error"
        self.refresh()
        self._notify(f"Rozpoznávání řeči se nespustilo: {msg}", error=True)

    def _server_event(self, kind: str, text: str):
        """What the Whisper server says on its own (WhisperServer.on_event)."""
        if kind == "backend":
            if text == "cpu":
                self._tell_cpu()
            return
        if self.server_state == "nomodel":  # a start for a model that's gone since: nothing of it matters
            return
        if kind == "restarting":
            self.server_state = "loading"
            if not self._restart_told:  # once: it may die again, the button shows it anyway
                self._restart_told = True
                self._notify("Rozpoznávání řeči spadlo, spouštím ho znovu. Za chvilku zase můžeš diktovat, rozpracovaný "
                             "diktát se dopíše.", title="Rozpoznávání řeči")
        elif kind == "restarted":
            self.server_state = "ready"
        elif kind == "failed":
            self.server_state = "error"
            self._notify(text, error=True, title="Rozpoznávání řeči")
        self.refresh()

    def _tell_cpu(self):
        """Once per run: the transcription runs on the processor. Not when that's expected (no usable graphics card)
        and the model is already the one recommended for it."""
        if self._cpu_told:
            return
        self._cpu_told = True
        turbo = "turbo" in self.cfg["model"]
        if turbo and downloads.advise().slow:
            return
        if turbo:
            text = ("Přepis běží jen na procesoru, takže bude pomalejší. Whisper nemůže použít grafickou kartu, pomoct "
                    "může nový ovladač grafiky.")
        else:
            text = ("Přepis běží na procesoru, takže bude pomalý. Doporučuju model turbo (Nastavení › Přepis › "
                    "Model).")
        self._notify(text, title="Rozpoznávání řeči")

    def _model_missing_text(self) -> str:
        model = self.cfg["model"]
        if self.downloads.running(model):
            return (f"Model pro rozpoznávání řeči se ještě stahuje ({self.downloads.percent(model)} %). Diktovat půjde, "
                    "až bude hotový.")
        return "Chybí model pro rozpoznávání řeči. Stáhneš ho v nastavení (Přepis › Model) nebo v průvodci."

    # -- downloads (models, voices) ----------------------------------------------------------

    def _download_progress(self, key: str, done, total):
        if key == self.cfg["model"] and self.server_state == "nomodel":
            self.refresh()

    def _download_finished(self, key: str, error: str):
        item = downloads.ITEMS.get(key)
        label = item.label if item else key
        if error == CANCELLED:
            log.info("Stahování %s zrušeno", key)
        elif error:
            self._notify(f"Stahování ({label}) se nepovedlo: {error}", error=True)
        elif key == self.cfg["model"]:
            self._notify("Model je stažený, za chvilku můžeš diktovat.", title="Rozpoznávání řeči", kind="done")
            self._start_server()
        elif key in voice.VOICES:
            self._notify(f"Český {label} je stažený.", title="Předčítání", kind="done")
            self._prepare_voice()
        else:  # a model that isn't the one in use (downloaded from the settings and not saved)
            self._notify(f"{label[:1].upper()}{label[1:]} je stažený.", kind="done")
        self.refresh()

    # -- Claude usage -----------------------------------------------------------------------

    def _apply_usage_setting(self):
        """Without Claude connected the panel shows a "Připojit Clauda" link instead (FloatingButton.set_claude).
        The limits come from Orbit's status line (read every few seconds) or, opted in, from the OAuth endpoint."""
        self.button.set_usage_visible(self.cfg["show_usage"])
        self._apply_statusline()
        if self.cfg["show_usage"] and self.claude.connected:
            interval = USAGE_REFRESH_MS if self.cfg["usage_source"] == "oauth" else STATUS_REFRESH_MS
            if not self.usage_timer.isActive() or self.usage_timer.interval() != interval:
                self.usage_timer.start(interval)
                self._fetch_usage()
        else:
            self.usage_timer.stop()

    def _apply_statusline(self):
        """Orbit's status line in Claude Code (the limits, the sessions' exact context): put in with the user's yes
        (claude_statusline), taken out without it. Like the hooks: only while Claude is connected, and Claude Code's
        folder is never created."""
        if not self.claude.connected or not paths.claude_dir().is_dir():
            return
        if self._cfg_doubtful and not self.cfg["claude_statusline"]:
            return  # a "no" only because config.json couldn't be read
        try:
            claude_settings.set_statusline(self.cfg["claude_statusline"])
        except claude_settings.SettingsError as e:
            self._notify(str(e), error=True)
        except Exception as e:
            log.exception("Stavový řádek Claude Code nejde nastavit")
            self._notify(f"Stavový řádek v Claude Code nejde nastavit: {e}", error=True)

    def _enable_statusline(self):
        """The "Zapnout →" link in the panel: the user's yes to the status line."""
        self.cfg["claude_statusline"] = True
        config.save(self.cfg)
        log.info("Stavový řádek pro limity zapnut z panelu")
        self._apply_usage_setting()
        self._fetch_usage()  # the link goes away right now, not with the next read
        if claude_settings.statusline_installed():
            self._notify("V Claude Code teď běží stavový řádek Orbitu. Limity se ukážou po první zprávě v kterékoli "
                         "relaci.", title="Limity Clauda", kind="done")

    # -- Claude connection ------------------------------------------------------------------

    def _claude_changed(self, status):
        """After every check of Claude Code (start, every 5 min while it isn't connected, during install / login).
        What needs it is switched on or off only when "connected" itself changes."""
        connected = self.claude.connected
        self.button.set_claude(connected)
        if connected == self._claude_was:
            return
        self._claude_was = connected
        if not connected:
            self.usage, self.usage_error = None, None
            self.button.set_usage(None, None)
        self._apply_usage_setting()
        self._apply_sessions_setting()
        self._apply_agent_setting()
        self.refresh()

    def _fetch_usage(self):
        if self._usage_inflight:
            return
        source = self.cfg["usage_source"]
        if source == "statusline" and not self.cfg["claude_statusline"]:  # no yes to the status line yet
            self._usage_ready(claude_usage.Usage([], note="Limity Orbit čte ze stavového řádku Claude Code.",
                                                 source=source, action="statusline"))
            return
        self._usage_inflight = True

        def run():
            try:
                self.bridge.usage_ready.emit(claude_usage.fetch(source))
            except claude_usage.UsageError as e:
                self.bridge.usage_failed.emit(str(e))
            except Exception as e:
                log.exception("Načtení využití Clauda selhalo")
                self.bridge.usage_failed.emit(f"Načtení využití selhalo: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _usage_ready(self, usage):
        self._usage_inflight = False
        self.usage, self.usage_error = usage, None
        self.button.set_usage(usage, None)
        self._update_forecast(usage)
        self.refresh()

    def _update_forecast(self, usage):
        """Track the 5-hour window's pace; warn once per window when it would run out within FORECAST_WARN."""
        lim = usage.get("session")
        if lim is None:
            return
        now, samples = datetime.now(timezone.utc), self._usage_samples
        if samples and (lim.percent < samples[-1][1] - 1 or self._samples_window != lim.resets_at):
            samples.clear()  # a new window started
        self._samples_window = lim.resets_at
        # a sample when it moved or every 2 minutes (the status line's files are read every few seconds): 60 of them
        # still reach back further than the 30 minutes the forecast looks at
        if not samples or lim.percent != samples[-1][1] or now - samples[-1][0] >= timedelta(minutes=2):
            samples.append((now, lim.percent))
        del samples[:-60]
        eta = claude_usage.forecast(samples, lim.resets_at)
        self.button.set_forecast(eta)
        if eta and eta - now <= FORECAST_WARN and self._forecast_warned != lim.resets_at:
            self._forecast_warned = lim.resets_at
            local = eta.astimezone()
            reset = claude_usage.reset_text(lim.resets_at)
            self._notify(f"Při tomhle tempu ti 5hodinový limit dojde v {local.hour}:{local.minute:02d}"
                         + (f", {reset}." if reset else "."), title="Limit Clauda")

    def _usage_failed(self, msg):
        self._usage_inflight = False
        if msg != self.usage_error:
            log.warning("Využití Clauda: %s", msg)
        self.usage_error = msg
        self.button.set_usage(self.usage, msg)
        self.refresh()

    # -- recording --------------------------------------------------------------------------

    def start_recording(self, for_agent: bool = False):
        if self.stop_timer.isActive():  # pressed again during the tail – just keep recording
            if self.take and self.take.agent == for_agent:
                self.stop_timer.stop()
            return
        if self.recorder.active:
            return
        self._stop_speech()  # don't talk over (or into) a dictation
        if self.server_state == "error":  # the mic stays closed; maybe it starts this time (a driver came back)
            self._notify("Rozpoznávání řeči neběží, zkouším ho spustit znovu. Za chvilku to zkus.",
                         title="Rozpoznávání řeči")
            self._start_server()
            return
        if self.server_state == "nomodel":  # the mic stays closed: there'd be nothing to transcribe with
            self._notify(self._model_missing_text(), title="Rozpoznávání řeči")
            return
        vocabulary = self.cfg["vocabulary"]
        if for_agent:
            try:
                self.agent.start()  # gets ready while Pepa talks
            except Exception as e:
                log.exception("Agent nejde spustit")
                self._notify(f"Agent nejde spustit: {e}", error=True)
                return
            # the sessions' folders, so Whisper spells them right
            vocabulary = ", ".join([vocabulary, *sorted({s.folder for s in self.tracker.sessions.values()})])
        self.live_timer.start()
        self.take = Take(build_prompt(vocabulary), for_agent)
        self._check_edit(self.take)
        # Only a question already in the panel can be answered: what was said before it came is no answer to it.
        # Not waiting until it's read to the end: a long one takes half a minute, Pepa reads it and cuts it short.
        if for_agent and self._confirm and time.monotonic() - self._confirm["shown"] >= CONFIRM_SEEN_S:
            self.take.confirm_id = self._confirm["id"]
        try:
            self.recorder.start()
        except Exception as e:
            self.live_timer.stop()
            self.take.drop_rewriter()
            self.take = None
            log.exception("Mikrofon nejde spustit")
            self._notify(f"Mikrofon nejde spustit: {e}", error=True)
            return
        self._recording_since = time.monotonic()
        self._desktop_ok = winutil.on_user_desktop()
        self.watch_timer.start()
        self.refresh()

    def _mic_live(self):
        """Audio is really flowing now – only now tell the user to speak (beep + red button)."""
        self.live_timer.stop()
        if not self.recorder.active:
            return
        if self.take:  # Ctrl pressed a moment after the mouse button still counts
            self._check_edit(self.take)
        if self.cfg["sounds"] and not self.cfg["muted"]:
            winutil.play("start")
        self.refresh()

    def _ptt_key(self) -> int:
        """The dictation key's code when it's a key (held as well: Right Ctrl doesn't make a dictation an edit)."""
        return self.cfg["ptt"]["code"] if self.cfg["ptt"].get("kind") == "key" else 0

    def _check_edit(self, take: Take):
        """Ctrl or Shift held as the dictation starts: an instruction for editing text, not text. Claude (for what
        isn't a plain "Nahraď X za Y") starts right away, while the user talks."""
        if take.edit or take.agent or not self.cfg["voice_edit"] or not inserter.edit_held(self._ptt_key()):
            return
        take.edit = True
        log.info("Diktát je pokyn pro úpravu textu")
        if self.claude.connected:
            take.rewriter = rewrite.Rewriter(self.cfg["name"], self.cfg["about"])
            try:
                take.rewriter.start()
            except claude_cli.ClaudeError as e:
                log.warning("Claude pro úpravu textu nejde spustit: %s", e)
                take.rewriter = None
        self.refresh()

    def stop_recording(self, for_agent: bool = False):
        if self.take and self.take.agent != for_agent:  # the other button's recording
            return
        if self.recorder.active and not self.stop_timer.isActive():
            self.stop_timer.start()

    def cancel_recording(self):
        """The mic button was dragged: it only ever starts dictation, so the agent's recording goes on."""
        if self.take and self.take.agent:
            return
        self._drop_recording()

    def _drop_recording(self):
        """Ends the recording and throws it away."""
        self.stop_timer.stop()
        self.live_timer.stop()
        self.listen_timer.stop()
        self.watch_timer.stop()
        self._hands_free = False
        if self.take:
            if self.take.agent:
                self._agent_state = self._agent_rest()
            self.take.cancelled = True
            self.take.drop_rewriter()
            self.take = None
        if self.recorder.active:
            self.recorder.stop()
            self.recorder.pop_pieces()
        self.refresh()

    def _watch_recording(self):
        """Every second while recording: a key-up the hook never saw, Windows' secure desktop, the length cap."""
        if not self.recorder.active:
            self.watch_timer.stop()
            return
        if self._desktop_ok and not winutil.on_user_desktop():
            # the lock screen or a UAC prompt: the user isn't dictating any more, and the key's release won't come
            log.warning("Windows přepnul na zabezpečenou plochu (zamčení, UAC), nahrávání ruším")
            for ptt in (self.ptt, self.agent_ptt):
                if ptt:
                    ptt.reset()
            self._drop_recording()
            return
        if time.monotonic() - self._recording_since > MAX_RECORDING_S and not self.stop_timer.isActive():
            log.warning("Nahrávání trvá přes %d s, ukončuji ho", MAX_RECORDING_S)
            for ptt in (self.ptt, self.agent_ptt):
                if ptt:
                    ptt.reset()
            self._finish_recording()
            self._notify(f"Nahrávání jsem po {MAX_RECORDING_S // 60} minutách zastavil a přepisuju, co zaznělo. "
                         "Nedržíš omylem klávesu?", title="Diktování")
            return
        for ptt in (self.ptt, self.agent_ptt):
            if ptt:
                ptt.check_stuck()  # calls its on_release: the recording ends the usual way

    def _take_pieces(self):
        if self.take:
            for piece in self.recorder.pop_pieces():
                self._queue_piece(self.take, piece)

    def _submit(self, fn, *args):
        """On the transcription worker; an exception there would otherwise vanish in its Future."""
        def run():
            try:
                fn(*args)
            except Exception:
                log.exception("Chyba ve vlákně přepisu (%s)", fn.__name__)
        return self.executor.submit(run)

    def _queue_piece(self, take: Take, audio):
        take.audio.append(audio)
        if not is_silent(audio, self.recorder.noise):
            take.spoken = True
            self._submit(self._transcribe_piece, take, audio)

    def _finish_recording(self):
        self.live_timer.stop()
        self.listen_timer.stop()
        self.stop_timer.stop()
        self.watch_timer.stop()
        self._hands_free = False
        if not self.recorder.active or self.take is None:
            return
        was_live = self.recorder.live
        tail = self.recorder.stop()
        take, self.take = self.take, None
        take.target = inserter.foreground()
        for piece in self.recorder.pop_pieces():  # cut just before release, not picked up yet
            self._queue_piece(take, piece)
        self._queue_piece(take, tail)
        if self.cfg["sounds"] and not self.cfg["muted"] and was_live:
            winutil.play("stop")  # after queueing: nothing may cost the dictation
        if not take.spoken:
            seconds = sum(map(len, take.audio)) / SAMPLE_RATE
            log.info("Nahrávka %.2f s je ticho nebo moc krátká – přeskakuji (signál: %s, šum %.0f)", seconds,
                     self.recorder.got_signal, self.recorder.noise)
            take.drop_rewriter()
            if take.agent:
                self._agent_state = self._agent_rest()
            if seconds >= SILENT_TELL_S:
                self._tell_silence(take.agent)
            self.refresh()
            return
        take.released_at = time.perf_counter()
        if take.agent:
            self._agent_state = "transcribing"
        else:
            self.pending += 1
        if take.edit:  # what's selected is read while Whisper transcribes the instruction
            self._edit_pending += 1
            self._probe_selection(take)
        self.refresh()
        self._submit(self._finish_take, take, list(self.cfg["replacements"]), self.cfg["voice_commands"],
                     self.cfg["keep_recordings"], self.cfg["learn_vocabulary"])

    def _tell_silence(self, for_agent: bool):
        """A recording long enough to be meant had nothing in it: say why, or it looks like Orbit ignored it."""
        if not self.recorder.got_signal:  # exact zeros all the time: muted, or Windows doesn't let apps use the mic
            text = ("Mikrofon posílá jen ticho. Není ztlumený? A mají aplikace přístup k mikrofonu (Nastavení "
                    "Windows › Soukromí a zabezpečení › Mikrofon)?")
        elif self.recorder.voiced_s >= 0.5:  # something like speech, only too quiet to count
            text = ("Skoro nic jsem neslyšel, mikrofon je moc potichu. Zesil ho v nastavení zvuku ve Windows, nebo "
                    "mluv blíž k němu.")
        else:
            return  # nothing above the mic's own noise: nothing was said
        log.info("Nahrávka bez řeči: %s", "jen nuly" if not self.recorder.got_signal else "moc potichu")
        if for_agent:
            self._feed_update(you="…", reply=text, send=None)
        else:
            self._notify(text, title="Diktování")

    def _transcribe_piece(self, take: Take, audio):
        """Worker thread. Pieces of one take run in order, so the previous piece's text is known here."""
        if take.cancelled or take.error:
            return
        context = " ".join(take.texts)[-CONTEXT_CHARS:]
        try:
            raw = self.server.transcribe(audio, f"{take.prompt} {context}" if context else take.prompt)
            text = clean_text(raw)
        except Exception as e:
            log.warning("Přepis selhal: %s", e, exc_info=not isinstance(e, RuntimeError))
            take.error = str(e)
            return
        if raw.strip() and not text:
            log.info("Přepis odfiltrován jako halucinace (%d znaků)", len(raw.strip()))
            log.debug("Odfiltrováno: %r", raw)
        take.raw.append(raw.strip())
        if text:
            take.texts.append(text)

    def _finish_take(self, take: Take, replacements, voice_commands, keep, learn):
        """Worker thread, queued after all pieces of the take. Always ends with a signal, or the button would stay
        on "Přepisuji…" (an exception in an executor task is lost otherwise)."""
        try:
            if take.error:
                self.bridge.transcribe_failed.emit(take.error, take)
                return
            text, key = apply_replacements(" ".join(take.texts), replacements), ""
            if not take.agent:
                # a whole dictation that's a command ("Smaž to"); in edit mode "Nahraď X za Y" too
                take.command = editing.command(text, edit=True) if take.edit else \
                    editing.command(text) if voice_commands else None
                if voice_commands and not take.edit and take.command is None:
                    text, key = terminal_command(apply_voice_commands(text))
            take.text, take.key = text, key
            audio = np.concatenate(take.audio)
            take.seconds, take.raw_text = len(audio) / SAMPLE_RATE, " ".join(take.raw)
            if keep:
                take.stem = self._recording_stem()
            what = (" pro agenta" if take.agent else " (pokyn pro úpravu)" if take.edit else
                    f" (povel {take.command.kind})" if take.command else "")
            # the text only when vocabulary learning (which reads it back from the log) is on
            log.info("Přepis %.1f s zvuku za %.2f s po puštění (kusů: %d)%s: %s%s", take.seconds,
                     time.perf_counter() - take.released_at, len(take.raw), what,
                     repr(text) if learn else f"{len(text)} znaků", f" + {key}" if key else "")
        except Exception as e:
            log.exception("Dokončení přepisu selhalo")
            self.bridge.transcribe_failed.emit(str(e), take)
            return
        if take.agent:
            self.bridge.agent_heard.emit(text, take.confirm_id)
        else:
            self.bridge.dictated.emit(take)
        if keep:  # after the text is on its way: writing the WAV took ~11 ms (up to 50) on the way to the window
            self._save_recording(audio, take.raw_text, take.stem)

    @staticmethod
    def _recording_stem() -> str:
        """The name a recording gets in recordings/ (its history entry knows it before it's written)."""
        stem = datetime.now().strftime("%Y%m%d-%H%M%S")
        if (config.RECORDINGS_DIR / f"{stem}.wav").exists():  # two in one second
            stem += "-2"
        return stem

    @staticmethod
    def _save_recording(audio, text, stem: str = ""):
        try:
            config.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
            stem = config.RECORDINGS_DIR / (stem or Dictation._recording_stem())
            stem.with_suffix(".wav").write_bytes(to_wav(audio))
            stem.with_suffix(".txt").write_text(text.strip(), encoding="utf-8")
            for old in sorted(config.RECORDINGS_DIR.glob("*.wav"))[:-KEEP_RECORDINGS]:
                old.unlink()
                old.with_suffix(".txt").unlink(missing_ok=True)
        except Exception:
            log.exception("Uložení nahrávky selhalo")

    def _dictated(self, take: Take):
        """A dictation is transcribed: an instruction for an edit, a command ("Smaž to"), or text for the window."""
        if take.edit:
            self.pending -= 1
            self._edit_pending -= 1
            take.heard = True
            self._edit_ready(take)
            self.refresh()
        elif take.command:
            self.pending -= 1
            self.refresh()
            self._run_command(take.command, take)
        else:
            self._insert_text(take.text, take.key, take.target, take)

    def _insert_text(self, text, key, target=0, take: Take | None = None):
        self.pending -= 1
        self.refresh()
        self._put_text(text, key, target, take)

    def _put_text(self, text, key, target=0, take: Take | None = None, entry: history.Entry | None = None):
        """Into the window that was in front when the recording ended, only if it still is (no text, and above all
        no Enter, for another chat or terminal). Otherwise, and where Windows won't let Orbit type (a window running
        as administrator), the text goes to the clipboard. A dictation (take) gets its history entry; text from the
        history (entry) keeps its own. What was typed goes on the trail, for "Smaž to"."""
        if not text and not key:
            return
        spoken = text
        if text and self.cfg["trailing_space"] and not text.endswith("\n") and key != "send":
            text += " "
        window = inserter.foreground()
        problem = ""
        if target == -1:  # a retry from Orbit's own menu: no window of the user's to type into
            problem = "Přepis je hotový"
        elif target and not inserter.same_window(target, window):
            problem = "Okno se mezitím změnilo"
        elif inserter.runs_as_admin(window):
            problem = "Okno běží jako správce a Windows do něj Orbitu nedovolí psát"
        typed = False
        try:
            if problem:
                log.info("Text nevkládám: %s", problem)
                if text.strip():
                    self.inserter.to_clipboard(text)
                    entry = self._remember(spoken, take, history.CLIPBOARD, target or window, key) or entry
                    entry_id = entry.id if entry else ""
                    self._notify(f"{problem}, text máš ve schránce (vlož ho Ctrl+V)."
                                 + (" Nebo klikni sem a vložím ho, kam teď píšeš." if entry_id else ""),
                                 title="Diktování",
                                 on_click=(lambda: self._insert_entry(entry_id)) if entry_id else None)
                elif key:
                    self._notify(f"{problem}, povel jsem neprovedl.", title="Diktování")
                return
            if text and not self.inserter.insert(text, self.cfg["insert_mode"]):
                self._remember(spoken, take, history.CLIPBOARD, window, key)
                self._notify("Windows nevzal všechny klávesy, text máš pro jistotu ve schránce (Ctrl+V).",
                             title="Diktování")
                return  # no Enter after a text that may not be there
            typed = bool(text)
            if key:
                said = "Odešli" if key == "send" else "Stop"
                self.inserter.press(key, after_text=text, on_skipped=lambda: self._notify(
                    f"Okno se mezitím změnilo, povel „{said}“ jsem neprovedl.", title="Diktování"))
        except Exception as e:
            log.exception("Vložení textu selhalo")
            self._notify(f"Text se nepodařilo vložit: {e}", error=True)
        if key:  # sent (Enter) or interrupted (Esc): nothing typed before it can be taken back
            self.trail.clear()
        if typed:
            entry = self._remember(spoken, take, history.INSERTED, window, key) or entry
            if not key:
                if take is not None:
                    self._redictated(spoken, window)
                self._typed(text, window, entry.id if entry else "")
        if text:
            self._maybe_learn()

    def _transcribe_failed(self, msg, take):
        """The transcription failed (the server died twice, it took too long): the recording is kept, a click on
        the bubble or the menu item transcribes it again."""
        retry = not take.agent and not take.edit and bool(take.audio)
        if take.agent:
            self._agent_state = self._agent_rest()
        else:
            self.pending -= 1
        if take.edit:
            self._edit_pending -= 1
            take.drop_rewriter()
        if retry:
            self._retry_take = take
            self.retry_action.setEnabled(True)
        self.refresh()
        self._notify(f"Přepis selhal: {msg}" + (" Klikni sem a zkusím ho znovu." if retry else ""), error=True,
                     on_click=self._retry_dictation if retry else None)

    def _retry_dictation(self):
        """The last dictation whose transcription failed, transcribed again as one piece, into the window in front."""
        take = self._retry_take
        if take is None:
            return
        if self.server_state != "ready":
            if self.server_state == "error":
                self._start_server()
            self._notify("Rozpoznávání řeči ještě není připravené, zkus to za chvilku znovu.",
                         title="Rozpoznávání řeči")
            return
        self._retry_take = None
        self.retry_action.setEnabled(False)
        again = Take(take.prompt)
        again.audio, again.spoken = [np.concatenate(take.audio)], True
        window = inserter.foreground()  # the bubble takes no focus; the tray menu does (then: the clipboard)
        again.released_at, again.target = time.perf_counter(), -1 if inserter.own_window(window) else window
        log.info("Přepisuji znovu diktát, který selhal (%.1f s)", len(again.audio[0]) / SAMPLE_RATE)
        self.pending += 1
        self.refresh()
        self._submit(self._transcribe_piece, again, again.audio[0])
        self._submit(self._finish_take, again, list(self.cfg["replacements"]), self.cfg["voice_commands"],
                     self.cfg["keep_recordings"], self.cfg["learn_vocabulary"])

    # -- taking back and editing what was typed (editing.py, rewrite.py) -------------------------

    UNDO_WHY = {  # why the last dictation can't be acted on (editing.Trail.check)
        "empty": "Není s čím pracovat: poslední diktát už odešel (Enter), nebo Orbit zatím nic nenapsal.",
        "input": "Od diktátu přišla klávesa nebo klik, kurzor už může být jinde. Naslepo nic mazat nebudu, poslední "
                 "diktáty najdeš v menu Orbitu: Historie diktátů.",
        "window": "Poslední diktát je v jiném okně. Přepni se do něj a řekni to znovu.",
    }

    def _user_input(self):
        """Hook thread: the user's own key or click. After it what Orbit typed can't be taken back blindly."""
        self.trail.input_seen()
        if self._watching:
            self._watching = False
            self.bridge.input_seen.emit()  # the mouse hook a keyboard binding doesn't need goes again

    def _typed(self, text: str, window: int, entry_id: str = ""):
        """Orbit typed text into a window: on the trail, and the user's next key or click is watched for."""
        self.trail.push(editing.Typed(text, window, time.monotonic(), inserter.is_terminal(window), entry=entry_id),
                        inserter.same_window)
        self._watching = True
        self.ptt.watch_clicks(True)

    def _remember(self, text: str, take: Take | None, outcome: str, window: int, key: str = "", **more):
        """A dictation's history entry (text inserted again from the history keeps its own: take is None)."""
        if take is None or not text.strip():
            return None
        entry = self.history.add(text.strip(), raw=take.raw_text, app=inserter.app_name(window), outcome=outcome,
                                 seconds=round(take.seconds, 1), recording=take.stem, key=key, **more)
        self._history_changed()
        return entry

    def _run_command(self, cmd: editing.Command, take: Take):
        log.info("Povel: %s", cmd.kind)
        if cmd.kind == editing.PASTE_AGAIN:
            self._paste_last(target=take.target)
        elif cmd.kind in (editing.DELETE, editing.SELECT):
            self._take_back(cmd.kind, take.target)

    def _take_back(self, kind: str, target: int):
        """"Smaž to" (Backspace over the last dictation, again for the one before it) and "Vyber to" (Shift+Left
        over it): only while the cursor is surely right after it (editing.Trail)."""
        title = "Smaž to" if kind == editing.DELETE else "Vyber to"
        window = inserter.foreground()
        if target and not inserter.same_window(target, window):
            self._notify("Okno se mezitím změnilo, nic jsem neudělal.", title=title)
            return
        top, why = self.trail.check(window, inserter.same_window)
        if top is None:
            self._notify(self.UNDO_WHY[why], title=title)
            return
        if top.terminal and kind == editing.SELECT:
            self._notify("V terminálu text označovat neumím. Smazat ho jde: „Smaž to“.", title=title)
            return
        if top.terminal and not editing.terminal_safe(top.text):
            self._notify("Delší text v terminálu nesmažu: Claude Code ho mohl sbalit do jednoho bloku a smazal bych i "
                         "to, co bylo před ním. Řádek smaže Ctrl+U.", title=title)
            return
        if kind == editing.SELECT and top.selected:
            return
        count = 1 if top.selected else editing.keystrokes(top.text)  # a selection goes with one Backspace
        if count > editing.MAX_DELETE_CHARS:
            self._notify("Diktát je na smazání po znacích moc dlouhý, smaž ho prosím ručně.", title=title)
            return

        def go(ok: bool):
            again, _ = self.trail.check(inserter.foreground(), inserter.same_window)
            if not ok:
                self._notify("Pusť Ctrl a Shift, pak to řekni znovu.", title=title)
            elif again is not top:
                self._notify("Mezitím přišla klávesa nebo klik, nic jsem neudělal.", title=title)
            elif kind == editing.DELETE:
                if inserter.delete_back(count):
                    self.trail.pop()
                    log.info("Smazán poslední diktát (%d znaků)", count)
                else:
                    self._notify("Windows nevzal všechny klávesy, diktát možná nezmizel celý.", title=title)
            elif inserter.select_back(count):
                top.selected = True
                log.info("Označen poslední diktát (%d znaků)", count)
        self.inserter.when_keys_up(go, self._ptt_key())

    def _paste_last(self, target: int = 0, from_menu: bool = False):
        """"Vlož to znovu" (into the window it was said in), or the menu item (into the window in front once the
        menu has gone; from the tray that's the taskbar: then the clipboard)."""
        entry = self.history.last()
        if entry is None:
            self._notify("Zatím není co vložit, žádný diktát tu ještě není.", title="Diktování")
        elif from_menu:
            QTimer.singleShot(200, lambda: self._insert_entry(entry.id))
        else:
            self._put_text(entry.best, "", target, entry=entry)

    def _copy_last(self):
        entry = self.history.last()
        if entry is None:
            self._notify("Zatím není co kopírovat, žádný diktát tu ještě není.", title="Diktování")
            return
        self.inserter.to_clipboard(entry.best)
        self._notify("Poslední diktát máš ve schránce (vlož ho Ctrl+V).", title="Diktování")

    def _insert_entry(self, entry_id: str):
        """A text from the history (its window, the bubble of a text that went to the clipboard, the menu): into the
        window in front, unless that's Orbit's own or the taskbar."""
        entry = self.history.get(entry_id)
        if entry is None:
            return
        window = inserter.foreground()
        if not window or inserter.own_window(window) or inserter.is_shell(window):
            self.inserter.to_clipboard(entry.best)
            self._notify("Nevím, kam text vložit, máš ho ve schránce (vlož ho Ctrl+V).", title="Diktování")
            return
        self.inserter.when_keys_up(lambda ok: self._put_text(entry.best, "", window, entry=entry), self._ptt_key())

    # edit mode: Ctrl or Shift held with the dictation key

    def _probe_selection(self, take: Take):
        """What's selected in the window (Ctrl+Insert), once the user lets go of Ctrl and Shift."""
        def copied(text):
            take.selection, take.selection_done = text, True
            self._edit_ready(take)

        def keys_up(ok: bool):
            if not ok:  # still held: no Ctrl+Insert (it would be Ctrl+Shift+Insert)
                take.selection_done = True
                self._edit_ready(take)
                return
            take.probed_at = time.monotonic()
            self.inserter.copy_selection(copied)
        self.inserter.when_keys_up(keys_up, self._ptt_key())

    def _edit_ready(self, take: Take):
        """The instruction and the selection are both known: a command, a replacement Orbit does itself, or Claude."""
        if not (take.heard and take.selection_done) or take.edit_begun:
            return
        take.edit_begun = True
        title = "Úprava textu"
        instruction = take.text.strip()
        if not instruction:
            take.drop_rewriter()
            return
        window = inserter.foreground()
        if take.target and not inserter.same_window(take.target, window):
            take.drop_rewriter()
            self._notify("Okno se mezitím změnilo, úpravu jsem neprovedl.", title=title)
            return
        cmd = take.command
        if cmd and cmd.kind != editing.REPLACE:  # "Smaž to" with Ctrl held is still "Smaž to"
            take.drop_rewriter()
            self._run_command(cmd, take)
            return
        top, why = self.trail.check(window, inserter.same_window)
        if take.selection is not None:
            scope, source = rewrite.SELECTION, take.selection
        elif top is not None and not top.selected:
            scope, source = rewrite.LAST, top.text
        else:
            scope, source = rewrite.NOTHING, ""
        if cmd and source and (done := editing.replace(source, cmd)):
            take.drop_rewriter()
            new, wrong, right = done
            log.info("Úprava textu: náhrada slov (%s)", scope)
            self._apply_edit(take, scope, source, new, top,
                             lambda entry: self._corrected([(wrong, right)], learning.BY_VOICE, new.strip()))
            return
        if cmd and not source:
            take.drop_rewriter()
            self._notify(self.UNDO_WHY[why] if why in ("input", "window") else
                         "Není v čem nahrazovat. Označ text, nebo to řekni hned po diktátu.", title=title)
            return
        if not self.claude.connected:
            take.drop_rewriter()
            self._notify("Tenhle pokyn umí jen Claude a ten není připojený (Nastavení › Claude). Bez něj umím "
                         "„Nahraď X za Y“, „Smaž to“ a „Vyber to“.", title=title)
            return
        if len(source) > rewrite.MAX_SOURCE_CHARS:
            take.drop_rewriter()
            self._notify(f"Označený text je na úpravu moc dlouhý (víc než {rewrite.MAX_SOURCE_CHARS} znaků).",
                         title=title)
            return
        rewriter, take.rewriter = take.rewriter or rewrite.Rewriter(self.cfg["name"], self.cfg["about"]), None
        app = inserter.app_name(window)
        self._rewriting += 1
        self.refresh()
        log.info("Úprava textu přes Clauda (%s, %d znaků)", scope, len(source))

        def run():
            try:
                result = rewriter.run(instruction, source.rstrip(), scope, app)
            except Exception as e:
                log.warning("Úprava textu selhala: %s", e, exc_info=not isinstance(e, claude_cli.ClaudeError))
                self.bridge.rewrite_failed.emit(take, str(e))
                return
            self.bridge.rewritten.emit(take, (scope, source, top, result))
        threading.Thread(target=run, daemon=True).start()  # a daemon: quitting Orbit mustn't wait for Claude

    def _rewritten(self, take: Take, data):
        self._rewriting -= 1
        self.refresh()
        scope, source, top, result = data
        title = "Úprava textu"
        if not result.text:
            self._notify(result.problem or "Claude nic nevrátil, text zůstal, jak byl.", title=title)
            return
        # the space after the last dictation stays where it was
        new = result.text + source[len(source.rstrip()):] if scope == rewrite.LAST else result.text
        if new == source:
            self._notify(result.problem or "Claude na textu nic nezměnil.", title=title)
            return
        log.info("Úprava textu hotová (%d → %d znaků)", len(source), len(new))
        replace = take.command is not None and take.command.kind == editing.REPLACE

        def done(entry):
            fixes = editing.word_changes(source, new) if replace and scope != rewrite.NOTHING else []
            if fixes:  # "Nahraď X za Y" that only Claude understood: still a correction of the recognition
                self._corrected(fixes, learning.BY_VOICE, new.strip())
            elif scope == rewrite.NOTHING:
                self._notify(f"Napsáno podle pokynu „{take.text.strip()}“. Klikni sem a zase to smažu.", title=title,
                             kind="done", on_click=lambda: self._revert_edit(entry.id))
            else:
                self._notify(f"Hotovo: „{take.text.strip()}“. Klikni sem a vrátím původní text.", title=title,
                             kind="done", on_click=lambda: self._revert_edit(entry.id))
        self._apply_edit(take, scope, source, new, top, done)

    def _rewrite_failed(self, take: Take, msg: str):
        self._rewriting -= 1
        self.refresh()
        self._notify(f"Úprava se nepovedla: {msg}", error=True, title="Úprava textu")

    def _apply_edit(self, take: Take, scope: str, source: str, new: str, top: editing.Typed | None, on_done):
        """The edited text instead of the old one: over the selection (pasted: replaces it, and where the selection
        isn't in a text field nothing happens, while typed letters could be a web page's shortcuts), over the last
        dictation (Backspace from where they differ, then the rest), or at the cursor. When it can't go there safely
        (another window, a key or click meanwhile) it goes to the clipboard."""
        title = "Úprava textu"
        original = source.strip()
        window = inserter.foreground()

        def to_clipboard(reason: str):
            self.inserter.to_clipboard(new.strip())
            self._remember(new, take, history.CLIPBOARD, window, instruction=take.text.strip(), original=original)
            self._notify(f"{reason}, upravený text máš ve schránce (vlož ho Ctrl+V).", title=title)

        if take.target and not inserter.same_window(take.target, window):
            to_clipboard("Okno se mezitím změnilo")
            return
        if inserter.runs_as_admin(window):
            to_clipboard("Okno běží jako správce a Windows do něj Orbitu nedovolí psát")
            return

        def go(ok: bool):
            if not ok:
                to_clipboard("Ctrl nebo Shift zůstal držený")
                return
            now = inserter.foreground()
            if take.target and not inserter.same_window(take.target, now):
                to_clipboard("Okno se mezitím změnilo")
                return
            if scope == rewrite.SELECTION:
                if self.trail.last_input > take.probed_at:
                    to_clipboard("Mezitím přišla klávesa nebo klik, takže text už nemusí být označený")
                    return
                text, ok = new, self.inserter.insert(new, "paste")
            elif scope == rewrite.LAST:
                current, _ = self.trail.check(now, inserter.same_window)
                if current is not top:
                    to_clipboard("Mezitím přišla klávesa nebo klik")
                    return
                if top.terminal and not editing.terminal_safe(top.text):
                    to_clipboard("Delší text v terminálu nepřepíšu (Claude Code ho mohl sbalit do jednoho bloku)")
                    return
                same = len(os.path.commonprefix([source, new]))
                ok = inserter.delete_back(editing.keystrokes(source[same:]))
                ok = ok and (not new[same:] or self.inserter.insert(new[same:], self.cfg["insert_mode"]))
                text = new
            else:
                text = new + (" " if self.cfg["trailing_space"] and not new.endswith("\n") else "")
                ok = self.inserter.insert(text, self.cfg["insert_mode"])
            if not ok:
                self._notify("Windows nevzal všechny klávesy, upravený text máš pro jistotu ve schránce (Ctrl+V).",
                             title=title)
                self.inserter.to_clipboard(new.strip())
                return
            entry = self._remember(new, take, history.INSERTED, now, instruction=take.text.strip(), original=original)
            if scope == rewrite.LAST:  # the same place on the trail, with the new text
                top.text, top.at, top.selected, top.entry = new, time.monotonic(), False, entry.id if entry else ""
                self._watching = True
                self.ptt.watch_clicks(True)
            else:
                self._typed(text, now, entry.id if entry else "")
            if entry:
                on_done(entry)
        self.inserter.when_keys_up(go, self._ptt_key())

    def _revert_edit(self, entry_id: str):
        """The edit's bubble was clicked: the text from before it back (only while it's surely still right before
        the cursor; otherwise the original goes to the clipboard)."""
        entry = self.history.get(entry_id)
        if entry is None:
            return
        window = inserter.foreground()
        top, why = self.trail.check(window, inserter.same_window)

        def fallback(reason: str):
            if entry.original:
                self.inserter.to_clipboard(entry.original)
                self._notify(f"{reason}, původní text máš ve schránce (vlož ho Ctrl+V).", title="Úprava textu")
            else:
                self._notify(reason + ".", title="Úprava textu")

        if top is None or top.entry != entry_id:
            fallback("Text už není hned před kurzorem" if why in ("", "empty") else
                     "Od úpravy přišla klávesa nebo klik" if why == "input" else "Upravený text je v jiném okně")
            return
        if top.terminal and not editing.terminal_safe(top.text):
            fallback("Delší text v terminálu nepřepíšu")
            return

        def go(ok: bool):
            again, _ = self.trail.check(inserter.foreground(), inserter.same_window)
            if not ok or again is not top:
                fallback("Mezitím přišla klávesa nebo klik")
                return
            tail = top.text[len(top.text.rstrip()):]
            old = entry.original + tail if entry.original else ""
            same = len(os.path.commonprefix([top.text, old]))
            inserter.delete_back(editing.keystrokes(top.text[same:]))
            if old[same:]:
                self.inserter.insert(old[same:], self.cfg["insert_mode"])
            if old:
                top.text, top.at, top.entry = old, time.monotonic(), ""
            else:
                self.trail.pop()
            log.info("Úprava textu vrácena")
        self.inserter.when_keys_up(go, self._ptt_key())

    # corrections: what Whisper wrote and what the user meant (learning.py)

    def _corrected(self, pairs: list[tuple[str, str]], source: str, context: str = ""):
        """The user's own corrections: kept for vocabulary learning, and a bubble offers to fix them every time."""
        kept = [(w, r) for w, r in pairs if learning.add_correction(w, r, context, source)]
        if not kept:
            return
        if source != learning.REDICTATED:  # a guess from saying it again: only for learning, no bubble
            shown = ", ".join(f"{w} → {r}" for w, r in kept[:4])
            self._notify(f"Opraveno: {shown}. Klikni sem a budu to tak opravovat vždycky.", title="Oprava",
                         kind="done", on_click=lambda: self._always_fix(kept))
        self._maybe_learn()

    def _always_fix(self, pairs: list[tuple[str, str]]):
        """The correction's bubble was clicked: a fix of letter case into the vocabulary ("claude" → "Claude"),
        another into the replacements, applied to every dictation from now on."""
        if self.dialog is not None:  # Uložit there would write over it
            self._notify("Nejdřív zavři nastavení, pak klikni na opravu znovu.", title="Slovník")
            return
        words = [r for w, r in pairs if w.lower() == r.lower()]
        fixes = [[w, r] for w, r in pairs if w.lower() != r.lower()]
        merged = vocab.merge(self.cfg["vocabulary"], self.cfg["replacements"], words, fixes)
        self.cfg.update(vocabulary=merged.vocabulary, replacements=merged.replacements)
        config.save(self.cfg)
        log.info("Opravy z diktátu do slovníku: + %d slov, + %d oprav", len(merged.added_words),
                 len(merged.added_fixes))
        self._notify(vocab.describe(merged), title="Slovník", kind="done")

    def _redictated(self, text: str, window: int):
        """A dictation right after "Smaž to" into the same place, much like the deleted one: what differs is most
        likely what Whisper got wrong the first time (a weaker hint than a correction, for learning only)."""
        deleted, self.trail.deleted = self.trail.deleted, None
        if not deleted or time.monotonic() - self.trail.deleted_at > REDICTATE_S or \
                not inserter.same_window(deleted.window, window):
            return
        if not REDICTATE_SIMILAR <= editing.similar(deleted.text, text) < 1:
            return
        pairs = [(w, r) for w, r in editing.word_changes(deleted.text, text) if w.lower() != r.lower()]
        if pairs:
            self._corrected(pairs, learning.REDICTATED, text.strip())

    # the history window

    def open_history(self):
        window = self.history_window
        if window is None:
            window = self.history_window = HistoryWindow(self.history, config.RECORDINGS_DIR)
            window.insert_requested.connect(self._insert_entry)
            window.copy_requested.connect(self._copy_entry)
            window.retranscribe_requested.connect(self._retranscribe_entry)
            window.correction_saved.connect(self._entry_corrected)
            window.remove_requested.connect(lambda entry_id: (self.history.remove(entry_id), window.refresh()))
            window.clear_requested.connect(lambda: (self.history.clear(), window.refresh()))
        window.refresh()
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def _history_changed(self, select: str | None = None, status: str = ""):
        if self.history_window is not None and self.history_window.isVisible():
            self.history_window.refresh(select, status)

    def _copy_entry(self, entry_id: str):
        entry = self.history.get(entry_id)
        if entry:
            self.inserter.to_clipboard(entry.best)

    def _entry_corrected(self, entry_id: str, text: str):
        """The user corrected a text in the history: what changed in a dictation is a correction for learning (an
        edit's result is Claude's text, not Whisper's: just saved)."""
        entry = self.history.get(entry_id)
        if entry is None:
            return
        before = entry.best
        self.history.update(entry, corrected=text)
        fixes = [] if entry.instruction else editing.word_changes(before, text)
        self._history_changed(entry_id, "Oprava uložená." + (" Opravená slova si Orbit vezme do učení slovníku."
                                                             if fixes else ""))
        if fixes:
            self._corrected(fixes, learning.IN_HISTORY, text)

    def _retranscribe_entry(self, entry_id: str):
        """Its recording transcribed again, with today's vocabulary (in the transcription worker, after any
        dictation in progress)."""
        entry = self.history.get(entry_id)
        if entry is None or not entry.recording:
            return
        if self.server_state != "ready":
            self._history_changed(entry_id, "Rozpoznávání řeči ještě není připravené, zkus to za chvilku.")
            return
        wav = config.RECORDINGS_DIR / f"{entry.recording}.wav"
        prompt, replacements = build_prompt(self.cfg["vocabulary"]), list(self.cfg["replacements"])
        commands = self.cfg["voice_commands"] and not entry.instruction

        def run():
            try:
                with wave.open(str(wav), "rb") as w:
                    audio = np.frombuffer(w.readframes(w.getnframes()), np.int16)
                raw = self.server.transcribe(audio, prompt)
                text = apply_replacements(clean_text(raw), replacements)
                if commands:
                    text = terminal_command(apply_voice_commands(text))[0]
                self.bridge.retranscribed.emit(entry_id, {"text": text, "raw": raw.strip()})
            except Exception as e:
                log.warning("Nový přepis nahrávky selhal: %s", e)
                self.bridge.retranscribed.emit(entry_id, {"error": str(e)})
        self._submit(run)

    def _retranscribed(self, entry_id: str, result: dict):
        entry = self.history.get(entry_id)
        if entry is None:
            return
        if result.get("error"):
            self._history_changed(entry_id, f"Přepis se nepovedl: {result['error']}")
            return
        same = result["text"].strip() == entry.text.strip()
        self.history.update(entry, text=result["text"].strip(), raw=result["raw"], corrected="")
        self._history_changed(entry_id, "Přepsáno znovu, vyšlo to stejně." if same else "Přepsáno znovu.")

    # -- Claude Code sessions ---------------------------------------------------------------

    def _apply_sessions_setting(self):
        """The session overview and reading artifacts aloud both need Orbit's hooks in Claude Code, which are added
        only with the user's yes (claude_hooks) and only while Claude Code is connected. Not connected (or not
        checked yet): the hooks aren't touched either way and nothing is polled."""
        on = self.cfg["claude_hooks"] and (self.cfg["show_sessions"] or self.cfg["read_artifacts"])
        if not self.claude.connected or (on and not paths.claude_dir().is_dir()):  # never create Claude's folder
            on = False
        elif self._cfg_doubtful and not on:
            pass  # a "no" only because config.json couldn't be read: the hooks stay as they are
        else:
            try:
                if claude_settings.set_hooks(on) and on:
                    self._notify("Orbit se napojil na Claude Code: přehled relací a čtení artefaktů.")
            except claude_settings.SettingsError as e:
                self._notify(str(e), error=True)
            except Exception as e:
                log.exception("Úprava hooků Claude Code selhala")
                self._notify(f"Nepodařilo se upravit nastavení Claude Code: {e}", error=True)
        if on:
            self.session_timer.start()
            self._poll_sessions()
        else:
            self.session_timer.stop()
        if not (on and self.cfg["show_sessions"]):
            self.button.set_sessions([])
            self.button.set_attention(False)
            # no overview, no colours: the windows Orbit tinted get their own background back
            tinted, self._tinted = [(pid, None) for pid, bg in self._tinted.items() if bg], {}
            if tinted:
                colors.tint_sessions(tinted)

    def _poll_sessions(self):
        for pub in artifacts.take_new():
            if not self.cfg["read_artifacts"]:
                artifacts.done(pub)
                continue
            log.info("Relace ve složce %s zveřejnila artefakt", pub.name)
            log.debug("Artefakt %s (%s)", pub.url or "?", pub.path)
            # a daemon thread: quitting Orbit mustn't wait for Claude
            threading.Thread(target=self._summarize_artifact, args=(pub,), daemon=True).start()
        if not self.cfg["show_sessions"]:
            return
        changes = self.tracker.poll()
        current = sorted(self.tracker.sessions.values(), key=lambda s: (s.folder.lower(), s.started))
        self.button.set_sessions(current)
        self.button.set_attention(any(s.state == "waiting" for s in current))
        self._tint_sessions(current)
        for s, state in changes:
            self._session_changed(s, state)

    def _tint_sessions(self, current: list[sessions.Session]):
        """Each session's terminal background in its folder's colour (tint_sessions), once per session and colour;
        switched off, the ones Orbit tinted get their own background back. A new session gets it within a second."""
        pairs = []
        for s in current:
            if not s.pid:
                continue
            color = colors.color_for(s.cwd or s.folder, self.cfg["folder_colors"])
            want = colors.shade(color) if self.cfg["tint_sessions"] else None
            if want != self._tinted.get(s.pid):
                pairs.append((s.pid, want))
                self._tinted[s.pid] = want
        alive = {s.pid for s in current}
        self._tinted = {pid: bg for pid, bg in self._tinted.items() if pid in alive}
        if pairs:
            try:
                colors.tint_sessions(pairs)
            except OSError:
                log.exception("Obarvení oken relací selhalo")

    def _show_folder_menu(self, folder: str, pos: QPoint):
        """A right click on a session in the panel: its folder's colour (the panel and, with tint_sessions, its
        terminals), then Orbit's own menu."""
        name, label = colors.key(folder), Path(folder).name or folder
        current = self.cfg["folder_colors"].get(name)
        menu = QMenu()
        title = menu.addAction(f"Barva složky {label}")
        title.setEnabled(False)
        for color, (czech, hex_) in colors.COLORS.items():
            action = menu.addAction(color_icon(hex_), czech)
            action.setCheckable(True)
            action.setChecked(color == current)
            action.triggered.connect(lambda _=False, c=color: self._set_folder_color(name, c))
        others = {k: v for k, v in self.cfg["folder_colors"].items() if k != name}
        auto = menu.addAction(f"Automaticky ({colors.COLORS[colors.color_for(name, others)][0]})")
        auto.setCheckable(True)
        auto.setChecked(current not in colors.COLORS)
        auto.triggered.connect(lambda: self._set_folder_color(name, None))
        menu.addSeparator()
        self.menu.setTitle("Orbit")
        menu.addMenu(self.menu)
        self._folder_menu = menu  # (kept while it's open)
        menu.popup(pos)

    def _set_folder_color(self, name: str, color: str | None):
        chosen = {k: v for k, v in self.cfg["folder_colors"].items() if k != name}
        if color:
            chosen[name] = color
        self.cfg["folder_colors"] = chosen
        config.save(self.cfg)
        log.info("Barva složky %s: %s", name, color or "automaticky")
        self.button.set_folder_colors(chosen)
        self._poll_sessions()  # its sessions' windows (and the automatic colours of the others) right away

    def _session_changed(self, s: sessions.Session, state: str):
        log.info("Relace ve složce %s: %s (tah %.0f s)", s.folder, state, s.turn_s)  # (the topic is content)
        if sessions.is_foreground(s):
            return  # Pepa is looking at it
        fallback = {"waiting": "Čeká na tvoji odpověď.", "error": "Claude skončil chybou.", "done": "Hotovo."}
        if state in ("waiting", "error") or (state == "done" and s.turn_s >= NOTIFY_TURN_S):
            self._notify(sessions.summary(s.message, 2) or fallback[state], title=s.name, kind=state,
                         note=sessions.STATE_LABELS[state], session_id=s.id)
        if state == "done" and s.turn_s >= NOTIFY_TURN_S:
            if self.cfg["speak_answers"]:
                self._speak(f"Hotovo: {s.name}. {sessions.summary(s.message, 2)}")

    def _focus_session(self, session_id: str):
        """Its window to the front as well as it goes (a terminal, an IDE); without a known window nothing happens."""
        s = self.tracker.sessions.get(session_id)
        if s and s.hwnd and not sessions.focus(s):
            log.info("Okno relace ve složce %s nejde přenést do popředí", s.folder)

    def _sessions_bypass(self) -> bool:
        """Do the user's sessions run without permission prompts (the agent may then send in that class)?"""
        tracked = list(self.tracker.sessions.values())
        return any(s.mode_class == "bypass" for s in tracked) or sessions.bypass_in_use(tracked)

    def _speak(self, text: str, wait: bool = False, kind: str = "", force: bool = False) -> bool:
        """Reads text aloud after whatever is being read now. While Pepa dictates it's dropped, or with `wait`
        read once he's done. kind: "artifact" (lights up the speaker button), "agent" (its chip glows) or "confirm"
        (the agent's question, see _ask_confirm); force: even when Orbit is muted (he asked for it).
        False when it won't be read at all (muted, a full-screen game, no Czech voice)."""
        if self.cfg["muted"] and not force:
            return False
        if self.recorder.active:
            if wait:
                QTimer.singleShot(1000, lambda: self._speak(text, wait, kind, force))
            return wait
        if not winutil.accepts_notifications():
            log.info("Nečtu nahlas: hra nebo prezentace na celou obrazovku")
            return False
        speaker = self._speaker()
        if speaker is None:  # no Czech voice here: Czech read by an English voice is gibberish
            if not self._no_voice_told:
                self._no_voice_told = True
                log.warning("Nečtu nahlas: žádný český hlas")
                self._notify(voice.missing_text(), title="Předčítání",
                             on_click=self._download_voice if voice.piper_installed() else None)
            return False
        # Not QTextToSpeech.enqueue: with the winrt engine two texts queued before it starts speaking (in the same
        # moment) drop the first one. The next text is said only once the previous one has finished.
        self._speech.append((text, kind))
        busy = speaker.speaking if speaker is self.piper else speaker.state() == QTextToSpeech.State.Speaking
        if not self._speaking or (not busy and time.monotonic() - self._said_at > 3):
            self._say_next()
        return True

    def _speaker(self):
        """The voice from settings: a local Piper voice (voice.PiperSpeaker), or Windows' Jakub (QTextToSpeech).
        Another one when that one isn't there; None when there's no Czech voice at all."""
        model = voice.effective(self.cfg["voice"])
        if model is None:
            return None
        if model != voice.JAKUB:
            if self.piper is None or self.piper.model != model:
                if self.piper:
                    self.piper.stop()
                self.piper = voice.PiperSpeaker(model)
                self.piper.finished.connect(lambda: QTimer.singleShot(0, self._say_next))
            return self.piper
        if self.tts is None:
            self.tts = QTextToSpeech("winrt")
            czech = next((v for v in self.tts.availableVoices() if v.locale().name() == "cs_CZ"), None)
            if czech:
                self.tts.setVoice(czech)
            self.tts.stateChanged.connect(self._speech_state)
            log.info("Předčítání: engine %s, hlas %s, hlasitost %.2f", self.tts.engine(),
                     czech.name() if czech else "výchozí (český nenalezen)", self.tts.volume())
        return self.tts

    def _say_next(self):
        self._speaking = bool(self._speech)
        text, kind = self._speech.pop(0) if self._speech else ("", "")
        self._reading_artifact = kind == "artifact"
        self.button.set_reading(self._reading_artifact)
        if kind in ("agent", "confirm"):
            self._set_agent_state("speaking")
        elif self._agent_state == "speaking":
            self._set_agent_state(self._agent_rest())
        speaker = self._speaker() if text else None
        if speaker:
            self._said_at = time.monotonic()
            log.info("Čtu nahlas (%d znaků)", len(text))
            log.debug("Čtu: %s", text)
            speaker.say(text)
        elif text:
            self._speaking = False

    def _speech_state(self, state):
        log.info("Předčítání: %s%s", state.name, f" – {self.tts.errorString()}" if state == QTextToSpeech.State.Error
                 else "")
        if state in (QTextToSpeech.State.Ready, QTextToSpeech.State.Error):
            # not right here: after stop() winrt ignores a say() made while it reports Ready
            QTimer.singleShot(0, self._say_next)

    def _stop_speech(self, artifacts_only: bool = False):
        """Silence now and forget what's queued (or only the artifact summaries; an answer after them still comes)."""
        self._speech = [s for s in self._speech if s[1] != "artifact"] if artifacts_only else []
        if self._reading_artifact or not artifacts_only:
            for speaker in (self.tts, self.piper):
                if speaker:
                    speaker.stop()

    def _prepare_voice(self):
        """A Piper voice loads its model in the background right away, so the first text doesn't wait for it.
        A chosen Piper voice that isn't here yet gets downloaded."""
        choice = self.cfg["voice"]
        if choice == voice.JAKUB:
            return
        if voice.piper_installed() and not voice.downloaded(choice):
            self.downloads.start(choice)
        if voice.effective(choice) not in (None, voice.JAKUB):
            self._speaker()

    def _download_voice(self):
        """The "no Czech voice" bubble was clicked: Jirka, the Piper voice offered then."""
        self.cfg["voice"] = voice.FALLBACK
        config.save(self.cfg)
        self._no_voice_told = False
        self.downloads.start(voice.FALLBACK)

    def _preview_voice(self, model: str):
        """The settings' "Poslechnout" button: a sample sentence in that voice (kept only if the settings are saved)."""
        self.cfg["voice"] = model
        self._stop_speech()
        self._speak(voice.PREVIEW, force=True)

    # -- artifacts read aloud ---------------------------------------------------------------

    def _summarize_artifact(self, pub: artifacts.Published):
        """Worker thread (tens of seconds)."""
        try:
            with self._summary_lock:
                summary = self.summarizer.summarize(pub)
        except Exception as e:
            log.warning("Souhrn artefaktu ze složky %s selhal: %s", pub.name, e,
                        exc_info=not isinstance(e, (claude_cli.ClaudeError, OSError)))
            self.bridge.artifact_failed.emit(pub, str(e))
            return
        finally:
            artifacts.done(pub)
        if summary:
            self.bridge.artifact_ready.emit(pub, summary)

    def _artifact_ready(self, pub: artifacts.Published, summary: artifacts.Summary):
        log.info("Souhrn artefaktu hotový (%d vět)", len(summary.sentences))
        log.debug("Souhrn artefaktu %s: %s – %s", pub.url or pub.path, summary.title, " ".join(summary.sentences))
        if not self.cfg["read_artifacts"]:
            return
        kind = "Aktualizovaný artefakt" if summary.updated else "Artefakt"
        session = self.tracker.sessions.get(pub.session_id)
        name = session.name if session else sessions.topic(pub.transcript) or pub.name
        self._artifact_speech = f"{kind} z relace {name}: {summary.title}. {' '.join(summary.sentences)}"
        self.reread_action.setEnabled(True)
        self._notify(" ".join(summary.sentences[:2]), title=summary.title, kind="done",
                     note=session.folder if session else pub.name, url=pub.url)
        self._speak(self._artifact_speech, wait=True, kind="artifact")

    def _artifact_failed(self, pub: artifacts.Published, msg: str):
        if self.cfg["read_artifacts"]:
            self._notify(f"Souhrn artefaktu {pub.title or pub.name} se nepovedl: {msg}", error=True, url=pub.url)

    def _reread_artifact(self):
        self._stop_speech()
        self._speak(self._artifact_speech, kind="artifact", force=True)

    def _toggle_mute(self):
        """The speaker button by the mic was clicked: no beeps, chimes or reading aloud (or all of them back)."""
        muted = self.cfg["muted"] = not self.cfg["muted"]
        config.save(self.cfg)
        log.info("Zvuky %s", "ztlumeny" if muted else "zapnuty")
        self.button.set_muted(muted)
        if muted:
            self._stop_speech()

    def _set_theme(self, name: str):
        """A colour dot above the panel was clicked."""
        self.cfg["theme"] = name
        config.save(self.cfg)
        log.info("Barva vzhledu: %s", name)
        theme.set_theme(name)
        theme.apply(QApplication.instance())
        self.icons = {s: mic_icon(s) for s in self.icons}
        self.edit_icons = {s: mic_icon(s, editing=True) for s in self.edit_icons}
        self._tray_look = None  # the new icon even in the same state
        self.button.update()
        if self.bubble:
            self.bubble.update()
        self.refresh()

    # -- voice agent ------------------------------------------------------------------------

    def _apply_agent_setting(self):
        """The agent (and its button, which it takes over system-wide) only while Claude is connected."""
        on = self.cfg["agent"] and bool(self.claude.connected) and self.cfg["agent_ptt"] != self.cfg["ptt"]
        self.button.set_agent(on, hotkey.binding_name(self.cfg["agent_ptt"]))
        self.ptt.ignore(self.cfg["agent_ptt"] if on else None)  # talking to the agent moves no cursor
        if on and self.agent_ptt is None:
            if self._agent_capture is not None:  # its button is being captured right now: back on after that
                return
            self.agent_ptt = hotkey.PushToTalk(self.cfg["agent_ptt"], self.bridge.agent_down.emit,
                                               self.bridge.agent_up.emit)
            self.agent_ptt.start()
        elif on:
            self.agent_ptt.set_binding(self.cfg["agent_ptt"])  # (changed in the settings)
        elif self.agent_ptt is not None:
            self.agent_ptt.stop()
            self.agent_ptt = None
            self.agent.stop()

    def _agent_down(self):
        """The agent's button (mouse back): hold = push-to-talk, a click = it listens until Pepa stops talking."""
        if self.recorder.active:
            if self.take and self.take.agent and self._hands_free:
                self._finish_recording()  # a second click: done talking
            return
        self._agent_pressed_at = time.monotonic()
        self.start_recording(for_agent=True)

    def _agent_up(self):
        if not (self.take and self.take.agent) or self._hands_free:
            return
        if time.monotonic() - self._agent_pressed_at < CLICK_S:
            self._listen_hands_free()
        else:
            self.stop_recording(for_agent=True)

    def _agent_clicked(self):
        """The agent's chip by the colour dots: like a click of its button."""
        if self.recorder.active:
            if self.take and self.take.agent and self._hands_free:
                self._finish_recording()
            return
        self.start_recording(for_agent=True)
        if self.take and self.take.agent:
            self._listen_hands_free()

    def _listen_hands_free(self):
        self._hands_free = True
        self.recorder.end_on_silence = True
        self.listen_timer.start()

    def _speech_over(self):
        if self._hands_free and self.take and self.take.agent and self.recorder.active:
            self._finish_recording()

    def _agent_heard(self, text: str, confirm_id=None):
        """What Pepa said to the agent: an answer to "Mám to poslat?" (only when the question was already in the
        panel when the recording started, confirm_id), or something for the agent."""
        text = text.strip()
        if self._confirm and text and self._confirm.get("kind") == "task" and confirm_id != self._confirm["id"]:
            # said before Orbit asked about a task: meant for the agent; the task waits for the next check
            self._drop_confirm("")
            if send := self._feed.get("send"):
                self._feed_update(send=dict(send, status="expired"))
        if self._confirm:
            if not text:
                self._set_agent_state(self._agent_rest())
            elif confirm_id is not None and confirm_id == self._confirm["id"]:
                self._feed_update(you=text)
                self._answer_confirm(text)
            else:  # started before the question came: it's no answer to it
                request, self._confirm = self._confirm, None
                self.confirm_timer.stop()
                log.info("Agent: věta začala dřív, než přišla otázka, nic neodchází")
                self.agent.resolve(request["id"], False, f"Uživatel začal mluvit dřív, než se otázka na potvrzení "
                                   f"ukázala, a řekl: „{text}“. Nic neodešlo. Reaguj na to a případně požádej "
                                   "o potvrzení znovu.")
                send = self._feed.get("send")
                self._feed_update(you=text, **({"send": dict(send, status="changed")} if send else {}))
                self._set_agent_state("thinking")
            return
        if not text:
            self._feed_update(you="…", reply="Nic jsem nezachytil.", send=None)
            self._set_agent_state(self._agent_rest())
            return
        self._feed_update(you=text, reply="", send=None)
        if not self.cfg["show_sessions"]:
            self.tracker.poll()  # the overview doesn't keep it current then
        current = sorted(self.tracker.sessions.values(), key=lambda s: (s.folder.lower(), s.started))
        try:
            self.agent.ask(agent.context(current, text, self.cfg["name"]))
        except Exception as e:
            log.exception("Agentovi nejde nic poslat")
            self._feed_update(reply=f"Agent nejde spustit: {e}")
            self._set_agent_state(self._agent_rest())
            return
        self._set_agent_state("thinking")

    def _agent_event(self, kind: str, data):
        if kind == "reply":
            log.info("Agent odpověděl (%d znaků)", len(data))
            log.debug("Agent říká: %s", data)
            self._feed_update(reply=data)
            self._speak(data, kind="agent")
        elif kind == "confirm":
            self._ask_confirm(data)
        elif kind == "page":  # opens straight away, nothing to confirm: just show which page
            host = data["url"].split("://", 1)[-1].removeprefix("www.")
            log.info("Agent otevírá v Chromu stránku z %s", host.split("/")[0])
            log.debug("Stránka %s (%s)", data["url"], data["title"])
            self._feed_update(send={"tool": "page", "name": data["title"] or host.split("/")[0], "folder": "Chrome",
                                    "message": host, "status": "opening", "session_id": ""})
        elif kind == "send_result":
            send = self._feed.get("send")
            if send and send.get("status") in ("sending", "opening"):
                done = "opened" if send.get("tool") in ("open", "page") else "sent"
                text = data["text"].lower()
                if send.get("tool") == "send" and "held" in text and "approv" in text:
                    done = "held"  # the session holds it for approval in its window (another permission class)
                log.info("Agent: %s %s", "stránka" if send.get("tool") == "page" else data["to"],
                         done if data["ok"] else "nepovedlo se")
                log.debug("Výsledek: %s", data["text"])
                self._feed_update(send=dict(send, status=done if data["ok"] else "failed"))
        elif kind == "done":
            if data["error"]:
                log.warning("Agent: chyba %s", data["error"])
                self._feed_update(reply=f"Chyba agenta: {sessions.summary(data['error'], 2, 200)}")
            if self._agent_state == "thinking":
                self._set_agent_state(self._agent_rest())
        elif kind in ("exit", "reset"):
            if self._confirm and self._confirm.get("kind") != "task":  # (a task's question isn't the agent's)
                self._confirm = None
                self.confirm_timer.stop()
                if send := self._feed.get("send"):
                    self._feed_update(send=dict(send, status="expired"))
            if kind == "exit" and self._agent_state in ("thinking", "confirm") and not self._confirm:
                self._feed_update(reply="Agent se ukončil, zkus to prosím znovu.")
                self._set_agent_state(self._agent_rest())

    @staticmethod
    def _readable(text: str) -> str:
        """The whole message as it's read out: Markdown marks dropped, an address as its server and the words of its
        path ("evil.example, cesta x install ps1"), so nothing in it goes unheard (the panel shows it whole)."""
        def address(m: re.Match) -> str:
            words = re.findall(r"[^\W_]+", m.group(2))
            return m.group(1).removeprefix("www.") + (f", cesta {' '.join(words)}," if words else "")
        text = re.sub(r"https?://([^\s/?#]+)(\S*)", address, text)
        return sessions.summary(text, 10_000, 1_000_000)

    @staticmethod
    def _unreadable(text: str) -> str:
        """Why a message can't be confirmed by voice ("" = it can): what's heard must be all that's sent."""
        if "```" in text:
            return ("Zpráva obsahuje blok kódu a ten nejde přečíst nahlas. Napiš ji prostým textem bez kódu a pošli "
                    "ji znovu ke schválení.")
        if re.search(r"\[[^\]]*\]\([^)]*\)", text):  # the link's target wouldn't be read out
            return ("Zpráva obsahuje odkaz v Markdownu a jeho cíl nejde přečíst nahlas. Napiš ji prostým textem "
                    "a pošli ji znovu ke schválení.")
        if any(unicodedata.category(c).startswith("C") and c != "\n" for c in text):  # zero-width, bidi, tags
            return ("Zpráva obsahuje neviditelné nebo řídicí znaky. Napiš ji obyčejným textem a pošli ji znovu "
                    "ke schválení.")
        if "(hlasem přes orbit)" in text.lower():  # what stood before it was never read out
            return ("Zpráva má „(hlasem přes Orbit)“ jinde než na začátku nebo s jiným jménem. Začni ji přesně "
                    "předepsanými slovy a pošli ji znovu ke schválení.")
        if len(text) > CONFIRM_MAX_CHARS or text.count("\n") > 6:
            return (f"Zpráva je na přečtení nahlas moc dlouhá. Zkrať ji pod {CONFIRM_MAX_CHARS} znaků (pár vět na "
                    "jednom řádku) a pošli ji znovu ke schválení.")
        return ""

    def _ask_confirm(self, data: dict):
        """The agent wants to send a message to a session or open a new one: show it, read all of it out and wait
        for Pepa's yes. What can't be read out whole, or a folder that isn't one of his, goes back to the agent."""
        if self._confirm:  # a second one while the first waits: the first is off
            self._drop_confirm("Mezitím přišel jiný požadavek, tohle neproběhlo.")
        if data["tool"] == "open":
            known, prompt = agent.known_folder(data["folder"]), agent.without_prefix(data["prompt"], self.agent.name)
            refused = self._unreadable(prompt) if known else \
                f"Složka {data['folder']} není v seznamu složek pro nové relace. Vezmi celou cestu ze seznamu."
            label = agent.folder_label(known) if known else Path(data["folder"]).name
            # the user's newest screenshot, when the agent wants one attached: Orbit picks it and names it in the
            # question, the agent never gives a path
            shot = agent.latest_screenshot() if (data.get("input") or {}).get("screenshot") else None
            if known and not refused and (data.get("input") or {}).get("screenshot") and not shot:
                refused = (f"Ve složce se snímky obrazovky ({agent.screenshots_folder()}) žádný není, relaci jsem "
                           "neotevřel. Řekni to uživateli: Výstřižky ho tam uloží, když mají zapnuté automatické "
                           "ukládání snímků.")
            log.info("Agent chce otevřít relaci v %s (zadání %d znaků%s)", data["folder"], len(prompt),
                     ", se snímkem obrazovky" if shot else "")
            log.debug("Zadání: %r", prompt)
            attached = f"snímek obrazovky z {agent.when(shot)}" if shot else ""
            send = {"tool": "open", "name": "nová relace", "folder": label, "status": "confirm",
                    "message": (prompt or "jen otevřít, bez zadání") + (f"\n+ {attached}" if shot else ""),
                    "session_id": ""}
            speech = f"Otevřu novou relaci ve složce {label}" + (
                f" se zadáním: {self._readable(prompt)}" if prompt else ".") + \
                (f" A přiložím poslední {attached}." if shot else "") + " Mám?"
            mode = ""
            # what goes out: the known folder, exactly the task that was read aloud and the screenshot it named
            # (agent_tools adds only that path)
            updated = dict(data.get("input") or {}, folder=known or data["folder"],
                           prompt=agent.with_prefix(prompt, self.agent.name))
            updated.pop("screenshot", None)
            if shot:
                updated["screenshot"] = str(shot)
        else:
            to = data["to"].split(" [")[0].strip()
            s = next((s for s in self.tracker.sessions.values() if s.peer == to), None)
            name, folder = (s.name, s.folder) if s else (to, "")
            folder = "" if folder == name else folder
            message = agent.without_prefix(data["message"], self.agent.name)
            # only a session in the overview (one on this PC that Pepa sees), with exactly what was read aloud
            refused = self._unreadable(message) if s else \
                f"Relace {to} není v přehledu relací na tomhle počítači. Vezmi adresu přesně z přehledu."
            updated = dict(data.get("input") or {}, message=agent.with_prefix(message, self.agent.name))
            log.info("Agent chce poslat do %s zprávu (%d znaků)", to, len(message))
            log.debug("Zpráva pro %s: %r", name, message)
            send = {"tool": "send", "name": name, "folder": folder, "message": message, "status": "confirm",
                    "session_id": s.id if s else ""}
            where = f"{name}, složka {folder}" if folder else name
            speech = f"Pošlu do relace {where}: {self._readable(message)}"
            # sent in the target's permission class, or the session would hold it for approval in its window; a
            # session that hasn't told its mode yet runs the way the user's sessions usually do
            target = s.mode_class if s else ""
            bypass = target == "bypass" or (not target and sessions.bypass_in_use(self.tracker.sessions.values()))
            mode = agent.BYPASS_MODE if bypass and self.agent.can_bypass else agent.DEFAULT_MODE
            if bypass and not self.agent.can_bypass:
                speech += " Relace běží bez ptaní na oprávnění, takže tam zpráva počká, až ji v jejím okně schválíš."
            speech += " Mám to poslat?"
        if refused:
            log.info("Agent: návrh vrácen (%s)", refused)
            self.agent.resolve(data["id"], False, refused)
            self._feed_update(send=dict(send, status="changed"))
            return
        self._confirm = dict(data, mode=mode, shown=time.monotonic(), updated=updated)
        self.confirm_timer.start()
        self._feed_update(send=send)
        self._set_agent_state("confirm")
        self._speak(speech, wait=True, kind="confirm")

    def _answer_confirm(self, text: str):
        request, self._confirm = self._confirm, None
        self.confirm_timer.stop()
        verdict = agent.confirmation(text)
        if request.get("kind") == "task":
            self._answer_task(request, verdict, text)
            return
        if verdict:
            self.agent.resolve(request["id"], True, mode=request.get("mode", ""),
                               updated_input=request.get("updated"))
            status = "sending"
        elif verdict is False:
            self.agent.resolve(request["id"], False, "Uživatel odeslání zrušil, nic neodešlo. Jen to krátce potvrď.")
            status = "cancelled"
        else:
            self.agent.resolve(request["id"], False, f"Místo potvrzení přišlo: „{text}“. Uprav podle toho zprávu "
                               "a pošli ji znovu ke schválení, nebo krátce odpověz.")
            status = "changed"
        log.info("Agent: odeslání %s", status)
        log.debug("Odpověď na potvrzení: %r", text)
        if send := self._feed.get("send"):
            self._feed_update(send=dict(send, status=status))
        self._set_agent_state("thinking")

    def _confirm_expired(self):
        if not self._confirm:
            return
        self._drop_confirm("Do dvou minut nepřišlo potvrzení, zpráva neodešla. Nic neříkej.")
        if send := self._feed.get("send"):
            self._feed_update(send=dict(send, status="expired"))
        self._set_agent_state(self._agent_rest())

    def _drop_confirm(self, reason: str):
        """The question waiting for the user's yes is off: the agent's tool gets a no with the reason; a task's
        question just goes (the task waits for the next check)."""
        request, self._confirm = self._confirm, None
        self.confirm_timer.stop()
        if request and request.get("kind") != "task":
            self.agent.resolve(request["id"], False, reason)
        elif request:  # nobody answered the task's question (or it had to go): asked again in a while
            self.tasks_timer.start(tasks.RETRY_MS)

    # -- the user's own tasks (notebook) -------------------------------------------------------

    def open_notebook(self):
        if self.notebook and self.notebook.isVisible():
            self.notebook.showNormal()
            self.notebook.raise_()
            self.notebook.activateWindow()
            return
        self.notebook = Notebook(self.tasks, agent.project_folders(), self.cfg["folder_colors"], self._next_check)
        self.notebook.changed.connect(self._tasks_changed)
        self.notebook.start_requested.connect(lambda task_id: self._check_tasks(task_id))
        self.notebook.show()

    def _next_check(self) -> str:
        """When the active tasks are looked at next ("10:30")."""
        if not self.tasks_timer.isActive():
            return ""
        at = time.localtime(time.time() + self.tasks_timer.remainingTime() / 1000)
        return f"{at.tm_hour}:{at.tm_min:02d}"

    def _tasks_changed(self):
        self.button.set_notes_count(sum(t.status == "active" for t in self.tasks))

    def _check_tasks(self, task_id: str = ""):
        """Every half hour (or "Začít teď", task_id): the first active task that hasn't run yet gets offered as a new
        session in its folder, after the user's yes (by voice through the agent, or a click on the bubble)."""
        asked = bool(task_id)
        if not asked:
            self.tasks_timer.start(tasks.CHECK_EVERY_MS)  # the half hour again (a sooner check is a one-off)
        task = next((t for t in self.tasks if t.id == task_id), None) if asked else tasks.next_to_offer(self.tasks)
        if not task:
            return
        if not self.claude.connected:
            if asked:
                self._notify("Úkol spustím, až bude Claude připojený (Nastavení › Claude).", error=True)
            return
        folder = agent.known_folder(task.folder)
        if not folder:
            if asked:
                self._notify(f"Složka {task.folder or '(žádná)'} není v seznamu složek Claude Code, úkol nemá kde "
                             "běžet. Vyber v poznámkách jinou.", error=True)
            return
        if self._confirm:  # another question waits for the user: this one comes a minute later
            if asked:
                self._notify("Nejdřív odpověz na otázku, která čeká, pak úkol začni znovu.")
            else:
                self.tasks_timer.start(tasks.NEXT_SOON_MS)
            return
        label = agent.folder_label(folder)
        title = task.title or "bez názvu"
        log.info("Úkol ve složce %s: nabízím spuštění", label)
        self._confirm = {"id": f"task-{task.id}-{time.monotonic()}", "kind": "task", "task": task.id,
                         "shown": time.monotonic()}
        self.confirm_timer.start()
        self._feed_update(you="", reply="", send={"tool": "task", "name": f"Úkol: {title}", "folder": label,
                                                  "message": "nová relace se zadáním úkolu", "status": "confirm",
                                                  "session_id": ""})
        self._set_agent_state("confirm")
        answer = " Klikni sem a začnu" + (", nebo řekni agentovi „jo“." if self.cfg["agent"] else ".")
        confirm_id = self._confirm["id"]
        self._notify(f"Otevřu pro něj novou relaci ve složce {label}.{answer}", kind="waiting", title=f"Úkol: {title}",
                     on_click=lambda: self._task_clicked(confirm_id))
        self._speak(f"{'Úkol' if asked else 'Aktivní úkol'}: {title}. Otevřu pro něj novou relaci ve složce {label}. "
                    "Mám?", wait=True, kind="confirm")

    def _task_clicked(self, confirm_id: str):
        """A click on the task's bubble: yes, while that question still waits."""
        if self._confirm and self._confirm["id"] == confirm_id:
            request, self._confirm = self._confirm, None
            self.confirm_timer.stop()
            self._answer_task(request, True, "")

    def _answer_task(self, request: dict, verdict: bool | None, text: str):
        task = next((t for t in self.tasks if t.id == request["task"]), None)
        if verdict and task:
            log.info("Úkol: spouštím")
            self._feed_update(send=dict(self._feed.get("send") or {}, status="opening"))
            self._set_agent_state(self._agent_rest())
            prompt, name = tasks.prompt_for(task), self.cfg["name"]
            threading.Thread(target=lambda: self.bridge.task_done.emit(
                task.id, *tasks.start_session(task.folder, prompt, name, task_id=task.id)), daemon=True).start()
            return
        if verdict is False and task:
            task.declined = time.time()  # not offered again by itself
            self._save_tasks()
            log.info("Úkol: odmítnut")
        # turned down: the next active one comes a minute later; no answer to it: this one again in a while
        self.tasks_timer.start(tasks.NEXT_SOON_MS if verdict is False else tasks.RETRY_MS)
        if send := self._feed.get("send"):
            self._feed_update(send=dict(send, status="cancelled" if verdict is False else "expired"))
        self._set_agent_state(self._agent_rest())
        if verdict is None and text:  # no answer to it ("a co m-tex?"): meant for the agent
            self._agent_heard(text)

    def _task_done(self, task_id: str, ok: bool, text: str):
        task = next((t for t in self.tasks if t.id == task_id), None)
        log.info("Úkol: relace %s", "otevřena" if ok else "nejde otevřít")
        if ok and task:
            # its session runs: off the active ones, into Hotovo (the session reports there through orbit-ukoly)
            task.started, task.status = time.time(), "done"
            self._save_tasks()
            self.tasks_timer.start(tasks.NEXT_SOON_MS)  # the next active task a minute later
        if send := self._feed.get("send"):
            self._feed_update(send=dict(send, status="opened" if ok else "failed"))
        if not ok:
            self._notify(text, error=True, title="Úkol se nespustil")

    def _check_inbox(self):
        """What the session of a task left in the inbox (the orbit-ukoly mod): its notes go to the task, "done"
        moves it to Hotovo with a bubble. Orbit stays the only writer of tasks.json."""
        applied = tasks.apply_inbox(self.tasks, tasks.read_inbox())
        if not applied:
            return
        log.info("Zprávy od relací k úkolům: %d", len(applied))
        self._save_tasks()
        for task, msg in applied:
            if msg["action"] == "done":
                self._notify(msg["text"] or "Relace úkol dokončila, je v Hotovo.", kind="done",
                             title=f"Hotovo: {task.title or 'úkol bez názvu'}", on_click=self.open_notebook)

    def _save_tasks(self):
        try:
            tasks.save(self.tasks)
        except OSError as e:
            log.exception("Úkoly nejde uložit")
            self._notify(f"Úkoly nejde uložit: {e}", error=True)
        if self.notebook and self.notebook.isVisible():
            self.notebook.refresh()
        self._tasks_changed()

    def _agent_rest(self) -> str:
        """What the agent's chip shows when it isn't listening or speaking."""
        return "confirm" if self._confirm else "thinking" if self.agent.busy else "idle"

    def _set_agent_state(self, state: str):
        self._agent_state = state
        self.refresh()

    def _feed_update(self, **changes):
        self._feed.update(changes)
        self._feed = {k: v for k, v in self._feed.items() if v}
        self.button.set_agent_feed(dict(self._feed))
        self.feed_timer.start()

    def _feed_expired(self):
        if self._agent_state != "idle":
            self.feed_timer.start()
            return
        self._feed = {}
        self.button.set_agent_feed(None)

    # -- self-improving vocabulary ----------------------------------------------------------

    def _maybe_learn(self, force: bool = False):
        """After every LEARN_EVERY new transcripts in the log or CORRECTIONS_EVERY corrections of the user's (or on
        request), let Claude extend the vocabulary."""
        if self._learning or (not force and (not self.cfg["learn_vocabulary"] or time.time() < self._learn_retry_at)):
            return
        if not self.claude.connected:
            if force:
                self._notify("Slovník se učí přes Clauda, a ten není připojený. Připojíš ho v nastavení (Claude).")
            return
        self._learning = True
        since = self.cfg["learned_until"]
        words, fixes = vocab.parse_words(self.cfg["vocabulary"]), list(self.cfg["replacements"])
        name, about = self.cfg["name"], self.cfg["about"]

        def run():
            try:
                new, corrections = learning.transcripts_since(since), learning.corrections_since(since)
                enough = (new or corrections) if force else (
                    len(new) >= learning.LEARN_EVERY or len(corrections) >= learning.CORRECTIONS_EVERY)
                if not enough:
                    self.bridge.learned.emit({"force": force, "count": len(new)})
                    return
                suggestion = learning.suggest([t for _, t in new], words, fixes, name, about, corrections)
                until = max([at for at, _ in new[-1:]] + [c["at"] for c in corrections])
                self.bridge.learned.emit({"force": force, "count": len(new), "corrections": len(corrections),
                                          "until": until, "suggestion": suggestion})
            except Exception as e:
                log.warning("Učení slovníku selhalo: %s", e, exc_info=not isinstance(e, claude_cli.ClaudeError))
                self.bridge.learn_failed.emit(str(e) if force else "")

        threading.Thread(target=run, daemon=True).start()

    def _learned(self, result):
        if self.dialog is not None:  # the settings dialog would overwrite the vocabulary on save
            QTimer.singleShot(5000, lambda: self._learned(result))
            return
        self._learning = False
        if "suggestion" not in result:
            if result["force"]:
                self._notify("Od posledního učení nepřibyly žádné diktáty.")
            return
        vocabulary, replacements, words, fixes = learning.merge(self.cfg["vocabulary"], self.cfg["replacements"],
                                                                result["suggestion"])
        self.cfg.update(vocabulary=vocabulary, replacements=replacements, learned_until=result["until"])
        config.save(self.cfg)
        log.info("Učení z %d diktátů a %d oprav: slovník + %s, opravy + %s", result["count"],
                 result.get("corrections", 0), words, fixes)
        lines = [f"Slovník: {', '.join(words)}"] if words else []
        lines += [f"Oprava: {w} → {r}" for w, r in fixes]
        if lines:
            self._notify("Naučil jsem se z diktátů\n" + "\n".join(lines))
        elif result["force"]:
            self._notify(f"Z {result['count']} nových diktátů není co se učit.")

    def _learn_failed(self, msg):
        self._learning = False
        self._learn_retry_at = time.time() + 3600
        if msg:
            self._notify(f"Učení slovníku selhalo: {msg}", error=True)

    # -- UI ---------------------------------------------------------------------------------

    def refresh(self):
        key = hotkey.binding_name(self.cfg["ptt"])
        for_agent = self.take is not None and self.take.agent
        pencil = False  # an edit: a pencil on the button instead of the microphone
        if self.recorder.live and not for_agent:
            pencil = self.take is not None and self.take.edit
            state, tip = "recording", ("Úprava textu: řekni, co s textem udělat, a pusť klávesu" if pencil else
                                       "Nahrávám… pusť klávesu a text se vloží")
        elif self.pending or self._rewriting:
            pencil = self.pending <= self._edit_pending
            state, tip = "busy", "Upravuji text podle pokynu…" if pencil else "Přepisuji…"
        elif self.server_state == "nomodel" and self.downloads.running(self.cfg["model"]):
            state = "loading"
            tip = f"Stahuji model pro rozpoznávání řeči… {self.downloads.percent(self.cfg['model'])} %"
        elif self.server_state == "nomodel":
            state, tip = "error", "Chybí model pro rozpoznávání řeči. Stáhneš ho v nastavení."
        elif self.server_state == "loading":
            state, tip = "loading", "Načítám model pro rozpoznávání řeči…"
        elif self.server_state == "error":
            state, tip = "error", "Rozpoznávání řeči neběží. Podrž klávesu a zkusím ho spustit znovu."
        else:
            state, tip = "idle", f"Drž {key} (nebo toto tlačítko) a mluv"
        self.button.set_state(state, pencil)
        self.button.set_button_tip(tip)
        self.button.set_agent_state("listening" if self.recorder.live and for_agent else self._agent_state)
        tray_tip = f"Orbit – {tip}"
        if self.cfg["show_usage"] and self.usage and self.usage.limits:
            tray_tip += "\nClaude: " + " · ".join(f"{lim.label} {lim.percent:.0f} %" for lim in self.usage.limits)
        if getattr(self, "_tray_look", None) != (state, pencil, tray_tip[:127]):  # each is a round trip to Explorer
            self._tray_look = (state, pencil, tray_tip[:127])
            self.tray.setIcon(self.edit_icons[state] if pencil else self.icons[state])
            self.tray.setToolTip(tray_tip[:127])
        self.hint_action.setText(f"Mluvení: drž {key}")

    def _notify(self, msg, error=False, title="Orbit", kind=None, note="", session_id=None, url="", on_click=None):
        """Orbit's bubble at the mic button, with Orbit's sound. kind: 'done', 'waiting', 'error' or 'info'
        (default from `error`); note: small text right of the title; session_id: a click switches to it;
        url: a click opens it; on_click: called on a click."""
        kind = kind or ("error" if error else "info")
        if not winutil.accepts_notifications():  # full-screen game or presentation: Windows holds it for later
            icon = QSystemTrayIcon.Warning if kind == "error" else QSystemTrayIcon.Information
            self.tray.showMessage(title, msg, icon, 6000)
            return
        if self.bubble:
            self.bubble.dismiss()
        bubble = self.bubble = Bubble(kind, title, msg, note)
        if on_click:
            bubble.clicked.connect(on_click)
        elif session_id:
            bubble.clicked.connect(lambda: self._focus_session(session_id))
        elif url.startswith("https://claude.ai/"):  # an artifact (the URL comes from a hook file: nothing else)
            bubble.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        bubble.closed.connect(lambda: self._bubble_closed(bubble))
        if self.button.isVisible():
            self.button.set_held(True)
            self.button.wake()
            bubble.show_near(*self.button.bubble_anchor())
        else:
            bubble.show_near(None)
        if not self.cfg["muted"]:
            winutil.play(kind)

    def _bubble_closed(self, bubble):
        if self.bubble is bubble:
            self.bubble = None
            self.button.set_held(False)

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_settings()

    def _show_menu(self, pos: QPoint):
        self.menu.popup(pos)

    def _set_button_visible(self, visible: bool):
        self.cfg["show_button"] = visible
        config.save(self.cfg)
        if self.toggle_action.isChecked() != visible:
            self.toggle_action.setChecked(visible)
        self.button.setVisible(visible)

    def _place_button(self):
        """At the saved place when both circles fit on a screen there, pulled onto the screen when they stick out
        (another resolution, scaling or monitor layout), bottom right of the main screen the first time."""
        pos = self.cfg.get("button_pos")
        if pos:
            self.button.place_button(self._on_screen(QPoint(*pos)))
        else:
            geo = QGuiApplication.primaryScreen().availableGeometry()
            side = FloatingButton.DIAMETER + 2 * FloatingButton.MARGIN
            self.button.place_button(QPoint(geo.right() - side - 24, geo.bottom() - side - 24))

    def _on_screen(self, pos: QPoint) -> QPoint:
        """pos (the mic square's top left), moved so that both circles are on one screen."""
        rect = self.button.button_rect(pos)
        if any(s.availableGeometry().contains(rect) for s in QGuiApplication.screens()):
            return pos
        geo = (QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()).availableGeometry()
        left = min(max(rect.left(), geo.left()), geo.right() + 1 - rect.width())
        top = min(max(rect.top(), geo.top()), geo.bottom() + 1 - rect.height())
        return QPoint(left + pos.x() - rect.left(), top)

    def _watch_screens(self):
        """A monitor unplugged or the taskbar moved while Orbit runs: keep the button reachable (not saved, so it
        goes back to its place when the monitor is back)."""
        app = QGuiApplication.instance()
        check = lambda *_: QTimer.singleShot(500, self._keep_button_on_screen)
        app.screenAdded.connect(lambda s: (s.availableGeometryChanged.connect(check), check()))
        app.screenRemoved.connect(check)
        for s in QGuiApplication.screens():
            s.availableGeometryChanged.connect(check)

    def _keep_button_on_screen(self):
        pos = self.button.button_pos()
        fitted = self._on_screen(pos)
        if fitted != pos:
            log.info("Tlačítko bylo mimo obrazovku, přesouvám ho")
            self.button.place_button(fitted)

    def _button_moved(self, pos: QPoint):
        self.cfg["button_pos"] = [pos.x(), pos.y()]
        config.save(self.cfg)

    def _export_vocabulary(self):
        if self.dialog is not None:  # the settings hold the newest words, maybe not saved yet
            self.dialog.raise_()
            self.dialog.export_vocabulary()
            return
        path = export_vocabulary(None, self.cfg["vocabulary"], self.cfg["replacements"])
        if path:
            self._notify(f"Slovník je uložený v {path}. Na jiném počítači ho načteš v menu Orbitu: Importovat "
                         "slovník.", title="Slovník")

    def _import_vocabulary(self):
        if self.dialog is not None:  # it would overwrite the import on save: import into its fields instead
            self.dialog.raise_()
            self.dialog.import_vocabulary()
            return
        result = import_vocabulary(None, self.cfg["vocabulary"], self.cfg["replacements"])
        if result is None:
            return
        merged, message = result
        self.cfg.update(vocabulary=merged.vocabulary, replacements=merged.replacements)
        config.save(self.cfg)
        log.info("Import slovníku: + %d slov, + %d oprav, nevešlo se %d", len(merged.added_words),
                 len(merged.added_fixes), len(merged.left_out))
        if merged.left_out:  # the whole list, a bubble would cut it
            message_box(None, "Slovník je načtený, ale celý se nevešel.", message, warning=True)
        else:
            self._notify(message, title="Slovník", kind="done")

    def _mic_list(self) -> tuple[list[str], set]:
        """The microphones now (PortAudio re-initialized to see newly plugged ones, when no stream is open) and
        which of them are Bluetooth hands-free."""
        refresh = not self.recorder.active
        if refresh:
            self._stop_speech()
            refresh = self._release_sound_card(wait=3)
        if refresh:
            self.recorder.shutdown()  # PortAudio re-init needs the stream closed
        mics = input_devices(refresh=refresh)
        return mics, {m for m in (None, *mics) if is_bluetooth_handsfree(m)}

    def _release_sound_card(self, wait: float = 1) -> bool:
        """Before PortAudio is re-initialized (Recorder.may_refresh): Pa_Terminate frees every stream, Piper's playing
        one too, under its thread (a native crash). Piper stops and lets go first; False when it doesn't in time."""
        if self.piper is None:
            return True
        self.piper.stop()
        return self.piper.release(wait)

    def open_settings(self):
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        if self.wizard is not None:  # one window with the mic and the key capture at a time
            self.wizard.raise_()
            self.wizard.activateWindow()
            return
        mics, handsfree = self._mic_list()
        self.recorder.set_monitor(True)  # the live meter in settings – only while the window is open
        dlg = SettingsDialog(self.cfg, mics, config.available_models(), winutil.autostart_enabled(),
                             lambda: self.recorder.level, handsfree, self.claude, self.downloads)
        self.dialog = dlg
        dlg.mic_changed.connect(self.recorder.configure)
        dlg.voice_preview.connect(self._preview_voice)
        voice_before = self.cfg["voice"]
        dlg.capture_requested.connect(self._capture_key)
        dlg.binding_refused.connect(self.ptt.set_binding)
        dlg.agent_capture_requested.connect(self._capture_agent_key)
        self.bridge.captured.connect(dlg.on_captured)
        self.bridge.agent_captured.connect(dlg.on_agent_captured)
        self.claude.refresh()  # installed or logged in from a terminal since the last check
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        accepted = dlg.exec() == SettingsDialog.Accepted
        self.bridge.captured.disconnect(dlg.on_captured)
        self.bridge.agent_captured.disconnect(dlg.on_agent_captured)
        self.ptt.cancel_capture()
        self._end_agent_capture()
        self.recorder.set_monitor(False)
        self.dialog = None
        self._apply_agent_setting()  # its hook may have been paused for a capture
        if not accepted:
            self.cfg["voice"] = voice_before  # a voice only listened to
            self.ptt.set_binding(self.cfg["ptt"])  # capture already switched it – revert
            self.recorder.configure(self.cfg["mic"])
            return
        self._apply_values(dlg.values())

    def open_wizard(self, start: str = "welcome"):
        """The first-run wizard (also from the menu, and from "Připojit Clauda" in the panel: start="claude")."""
        if self.wizard is not None:
            self.wizard.raise_()
            self.wizard.activateWindow()
            return
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        mics, handsfree = self._mic_list()
        wizard = self.wizard = Wizard(self.cfg, mics, handsfree, lambda: self.recorder.level, self.claude,
                                      self.downloads, winutil.autostart_enabled(), self.cfg["wizard_pending"], start)
        wizard.mic_changed.connect(self.recorder.configure)
        wizard.monitor.connect(self.recorder.set_monitor)  # the mic is open only while its page is on screen
        wizard.model_chosen.connect(self._wizard_model)
        wizard.capture_requested.connect(self._capture_key)
        wizard.binding_refused.connect(self.ptt.set_binding)
        self.bridge.captured.connect(wizard.on_captured)
        wizard.finished.connect(self._wizard_closed)
        self.claude.refresh()
        log.info("Průvodce nastavením otevřen (%s)", start)
        wizard.show()
        wizard.raise_()
        wizard.activateWindow()

    # -- capturing a new key (settings, wizard) ---------------------------------------------

    def _capture_key(self):
        """The dictation's next key or button press becomes its new binding. The agent's hook is off meanwhile: as
        the newer hook it would see the press first and start listening instead."""
        self._pause_agent_key()
        self.ptt.capture(self.bridge.captured.emit)

    def _pause_agent_key(self):
        if self.agent_ptt is not None:
            self.agent_ptt.stop()
            self.agent_ptt = None  # _key_captured puts it back (_apply_agent_setting)

    def _key_captured(self, _binding=None):
        if self.dialog is None and self.wizard is None:
            return
        QTimer.singleShot(1500, self._resume_agent_key)  # after the captured key's release (swallowed by its hook)

    def _resume_agent_key(self):
        if self._agent_capture is not None:
            return  # _end_agent_capture puts it back
        if not self.ptt.released():  # another capture started meanwhile
            QTimer.singleShot(500, self._resume_agent_key)
            return
        self._apply_agent_setting()

    def _capture_agent_key(self):
        """Settings: the agent's new button. A hook of its own just for this (the dictation's would take the key as
        its own); stopped once the captured key is let go."""
        self._end_agent_capture()
        self._pause_agent_key()
        capture = self._agent_capture = hotkey.PushToTalk({"kind": "key", "code": -1}, lambda: None, lambda: None)
        capture.start()
        capture.capture(self.bridge.agent_captured.emit)

    def _agent_key_captured(self, _binding=None):
        self._agent_capture_wait = 0
        self._agent_capture_timer.start()

    def _poll_agent_capture(self):
        """Stops the capture hook once it has swallowed the release too (or after 10 s)."""
        capture = self._agent_capture
        self._agent_capture_wait += 1
        if capture is None or capture.released() or self._agent_capture_wait > 100:
            self._end_agent_capture()

    def _end_agent_capture(self):
        self._agent_capture_timer.stop()
        capture, self._agent_capture = self._agent_capture, None
        if capture is not None:
            capture.stop()
            self._apply_agent_setting()

    def _wizard_model(self, model: str):
        """The wizard's model page was left: that model from now on, so the last page can try it out."""
        if model != self.cfg["model"]:
            self.cfg["model"] = model
            config.save(self.cfg)
            self._start_server()

    def _wizard_closed(self, _result=None):
        """Finished or closed early: what was set so far counts (consents only from the page that asks)."""
        wizard, self.wizard = self.wizard, None
        if wizard is None:
            return
        self.bridge.captured.disconnect(wizard.on_captured)
        self.ptt.cancel_capture()
        self.recorder.set_monitor(False)
        values = wizard.values()
        wizard.deleteLater()
        log.info("Průvodce nastavením zavřen")
        self.cfg["wizard_pending"] = False
        self._apply_values(values)
        if self.server_state == "nomodel" and not self.downloads.running(self.cfg["model"]):
            self._notify(self._model_missing_text(), title="Rozpoznávání řeči")

    def _apply_values(self, values: dict):
        """New settings from the settings dialog or the wizard: save them and make them take effect."""
        self._cfg_doubtful = False  # the user's own choice now, also a "no"
        autostart = values.pop("autostart", None)
        if autostart is not None and autostart != winutil.autostart_enabled():
            try:
                winutil.set_autostart(autostart)
            except OSError as e:
                log.exception("Spouštění s Windows nejde nastavit")
                self._notify(f"Spouštění s Windows nejde nastavit: {e}", error=True)
        restart_server = values.get("model", self.cfg["model"]) != self.cfg["model"] or \
            self.server_state in ("nomodel", "error")
        if self.cfg["read_artifacts"] and not values.get("read_artifacts", True):
            self._stop_speech(artifacts_only=True)
        self.cfg.update(values)
        config.save(self.cfg)
        self.history.set_persist(self.cfg["keep_history"])
        self._history_changed()
        self.agent.name = self.cfg["name"]  # its next conversation uses it
        self.ptt.set_binding(self.cfg["ptt"])
        self.recorder.configure(self.cfg["mic"])
        self.recorder.split = self.cfg["live_transcribe"]
        self._set_button_visible(self.cfg["show_button"])
        self.button.set_fade_after(self.cfg["fade_after_s"])
        self._apply_usage_setting()
        self._apply_sessions_setting()
        self._apply_agent_setting()
        self._prepare_voice()
        if "model" in values and not config.model_present(self.cfg["model"]):
            self.downloads.start(self.cfg["model"])  # a model chosen but not here yet
        if restart_server:
            self._start_server()
        self.refresh()

    def shutdown(self):
        self.downloads.cancel_all()  # the .part files stay: the next start resumes them
        if self.take:
            self.take.cancelled = True
            self.take.drop_rewriter()
        # queued pieces would wait for a server that's gone and keep Orbit (and its single-instance mutex) alive
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.ptt.stop()
        if self.agent_ptt:
            self.agent_ptt.stop()
        self.agent.stop()
        self.recorder.shutdown()
        self.server.stop()
        self.tray.hide()


_crash_file = None  # kept open: faulthandler writes into it when the process dies in native code


def _setup_logging():
    """orbit.log in the data folder, at most ~3 MB (1 MB + 2 older ones). Vocabulary learning reads it back.
    What people said, read or opened is logged only as lengths (ORBIT_DEBUG=1: the texts too, at debug level).
    Every error ends up there: in Qt slots (Orbit keeps running), in threads, Qt's own warnings (debug level), and a
    crash in native code (PortAudio, Qt, a driver) writes every thread's Python stack to crash.log."""
    global _crash_file
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(config.LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    level = logging.DEBUG if os.environ.get("ORBIT_DEBUG") else logging.INFO
    logging.basicConfig(level=level, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("urllib3").setLevel(logging.INFO)  # one line per request at debug
    sys.excepthook = lambda *exc: log.critical("Neošetřená výjimka", exc_info=exc)
    threading.excepthook = lambda a: log.critical("Neošetřená výjimka ve vlákně %s", a.thread.name if a.thread else "?",
                                                  exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    sys.unraisablehook = lambda u: log.error("Výjimka, kterou nešlo předat dál (%s)", u.err_msg or u.object,
                                             exc_info=(u.exc_type, u.exc_value, u.exc_traceback))
    qt_log = logging.getLogger("qt")
    qInstallMessageHandler(lambda mode, context, message: qt_log.log(
        logging.CRITICAL if mode == QtMsgType.QtFatalMsg else logging.DEBUG, "%s", message))
    try:
        _crash_file = open(config.DATA_DIR / "crash.log", "a", encoding="utf-8")
        faulthandler.enable(_crash_file, all_threads=True)
    except OSError:
        log.warning("crash.log nejde otevřít, pád v nativním kódu nebude zapsaný")


def main():
    _setup_logging()
    winutil.set_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Orbit")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(mic_icon("idle"))
    theme.apply(app)
    if winutil.already_running():
        QMessageBox.information(None, "Orbit", "Orbit už běží – najdeš ho v oznamovací oblasti vedle hodin.")
        return
    log.info("Start Orbit %s (data: %s)", VERSION, config.DATA_DIR)
    try:
        dictation = Dictation()
    except Exception as e:
        log.exception("Orbit se nespustil")
        message_box(None, "Orbit se nespustil.", f"{e}\n\nPodrobnosti jsou v {config.LOG_PATH}", warning=True)
        return
    app.aboutToQuit.connect(dictation.shutdown)
    app.exec()
    log.info("Konec")
