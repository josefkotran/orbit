import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

import numpy as np
from PySide6.QtCore import QObject, QPoint, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import artifacts, claude_cli, claude_usage, config, hotkey, learning, sessions, theme, winutil
from .inserter import Inserter
from .recorder import Recorder, input_devices, is_bluetooth_handsfree, is_silent
from .ui import Bubble, FloatingButton, SettingsDialog, mic_icon
from .whisper_server import (SAMPLE_RATE, WhisperServer, apply_replacements, apply_voice_commands, build_prompt,
                             clean_text, terminal_command, to_wav)

log = logging.getLogger("orbit")

TAIL_MS = 250  # keep recording a moment after release – people let go while finishing the last word
KEEP_RECORDINGS = 30
LIVE_FALLBACK_MS = 600  # if the mic sends only exact zeros (e.g. muted), start anyway after this
USAGE_REFRESH_MS = 120_000
SESSION_POLL_MS = 1000
NOTIFY_TURN_S = 20  # a finished turn is announced only if Claude worked at least this long (else Pepa watched it)
FORECAST_WARN = timedelta(minutes=60)  # warn when the 5-hour limit runs out sooner than this at the current pace
CONTEXT_CHARS = 150  # the end of the previous piece goes into the prompt; Whisper keeps only ~224 prompt tokens


class Take:
    """One push-to-talk recording. With live transcription it arrives in pieces cut at pauses, which are
    transcribed while the user keeps talking; the text is inserted once, after release."""

    def __init__(self, prompt: str):
        self.prompt = prompt
        self.audio: list[np.ndarray] = []
        self.raw: list[str] = []
        self.texts: list[str] = []
        self.spoken = False  # at least one piece wasn't silence
        self.cancelled = False
        self.error: str | None = None
        self.released_at = 0.0


class Bridge(QObject):
    """Signals used to hop from hook/worker threads into the Qt main thread."""
    ptt_down = Signal()
    mic_live = Signal()
    piece_ready = Signal()
    ptt_up = Signal()
    captured = Signal(object)
    server_ready = Signal()
    server_failed = Signal(str)
    text_ready = Signal(str, str)  # text, key to press after it ("send" / "stop" / "")
    transcribe_failed = Signal(str)
    usage_ready = Signal(object)
    usage_failed = Signal(str)
    learned = Signal(object)
    learn_failed = Signal(str)
    artifact_ready = Signal(object, object)  # artifacts.Published, artifacts.Summary
    artifact_failed = Signal(object, str)


