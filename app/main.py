import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import claude_usage, config, hotkey, theme, winutil
from .inserter import Inserter
from .recorder import Recorder, input_devices, is_silent
from .ui import FloatingButton, SettingsDialog, mic_icon
from .whisper_server import SAMPLE_RATE, WhisperServer, apply_voice_commands, build_prompt, clean_text, to_wav

log = logging.getLogger("orbit")

TAIL_MS = 250  # keep recording a moment after release – people let go while finishing the last word
KEEP_RECORDINGS = 30
LIVE_FALLBACK_MS = 600  # if the mic sends only exact zeros (e.g. muted), start anyway after this
USAGE_REFRESH_MS = 120_000


class Bridge(QObject):
    """Signals used to hop from hook/worker threads into the Qt main thread."""
    ptt_down = Signal()
    mic_live = Signal()
    ptt_up = Signal()
    captured = Signal(object)
    server_ready = Signal()
    server_failed = Signal(str)
    text_ready = Signal(str)
    transcribe_failed = Signal(str)
    usage_ready = Signal(object)
    usage_failed = Signal(str)


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

        self.bridge = Bridge()
        self.server = WhisperServer()
        self.recorder = Recorder(on_live=self.bridge.mic_live.emit)
        self.recorder.configure(self.cfg["mic"])
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
        b.server_ready.connect(self._server_ready)
        b.server_failed.connect(self._server_failed)
        b.text_ready.connect(self._insert_text)
        b.transcribe_failed.connect(self._transcribe_failed)
        b.usage_ready.connect(self._usage_ready)
        b.usage_failed.connect(self._usage_failed)
        self.usage_timer = QTimer(interval=USAGE_REFRESH_MS)
        self.usage_timer.timeout.connect(self._fetch_usage)

        self.ptt = hotkey.PushToTalk(self.cfg["ptt"], b.ptt_down.emit, b.ptt_up.emit)
        self.ptt.start()
        self._start_server()
        self._set_button_visible(self.cfg["show_button"])
        self._apply_usage_setting()
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
        self.refresh()

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
        if self.server_state == "error":
            self._notify("Rozpoznávání řeči neběží, zkus aplikaci restartovat.", error=True)
            return
        self.live_timer.start()
        try:
            self.recorder.start()
        except Exception as e:
            self.live_timer.stop()
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
        if self.recorder.active:
            self.recorder.stop()
            self.refresh()

    def _finish_recording(self):
        self.live_timer.stop()
        was_live = self.recorder.live
        audio = self.recorder.stop()
        if self.cfg["sounds"] and was_live:
            winutil.play("stop")
        if is_silent(audio):
            log.info("Nahrávka %.2f s je ticho nebo moc krátká – přeskakuji", len(audio) / 16000)
            self.refresh()
            return
        self.pending += 1
        self.refresh()
        self.executor.submit(self._transcribe_job, audio, build_prompt(self.cfg["vocabulary"]),
                             self.cfg["voice_commands"], self.cfg["keep_recordings"])

    def _transcribe_job(self, audio, prompt, voice_commands, keep):
        try:
            t0 = time.perf_counter()
            raw = self.server.transcribe(audio, prompt)
            text = clean_text(raw)
            if voice_commands:
                text = apply_voice_commands(text)
            log.info("Přepis %.1f s zvuku za %.2f s: %r", len(audio) / SAMPLE_RATE, time.perf_counter() - t0, text)
            if keep:
                self._save_recording(audio, raw)
            self.bridge.text_ready.emit(text)
        except Exception as e:
            log.exception("Přepis selhal")
            self.bridge.transcribe_failed.emit(str(e))

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

    def _insert_text(self, text):
        self.pending -= 1
        self.refresh()
        if not text:
            return
        if self.cfg["trailing_space"] and not text.endswith("\n"):
            text += " "
        try:
            self.inserter.insert(text, self.cfg["insert_mode"])
        except Exception as e:
            log.exception("Vložení textu selhalo")
            self._notify(f"Text se nepodařilo vložit: {e}", error=True)

    def _transcribe_failed(self, msg):
        self.pending -= 1
        self.refresh()
        self._notify(f"Přepis selhal: {msg}", error=True)

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

    def _notify(self, msg, error=False):
        icon = QSystemTrayIcon.Warning if error else QSystemTrayIcon.Information
        self.tray.showMessage("Orbit", msg, icon, 6000)

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
        self.recorder.set_monitor(True)  # the live meter in settings – only while the window is open
        dlg = SettingsDialog(self.cfg, mics, config.available_models(), winutil.autostart_enabled(),
                             self.first_run, lambda: self.recorder.level)
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
        self._set_button_visible(self.cfg["show_button"])
        self._apply_usage_setting()
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
