"""
MADRAC-DUBBING Qt GUI — Main window with QUiLoader.

Pattern follows MADRAC-SUBS: .ui file loaded via QUiLoader, resource
loading works in both dev (file path) and frozen (PyInstaller) modes.
QDarkStyle dark theme applied on top of Fusion.
"""

import sys
import os
import logging
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject, QMetaObject
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QWidget,
    QLineEdit, QPushButton, QComboBox, QTextEdit, QProgressBar, QLabel,
)
from PySide6.QtUiTools import QUiLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resource loading — works in dev and frozen builds
# ---------------------------------------------------------------------------

def _ui_path() -> str:
    """Return the absolute path to ``main_window.ui``."""
    if getattr(sys, "frozen", False):
        return str(Path(sys._MEIPASS) / "madrac_dubbing" / "ui" / "main_window.ui")
    return str(Path(__file__).resolve().parent / "ui" / "main_window.ui")


# ---------------------------------------------------------------------------
# QThread worker — runs pipeline without blocking the UI
# ---------------------------------------------------------------------------

class PipelineWorker(QObject):
    finished = Signal(bool, str, object)  # success, error_message, job (with report)
    progress = Signal(int, str)           # percent, message
    log = Signal(str)

    def __init__(self, pipeline, job):
        super().__init__()
        self._pipeline = pipeline
        self._job = job

    def run(self):
        try:
            self._pipeline.on_progress = self._on_progress
            self._pipeline.on_log = self._on_log
            success = self._pipeline.process(self._job)
            err = self._job.error if hasattr(self._job, 'error') and self._job.error else ""
            self.finished.emit(success, err, self._job)
        except Exception as e:
            self.finished.emit(False, str(e), self._job)

    def _on_progress(self, job):
        self.progress.emit(job.progress_pct, job.message)

    def _on_log(self, msg):
        self.log.emit(msg)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """MADRAC-DUBBING main window with pipeline integration."""
    WINDOW_TITLE = "MADRAC Dubbing"

    def __init__(self, workspace_mgr=None, capabilities=None, mode="standalone"):
        super().__init__()
        self._workspace_mgr = workspace_mgr
        self._capabilities = capabilities
        self._mode = mode

        self._tts_engine = None
        self._pipeline = None
        self._thread = None
        self._worker = None

        self._load_ui()
        self._setup_connections()
        self._refresh_integration_status()
        self._init_tts_async()

    # -- UI loading -------------------------------------------------------

    def _load_ui(self):
        loader = QUiLoader()
        ui_file = _ui_path()
        if not Path(ui_file).exists():
            logger.warning("UI file not found: %s", ui_file)
            self._build_placeholder()
            return

        # The .ui file has QMainWindow as root. Loading it with *no* parent
        # creates a standalone QMainWindow shell. We extract its centralWidget
        # and reparent it to *our* QMainWindow.
        shell = loader.load(ui_file)
        if shell is None:
            raise RuntimeError(f"Failed to load UI: {ui_file}")

        self._ui = shell.centralWidget()
        if self._ui is None:
            raise RuntimeError(f"UI file {ui_file} has no centralWidget")

        self._ui.setParent(self)
        self.setCentralWidget(self._ui)
        shell.deleteLater()

        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(1000, 700)
        self._cache_widgets()

    def _build_placeholder(self):
        """Fallback when .ui file is missing."""
        widget = QWidget()
        from PySide6.QtWidgets import QVBoxLayout, QLabel
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("MADRAC Dubbing — UI file not found"))
        self.setCentralWidget(widget)
        self.setWindowTitle(self.WINDOW_TITLE)

    def _cache_widgets(self):
        """Store commonly accessed widgets for fast access."""
        ui = self._ui
        self._w = {}
        type_map = {
            "editVideoPath": QLineEdit,
            "editSrtPath": QLineEdit,
            "editOutputPath": QLineEdit,
            "btnBrowseVideo": QPushButton,
            "btnBrowseSrt": QPushButton,
            "btnBrowseOutput": QPushButton,
            "btnRefreshVoices": QPushButton,
            "btnPreviewVoice": QPushButton,
            "btnStartDubbing": QPushButton,
            "comboLanguage": QComboBox,
            "comboVoice": QComboBox,
            "textLog": QTextEdit,
            "progressBar": QProgressBar,
            "labelSubsStatus": QLabel,
            "labelDubbingStatus": QLabel,
            "labelAssistantStatus": QLabel,
            "labelRecognitionStatus": QLabel,
            "labelModeStatus": QLabel,
            "labelStatusInfo": QLabel,
        }
        for name, cls in type_map.items():
            w = ui.findChild(cls, name)
            if w is not None:
                self._w[name] = w

    # -- Connections ------------------------------------------------------

    def _setup_connections(self):
        browse_video = self._w.get("btnBrowseVideo")
        if browse_video:
            browse_video.clicked.connect(self._on_browse_video)
        browse_srt = self._w.get("btnBrowseSrt")
        if browse_srt:
            browse_srt.clicked.connect(self._on_browse_srt)
        browse_out = self._w.get("btnBrowseOutput")
        if browse_out:
            browse_out.clicked.connect(self._on_browse_output)
        refresh_btn = self._w.get("btnRefreshVoices")
        if refresh_btn:
            refresh_btn.clicked.connect(self._refresh_voices_async)
        preview_btn = self._w.get("btnPreviewVoice")
        if preview_btn:
            preview_btn.clicked.connect(self._preview_voice)
        start_btn = self._w.get("btnStartDubbing")
        if start_btn:
            start_btn.clicked.connect(self._start_dubbing)
        lang_combo = self._w.get("comboLanguage")
        if lang_combo:
            lang_combo.currentTextChanged.connect(self._on_language_changed)
        self._tts_initialised.connect(self._refresh_languages)

    # -- Integration status ----------------------------------------------

    def _refresh_integration_status(self):
        """Update module indicator labels."""
        modules = {"subs": False, "dubbing": True, "assistant": False, "recognition": False}
        if self._workspace_mgr:
            modules = self._workspace_mgr.discover_modules()
        elif self._capabilities:
            modules = {
                "subs": self._capabilities.subs,
                "dubbing": self._capabilities.dubbing_app,
                "assistant": self._capabilities.assistant_app,
                "recognition": self._capabilities.recognition_app,
            }
        self._set_module_status("labelSubsStatus", modules.get("subs", False))
        self._set_module_status("labelDubbingStatus", modules.get("dubbing", True))
        self._set_module_status("labelAssistantStatus", modules.get("assistant", False))
        self._set_module_status("labelRecognitionStatus", modules.get("recognition", False))
        mode_label = self._w.get("labelModeStatus")
        if mode_label:
            mode_label.setText(f"Mode: {self._mode}")

    def _set_module_status(self, label_name, available):
        label = self._w.get(label_name)
        if label:
            indicator = "🟢" if available else "🔴"
            name = label_name.replace("label", "").replace("Status", "")
            label.setText(f"{indicator} {name}")

    # -- TTS engine -------------------------------------------------------

    _tts_initialised = Signal()

    def _init_tts_async(self):
        """Initialise TTS engine in background thread."""
        def _init():
            try:
                from .tts.edge_tts import EdgeTTSEngine
                engine = EdgeTTSEngine()
                _ = engine.supported_languages
                self._tts_engine = engine
                self._tts_initialised.emit()
            except Exception as e:
                logger.warning("TTS init failed: %s", e)
        threading.Thread(target=_init, daemon=True).start()

    def _refresh_languages(self):
        combo = self._w.get("comboLanguage")
        if combo is None or self._tts_engine is None:
            return
        langs = self._tts_engine.supported_languages
        combo.clear()
        combo.addItems(langs)
        if "es" in langs:
            combo.setCurrentText("es")

    def _refresh_voices_async(self):
        threading.Thread(target=self._refresh_voices, daemon=True).start()

    def _refresh_voices(self):
        if self._tts_engine is None:
            return
        lang = self._w.get("comboLanguage")
        if lang is None:
            return
        lang_text = lang.currentText()
        if not lang_text:
            return
        voices = self._tts_engine.list_voices(lang_text)
        combo = self._w.get("comboVoice")
        if combo:
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(
                combo, "clear", Qt.ConnectionType.QueuedConnection
            )
            QMetaObject.invokeMethod(
                combo, "addItems", Qt.ConnectionType.QueuedConnection,
                voices
            )
            if voices:
                QMetaObject.invokeMethod(
                    combo, "setCurrentText", Qt.ConnectionType.QueuedConnection,
                    voices[0]
                )

    def _on_language_changed(self, lang):
        if lang and self._tts_engine:
            voices = self._tts_engine.list_voices(lang)
            combo = self._w.get("comboVoice")
            if combo:
                combo.clear()
                combo.addItems(voices)
                if voices:
                    combo.setCurrentText(voices[0])

    def _preview_voice(self):
        if self._tts_engine is None:
            return
        lang = self._w.get("comboLanguage")
        voice = self._w.get("comboVoice")
        if lang is None or voice is None:
            return
        lang_text = lang.currentText()
        voice_text = voice.currentText()
        if not voice_text:
            return
        def _do_preview():
            try:
                audio = self._tts_engine.preview_voice(lang_text, voice_text)
                fd, path = tempfile.mkstemp(suffix=".wav")
                with os.fdopen(fd, "wb") as f:
                    f.write(audio)
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
                os.unlink(path)
            except Exception as e:
                self._log(f"Preview failed: {e}")
        threading.Thread(target=_do_preview, daemon=True).start()

    # -- File browsing ----------------------------------------------------

    def _on_browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select video", "", "Video (*.mp4 *.mkv *.avi)"
        )
        if path:
            edit = self._w.get("editVideoPath")
            if edit:
                edit.setText(path)
            # Auto-suggest output
            out_edit = self._w.get("editOutputPath")
            if out_edit and not out_edit.text():
                p = Path(path)
                out_edit.setText(str(p.with_name(f"{p.stem}_dubbed.mkv")))

    def _on_browse_srt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SRT", "", "Subtitle (*.srt)"
        )
        if path:
            edit = self._w.get("editSrtPath")
            if edit:
                edit.setText(path)

    def _on_browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Output file", "", "Video (*.mkv *.mp4)"
        )
        if path:
            edit = self._w.get("editOutputPath")
            if edit:
                edit.setText(path)

    # -- Logging -----------------------------------------------------------

    def _log(self, msg):
        text_log = self._w.get("textLog")
        if text_log:
            text_log.append(msg)

    # -- Pipeline execution ------------------------------------------------

    def _start_dubbing(self):
        video = self._w.get("editVideoPath")
        srt = self._w.get("editSrtPath")
        output = self._w.get("editOutputPath")
        if not all([video, srt, output]):
            QMessageBox.warning(self, "Error", "Please select Video, SRT, and Output files.")
            return
        video_path = video.text()
        srt_path = srt.text()
        output_path = output.text()
        if not all([video_path, srt_path, output_path]):
            QMessageBox.warning(self, "Error", "Please select Video, SRT, and Output files.")
            return

        from .pipeline.models import DubbingJob, DubbingConfig
        from .pipeline.dubbing_pipeline import DubbingPipeline

        lang = self._w.get("comboLanguage")
        voice = self._w.get("comboVoice")
        language = lang.currentText() if lang else "es"
        voice_text = voice.currentText() if (voice and voice.currentText()) else "male"

        config = DubbingConfig(
            language=language,
            voice=voice_text,
            tts_engine="edge",
        )
        job = DubbingJob(
            job_id="qt-gui-job",
            video_path=Path(video_path),
            srt_path=Path(srt_path),
            output_path=Path(output_path),
            config=config,
        )

        # Disable start button
        start_btn = self._w.get("btnStartDubbing")
        if start_btn:
            start_btn.setEnabled(False)

        pipeline = DubbingPipeline()

        # Create thread and worker
        self._thread = QThread(self)
        self._worker = PipelineWorker(pipeline, job)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_pipeline_finished)
        self._worker.progress.connect(self._on_pipeline_progress)
        self._worker.log.connect(self._log)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._log("Starting dubbing...")
        self._thread.start()

    def _on_pipeline_progress(self, pct, msg):
        bar = self._w.get("progressBar")
        if bar:
            bar.setValue(pct)
        if msg:
            self._log(f"[{pct}%] {msg}")

    def _on_pipeline_finished(self, success, error, job):
        start_btn = self._w.get("btnStartDubbing")
        if start_btn:
            start_btn.setEnabled(True)
        bar = self._w.get("progressBar")
        if bar:
            bar.setValue(100 if success else 0)
        if success:
            self._log("Dubbing completed successfully!")
            self._log_sync_report(job)
        else:
            self._log(f"Dubbing failed: {error}")
            QMessageBox.critical(self, "Error", f"Dubbing failed:\n{error}")
        self._worker = None
        self._thread = None

    def _log_sync_report(self, job):
        """Log formatted sync diagnostics to the text log."""
        report = getattr(job, "report", None)
        if not report or not report.sync:
            return

        s = report.sync
        lines = ["", "── Sync Diagnostics ──", ""]
        lines.append(f"  🟢  {s.ok_count} OK")
        lines.append(f"  🟡  {s.stretched_count} Stretched")
        lines.append(f"  🔴  {s.truncated_count} Truncated")
        lines.append(f"  ⚪  {s.padded_count} Padded")
        lines.append("")
        lines.append(f"  Error medio:    {s.avg_error_ms} ms")
        lines.append(f"  Error máximo:   {s.max_error_ms} ms  ({s.max_error_pct}%)")
        lines.append(f"  Drift acumulado: {s.drift_ms} ms")
        lines.append("")

        worst = sorted(s.segments, key=lambda x: abs(x.error_ms), reverse=True)[:5]
        if worst:
            lines.append("  Top 5 segmentos con mayor error:")
            lines.append("  #     slot     TTS     error   acción")
            for seg in worst:
                icon = "🔴" if seg.action == "truncated" else ("🟡" if seg.action == "stretched" else "🟢")
                lines.append(
                    f"  {icon} #{seg.index:<3d}  "
                    f"{seg.slot_dur_ms:>5d}ms  {seg.tts_dur_ms:>5d}ms  "
                    f"{seg.error_ms:+5d}ms  {seg.action}"
                )

        if report.tts:
            t = report.tts
            lines.append("")
            lines.append(f"  TTS Cache:   {t.cache_hits} hits / {t.cache_misses} misses  ({t.hit_rate}%)")
            lines.append(f"  TTS Synth:   {t.synthesis_s}s")

        if report.performance:
            lines.append("")
            lines.append("  Stage Timings:")
            for st in report.performance.stage_timings:
                lines.append(f"    {st.stage:<20s}  {st.elapsed_s:>8.3f}s")

        for line in lines:
            self._log(line)


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------

def run_gui_qt():
    """Start the Qt application."""
    app = QApplication(sys.argv)

    # Apply QDarkStyle if available
    try:
        import qdarkstyle
        app.setStyle("Fusion")
        app.setStyleSheet(qdarkstyle.load_stylesheet())
    except ImportError:
        app.setStyle("Fusion")

    # Determine workspace and capabilities
    workspace_mgr = None
    capabilities = None
    mode = "standalone"
    try:
        from .workspace_manager import get_manager
        workspace_mgr = get_manager()
        from .integration_layer import capabilities as caps
        capabilities = caps
        from .integration_layer import current_mode
        mode = current_mode
    except Exception:
        pass

    window = MainWindow(workspace_mgr, capabilities, mode)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui_qt()