class Dictation:
    def __init__(self):
        self.first_run = config.is_first_run()
        self.cfg = config.load()
        if self.first_run:
            config.save(self.cfg)
        self.server_state = "loading"
        self.pending = 0
        self.dialog: SettingsDialog | None = None
        self.usage: claude_usage.Usage | None = None
        self.usage_error: str | None = None
        self._usage_inflight = False
        self.take: Take | None = None
        self._learning = False
        self._learn_retry_at = 0.0

        self.bridge = Bridge()
        self.server = WhisperServer()
        self.recorder = Recorder(on_live=self.bridge.mic_live.emit, on_piece=self.bridge.piece_ready.emit)
        self.recorder.configure(self.cfg["mic"])
        self.recorder.split = self.cfg["live_transcribe"]
        self.live_timer = QTimer(singleShot=True, interval=LIVE_FALLBACK_MS)
        self.live_timer.timeout.connect(self.recorder.force_live)
        self.inserter = Inserter()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.stop_timer = QTimer(singleShot=True, interval=TAIL_MS)
        self.stop_timer.timeout.connect(self._finish_recording)

        self.icons = {s: mic_icon(s) for s in ("idle", "loading", "recording", "busy", "error")}
        self.button = FloatingButton(lambda: self.recorder.level)
        self.button.pressed.connect(self.start_recording)
        self.button.released.connect(self.stop_recording)
        self.button.cancelled.connect(self.cancel_recording)
        self.button.moved.connect(self._button_moved)
        self.button.menu_requested.connect(self._show_menu)
        self.bubble: Bubble | None = None
        self.button.session_clicked.connect(self._focus_session)
        self.button.reader_toggled.connect(self._toggle_reader)
        self.tracker = sessions.SessionTracker()
        self.session_timer = QTimer(interval=SESSION_POLL_MS)
        self.session_timer.timeout.connect(self._poll_sessions)
        self.tts: QTextToSpeech | None = None
        self._speech: list[tuple[str, bool]] = []  # (text, is an artifact) waiting to be read (see _speak)
        self._speaking = False
        self._reading_artifact = False  # what's being read now is an artifact summary
        self._said_at = 0.0
        self.summarizer = artifacts.Summarizer()
        self._summary_lock = threading.Lock()  # one artifact after another
        self._artifact_speech = ""  # the last artifact summary, for reading it again
        self._usage_samples: list[tuple[datetime, float]] = []
        self._samples_window = None  # resets_at of the 5-hour window the samples belong to
        self._forecast_warned = None  # the 5-hour window we already warned about
        self.button.set_usage_visible(self.cfg["show_usage"])
        self._place_button()

        self.menu = QMenu()
        self.hint_action = self.menu.addAction("")
        self.hint_action.setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction("Nastavení…", self.open_settings)
        self.toggle_action = QAction("Zobrazovat plovoucí tlačítko", self.menu, checkable=True)
        self.toggle_action.setChecked(self.cfg["show_button"])
        self.toggle_action.toggled.connect(self._set_button_visible)
        self.menu.addAction(self.toggle_action)
        self.menu.addAction("Obnovit využití Clauda", self._fetch_usage)
        self.menu.addAction("Naučit slovník z nových diktátů", lambda: self._maybe_learn(force=True))
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
        b.text_ready.connect(self._insert_text)
        b.transcribe_failed.connect(self._transcribe_failed)
        b.usage_ready.connect(self._usage_ready)
        b.usage_failed.connect(self._usage_failed)
        b.learned.connect(self._learned)
        b.learn_failed.connect(self._learn_failed)
        b.artifact_ready.connect(self._artifact_ready)
        b.artifact_failed.connect(self._artifact_failed)
        self.usage_timer = QTimer(interval=USAGE_REFRESH_MS)
        self.usage_timer.timeout.connect(self._fetch_usage)

        self.ptt = hotkey.PushToTalk(self.cfg["ptt"], b.ptt_down.emit, b.ptt_up.emit)
        self.ptt.start()
        self._start_server()
        self._set_button_visible(self.cfg["show_button"])
        self._apply_usage_setting()
        self._apply_sessions_setting()
        self.refresh()
        if self.first_run:
            QTimer.singleShot(0, self.open_settings)

    # -- whisper server ---------------------------------------------------------------------

    def _start_server(self):
        self.server_state = "loading"
        self.refresh()
        model = self.cfg["model"]

        def run():
            try:
                self.server.start(model)
                self.bridge.server_ready.emit()
            except Exception as e:
                log.exception("Start whisper serveru selhal")
                self.bridge.server_failed.emit(str(e))

        threading.Thread(target=run, daemon=True).start()

    def _server_ready(self):
        self.server_state = "ready"
        self.refresh()

    def _server_failed(self, msg):
        self.server_state = "error"
        self.refresh()
        self._notify(f"Rozpoznávání řeči se nespustilo: {msg}", error=True)

    # -- Claude usage -----------------------------------------------------------------------

    def _apply_usage_setting(self):
        self.button.set_usage_visible(self.cfg["show_usage"])
        if self.cfg["show_usage"]:
            if not self.usage_timer.isActive():
                self.usage_timer.start()
                self._fetch_usage()
        else:
            self.usage_timer.stop()

    def _fetch_usage(self):
        if self._usage_inflight:
            return
        self._usage_inflight = True

        def run():
            try:
                self.bridge.usage_ready.emit(claude_usage.fetch())
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

    def start_recording(self):
        if self.stop_timer.isActive():  # pressed again during the tail – just keep recording
            self.stop_timer.stop()
            return
        if self.recorder.active:
            return
        self._stop_speech()  # don't talk over (or into) a dictation
        if self.server_state == "error":
            self._notify("Rozpoznávání řeči neběží, zkus aplikaci restartovat.", error=True)
            return
        self.live_timer.start()
        self.take = Take(build_prompt(self.cfg["vocabulary"]))
        try:
            self.recorder.start()
        except Exception as e:
            self.live_timer.stop()
            self.take = None
            log.exception("Mikrofon nejde spustit")
            self._notify(f"Mikrofon nejde spustit: {e}", error=True)
            return
        self.refresh()

    def _mic_live(self):
        """Audio is really flowing now – only now tell the user to speak (beep + red button)."""
        self.live_timer.stop()
        if not self.recorder.active:
            return
        if self.cfg["sounds"]:
            winutil.play("start")
        self.refresh()

    def stop_recording(self):
        if self.recorder.active and not self.stop_timer.isActive():
            self.stop_timer.start()

    def cancel_recording(self):
        self.stop_timer.stop()
        self.live_timer.stop()
        if self.take:
            self.take.cancelled = True
            self.take = None
        if self.recorder.active:
            self.recorder.stop()
            self.recorder.pop_pieces()
            self.refresh()

    def _take_pieces(self):
        if self.take:
            for piece in self.recorder.pop_pieces():
                self._queue_piece(self.take, piece)

    def _queue_piece(self, take: Take, audio):
        take.audio.append(audio)
        if not is_silent(audio):
            take.spoken = True
            self.executor.submit(self._transcribe_piece, take, audio)

    def _finish_recording(self):
        self.live_timer.stop()
        was_live = self.recorder.live
        tail = self.recorder.stop()
        take, self.take = self.take, None
        if self.cfg["sounds"] and was_live:
            winutil.play("stop")
        for piece in self.recorder.pop_pieces():  # cut just before release, not picked up yet
            self._queue_piece(take, piece)
        self._queue_piece(take, tail)
        if not take.spoken:
            log.info("Nahrávka %.2f s je ticho nebo moc krátká – přeskakuji",
                     sum(map(len, take.audio)) / SAMPLE_RATE)
            self.refresh()
            return
        take.released_at = time.perf_counter()
        self.pending += 1
        self.refresh()
        self.executor.submit(self._finish_take, take, list(self.cfg["replacements"]), self.cfg["voice_commands"],
                             self.cfg["keep_recordings"])

    def _transcribe_piece(self, take: Take, audio):
        """Worker thread. Pieces of one take run in order, so the previous piece's text is known here."""
        if take.cancelled or take.error:
            return
        context = " ".join(take.texts)[-CONTEXT_CHARS:]
        try:
            raw = self.server.transcribe(audio, f"{take.prompt} {context}" if context else take.prompt)
        except Exception as e:
            log.exception("Přepis selhal")
            take.error = str(e)
            return
        text = clean_text(raw)
        if raw.strip() and not text:
            log.info("Přepis odfiltrován jako halucinace: %r", raw)
        take.raw.append(raw.strip())
        if text:
            take.texts.append(text)

    def _finish_take(self, take: Take, replacements, voice_commands, keep):
        """Worker thread, queued after all pieces of the take."""
        if take.error:
            self.bridge.transcribe_failed.emit(take.error)
            return
        text, key = apply_replacements(" ".join(take.texts), replacements), ""
        if voice_commands:
            text, key = terminal_command(apply_voice_commands(text))
        audio = np.concatenate(take.audio)
        log.info("Přepis %.1f s zvuku za %.2f s po puštění (kusů: %d): %r%s", len(audio) / SAMPLE_RATE,
                 time.perf_counter() - take.released_at, len(take.raw), text, f" + {key}" if key else "")
        if keep:
            self._save_recording(audio, " ".join(take.raw))
        self.bridge.text_ready.emit(text, key)

    @staticmethod
    def _save_recording(audio, text):
        try:
            config.RECORDINGS_DIR.mkdir(exist_ok=True)
            stem = config.RECORDINGS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
            stem.with_suffix(".wav").write_bytes(to_wav(audio))
            stem.with_suffix(".txt").write_text(text.strip(), encoding="utf-8")
            for old in sorted(config.RECORDINGS_DIR.glob("*.wav"))[:-KEEP_RECORDINGS]:
                old.unlink()
                old.with_suffix(".txt").unlink(missing_ok=True)
        except Exception:
            log.exception("Uložení nahrávky selhalo")

    def _insert_text(self, text, key):
        self.pending -= 1
        self.refresh()
        if not text and not key:
            return
        if text and self.cfg["trailing_space"] and not text.endswith("\n") and key != "send":
            text += " "
        try:
            if text:
                self.inserter.insert(text, self.cfg["insert_mode"])
            if key:
                self.inserter.press(key, after_text=text)
        except Exception as e:
            log.exception("Vložení textu selhalo")
            self._notify(f"Text se nepodařilo vložit: {e}", error=True)
        if text:
            self._maybe_learn()

    def _transcribe_failed(self, msg):
        self.pending -= 1
        self.refresh()
        self._notify(f"Přepis selhal: {msg}", error=True)

    # -- Claude Code sessions ---------------------------------------------------------------

    def _apply_sessions_setting(self):
        """The session overview and reading artifacts aloud both need Orbit's hooks in Claude Code."""
        self.button.set_reader(self.cfg["read_artifacts"])
        on = self.cfg["show_sessions"] or self.cfg["read_artifacts"]
        try:
            if sessions.set_hooks(on) and on:
                self._notify("Orbit se napojil na Claude Code: přehled relací a čtení artefaktů.")
        except Exception as e:
            log.exception("Úprava hooků Claude Code selhala")
            self._notify(f"Nepodařilo se upravit nastavení Claude Code: {e}", error=True)
        if on:
            self.session_timer.start()
            self._poll_sessions()
        else:
            self.session_timer.stop()
        if not self.cfg["show_sessions"]:
            self.button.set_sessions([])
            self.button.set_attention(False)

    def _poll_sessions(self):
        for pub in artifacts.take_new():
            if not self.cfg["read_artifacts"]:
                artifacts.done(pub)
                continue
            log.info("Relace %s zveřejnila artefakt %s (%s)", pub.name, pub.url or "?", pub.path)
            # a daemon thread: quitting Orbit mustn't wait for Claude
            threading.Thread(target=self._summarize_artifact, args=(pub,), daemon=True).start()
        if not self.cfg["show_sessions"]:
            return
        changes = self.tracker.poll()
        current = sorted(self.tracker.sessions.values(), key=lambda s: (s.folder.lower(), s.started))
        self.button.set_sessions(current)
        self.button.set_attention(any(s.state == "waiting" for s in current))
        for s, state in changes:
            self._session_changed(s, state)

    def _session_changed(self, s: sessions.Session, state: str):
        log.info("Relace %s: %s (tah %.0f s)", s.name, state, s.turn_s)
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
        s = self.tracker.sessions.get(session_id)
        if s and not sessions.focus(s):
            self._notify(f"Okno terminálu relace {s.name} se nepodařilo najít.")

    def _speak(self, text: str, wait: bool = False, artifact: bool = False):
        """Reads text aloud after whatever is being read now. While Pepa dictates it's dropped, or with `wait`
        read once he's done. artifact: an artifact summary (lights up the reading satellite)."""
        if self.recorder.active:
            if wait:
                QTimer.singleShot(1000, lambda: self._speak(text, wait, artifact))
            return
        if not winutil.accepts_notifications():
            log.info("Nečtu nahlas: hra nebo prezentace na celou obrazovku")
            return
        if self.tts is None:
            self.tts = QTextToSpeech("winrt")
            voice = next((v for v in self.tts.availableVoices() if v.locale().name() == "cs_CZ"), None)
            if voice:
                self.tts.setVoice(voice)
            self.tts.stateChanged.connect(self._speech_state)
            log.info("Předčítání: engine %s, hlas %s, hlasitost %.2f", self.tts.engine(),
                     voice.name() if voice else "výchozí (český nenalezen)", self.tts.volume())
        # Not QTextToSpeech.enqueue: with the winrt engine two texts queued before it starts speaking (in the same
        # moment) drop the first one. The next text is said only once the previous one has finished.
        self._speech.append((text, artifact))
        stuck = self.tts.state() != QTextToSpeech.State.Speaking and time.monotonic() - self._said_at > 3
        if not self._speaking or stuck:
            self._say_next()

    def _say_next(self):
        self._speaking = bool(self._speech)
        text, self._reading_artifact = self._speech.pop(0) if self._speech else ("", False)
        self.button.set_reading(self._reading_artifact)
        if text:
            self._said_at = time.monotonic()
            log.info("Čtu nahlas (%d znaků): %s", len(text), text[:80])
            self.tts.say(text)

    def _speech_state(self, state):
        log.info("Předčítání: %s%s", state.name, f" – {self.tts.errorString()}" if state == QTextToSpeech.State.Error
                 else "")
        if state in (QTextToSpeech.State.Ready, QTextToSpeech.State.Error):
            # not right here: after stop() winrt ignores a say() made while it reports Ready
            QTimer.singleShot(0, self._say_next)

    def _stop_speech(self, artifacts_only: bool = False):
        """Silence now and forget what's queued (or only the artifact summaries; an answer after them still comes)."""
        self._speech = [s for s in self._speech if not s[1]] if artifacts_only else []
        if self.tts and (self._reading_artifact or not artifacts_only):
            self.tts.stop()

    # -- artifacts read aloud ---------------------------------------------------------------

    def _summarize_artifact(self, pub: artifacts.Published):
        """Worker thread (tens of seconds)."""
        try:
            with self._summary_lock:
                summary = self.summarizer.summarize(pub)
        except Exception as e:
            log.warning("Souhrn artefaktu %s selhal: %s", pub.path, e,
                        exc_info=not isinstance(e, (claude_cli.ClaudeError, OSError)))
            self.bridge.artifact_failed.emit(pub, str(e))
            return
        finally:
            artifacts.done(pub)
        if summary:
            self.bridge.artifact_ready.emit(pub, summary)

    def _artifact_ready(self, pub: artifacts.Published, summary: artifacts.Summary):
        log.info("Souhrn artefaktu %s: %s – %s", pub.url or pub.path, summary.title, " ".join(summary.sentences))
        if not self.cfg["read_artifacts"]:
            return
        kind = "Aktualizovaný artefakt" if summary.updated else "Artefakt"
        session = self.tracker.sessions.get(pub.session_id)
        name = session.name if session else sessions.topic(pub.transcript) or pub.name
        self._artifact_speech = f"{kind} z relace {name}: {summary.title}. {' '.join(summary.sentences)}"
        self.reread_action.setEnabled(True)
        self._notify(" ".join(summary.sentences[:2]), title=summary.title, kind="done", note=pub.name, url=pub.url)
        self._speak(self._artifact_speech, wait=True, artifact=True)

    def _artifact_failed(self, pub: artifacts.Published, msg: str):
        if self.cfg["read_artifacts"]:
            self._notify(f"Souhrn artefaktu {pub.title or pub.name} se nepovedl: {msg}", error=True, url=pub.url)

    def _reread_artifact(self):
        self._stop_speech()
        self._speak(self._artifact_speech, artifact=True)

    def _toggle_reader(self):
        """The reading satellite by the mic button was clicked."""
        on = self.cfg["read_artifacts"] = not self.cfg["read_artifacts"]
        config.save(self.cfg)
        log.info("Předčítání artefaktů %s", "zapnuto" if on else "vypnuto")
        if not on:
            self._stop_speech(artifacts_only=True)
        self._apply_sessions_setting()

    # -- self-improving vocabulary ----------------------------------------------------------

    def _maybe_learn(self, force: bool = False):
        """After every LEARN_EVERY new transcripts in the log (or on request), let Claude extend the vocabulary."""
        if self._learning or (not force and (not self.cfg["learn_vocabulary"] or time.time() < self._learn_retry_at)):
            return
        self._learning = True
        since = self.cfg["learned_until"]
        words, fixes = learning.parse_words(self.cfg["vocabulary"]), list(self.cfg["replacements"])

        def run():
            try:
                new = learning.transcripts_since(since)
                if len(new) < (1 if force else learning.LEARN_EVERY):
                    self.bridge.learned.emit({"force": force, "count": len(new)})
                    return
                suggestion = learning.suggest([t for _, t in new], words, fixes)
                self.bridge.learned.emit({"force": force, "count": len(new), "until": new[-1][0],
                                          "suggestion": suggestion})
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
        log.info("Učení z %d diktátů: slovník + %s, opravy + %s", result["count"], words, fixes)
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
        if self.recorder.live:
            state, tip = "recording", "Nahrávám… pusť klávesu a text se vloží"
        elif self.pending:
            state, tip = "busy", "Přepisuji…"
        elif self.server_state == "loading":
            state, tip = "loading", "Načítám model pro rozpoznávání řeči…"
        elif self.server_state == "error":
            state, tip = "error", "Rozpoznávání řeči neběží"
        else:
            state, tip = "idle", f"Drž {key} (nebo toto tlačítko) a mluv"
        self.button.set_state(state)
        self.button.set_button_tip(tip)
        self.tray.setIcon(self.icons[state])
        tray_tip = f"Orbit – {tip}"
        if self.cfg["show_usage"] and self.usage and self.usage.limits:
            tray_tip += "\nClaude: " + " · ".join(f"{lim.label} {lim.percent:.0f} %" for lim in self.usage.limits)
        self.tray.setToolTip(tray_tip[:127])
        self.hint_action.setText(f"Mluvení: drž {key}")

    def _notify(self, msg, error=False, title="Orbit", kind=None, note="", session_id=None, url=""):
        """Orbit's bubble at the mic button, with Orbit's sound. kind: 'done', 'waiting', 'error' or 'info'
        (default from `error`); note: small text right of the title; session_id: a click switches to it;
        url: a click opens it."""
        kind = kind or ("error" if error else "info")
        if not winutil.accepts_notifications():  # full-screen game or presentation: Windows holds it for later
            icon = QSystemTrayIcon.Warning if kind == "error" else QSystemTrayIcon.Information
            self.tray.showMessage(title, msg, icon, 6000)
            return
        if self.bubble:
            self.bubble.dismiss()
        bubble = self.bubble = Bubble(kind, title, msg, note)
        if session_id:
            bubble.clicked.connect(lambda: self._focus_session(session_id))
        elif url:
            bubble.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        bubble.closed.connect(lambda: self._bubble_closed(bubble))
        if self.button.isVisible():
            self.button.set_held(True)
            self.button.wake()
            bubble.show_near(*self.button.bubble_anchor())
        else:
            bubble.show_near(None)
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
        pos = self.cfg.get("button_pos")
        if pos and any(s.availableGeometry().contains(QPoint(*pos)) for s in QGuiApplication.screens()):
            self.button.place_button(QPoint(*pos))
        else:
            geo = QGuiApplication.primaryScreen().availableGeometry()
            side = FloatingButton.DIAMETER + 2 * FloatingButton.MARGIN
            self.button.place_button(QPoint(geo.right() - side - 24, geo.bottom() - side - 24))

    def _button_moved(self, pos: QPoint):
        self.cfg["button_pos"] = [pos.x(), pos.y()]
        config.save(self.cfg)

    def open_settings(self):
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        refresh = not self.recorder.active
        if refresh:
            self.recorder.shutdown()  # PortAudio re-init (to see newly plugged mics) needs the stream closed
        mics = input_devices(refresh=refresh)
        handsfree = {m for m in (None, *mics) if is_bluetooth_handsfree(m)}
        self.recorder.set_monitor(True)  # the live meter in settings – only while the window is open
        dlg = SettingsDialog(self.cfg, mics, config.available_models(), winutil.autostart_enabled(),
                             self.first_run, lambda: self.recorder.level, handsfree)
        self.dialog = dlg
        dlg.mic_changed.connect(self.recorder.configure)
        dlg.capture_requested.connect(lambda: self.ptt.capture(self.bridge.captured.emit))
        self.bridge.captured.connect(dlg.on_captured)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        accepted = dlg.exec() == SettingsDialog.Accepted
        self.bridge.captured.disconnect(dlg.on_captured)
        self.ptt.cancel_capture()
        self.recorder.set_monitor(False)
        self.dialog = None
        self.first_run = False
        if not accepted:
            self.ptt.set_binding(self.cfg["ptt"])  # capture already switched it – revert
            self.recorder.configure(self.cfg["mic"])
            return

        values = dlg.values()
        if values.pop("autostart") != winutil.autostart_enabled():
            winutil.set_autostart(not winutil.autostart_enabled())
        model_changed = values["model"] != self.cfg["model"]
        self.cfg.update(values)
        config.save(self.cfg)
        self.ptt.set_binding(self.cfg["ptt"])
        self.recorder.configure(self.cfg["mic"])
        self.recorder.split = self.cfg["live_transcribe"]
        self._set_button_visible(self.cfg["show_button"])
        self._apply_usage_setting()
        self._apply_sessions_setting()
        if model_changed:
            self._start_server()
        self.refresh()

    def shutdown(self):
        self.ptt.stop()
        self.recorder.shutdown()
        self.server.stop()
        self.tray.hide()


def _setup_logging():
    handler = RotatingFileHandler(config.LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.excepthook = lambda *exc: log.critical("Neošetřená výjimka", exc_info=exc)
    threading.excepthook = lambda a: log.critical("Neošetřená výjimka ve vlákně %s", a.thread,
                                                  exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


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
    log.info("Start")
    dictation = Dictation()
    app.aboutToQuit.connect(dictation.shutdown)
    app.exec()
    log.info("Konec")
