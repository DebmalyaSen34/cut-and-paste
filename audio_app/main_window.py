from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from audio_app.audio_engine import (
    AudioEngineError,
    export_batch_segments,
    extract_waveform_peaks,
    merge_segments,
    probe_audio,
)
from audio_app.audio_player import AudioPlayer
from audio_app.export_dialog import ExportDialog
from audio_app.models import AudioMetadata, AudioSegment, ExportSettings
from audio_app.segment_panel import SegmentPanel
from audio_app.utils import (
    SUPPORTED_AUDIO_EXTENSIONS,
    ensure_cache_dir,
    format_timestamp,
    parse_timestamp,
)
from audio_app.waveform_widget import WaveformWidget


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)


class FunctionWorker(QRunnable):
    def __init__(self, fn: Callable[..., object], *args, **kwargs) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Audio Cutter & Merger")
        self.resize(1180, 780)
        self.setMinimumSize(850, 600)
        self.setAcceptDrops(True)

        self._audio_path: Path | None = None
        self._metadata: AudioMetadata | None = None
        self._peaks: list[tuple[float, float]] = []

        self._player = AudioPlayer(self)
        self._thread_pool = QThreadPool.globalInstance()
        ensure_cache_dir()

        self._setup_ui()
        self._setup_menus_and_shortcuts()
        self._connect_signals()
        self._update_ui_state()

    def _setup_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 8)
        main_layout.setSpacing(8)

        # 1. Top Header & File Info Bar
        top_bar = QHBoxLayout()

        self.btn_open = QPushButton("Open Audio File...")
        self.btn_open.setFixedHeight(32)
        self.btn_open.setStyleSheet("font-weight: bold; padding: 0 14px;")
        self.btn_open.clicked.connect(self._open_file_dialog)

        self.lbl_file_info = QLabel("No file loaded. Open or drag & drop an audio file.")
        self.lbl_file_info.setStyleSheet("color: #9999aa; font-size: 12px; margin-left: 8px;")

        # Volume control
        self.lbl_vol_icon = QLabel("🔊")
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(85)
        self.slider_volume.setFixedWidth(100)
        self.slider_volume.valueChanged.connect(self._on_volume_slider_changed)

        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.lbl_file_info)
        top_bar.addStretch()
        top_bar.addWidget(self.lbl_vol_icon)
        top_bar.addWidget(self.slider_volume)
        main_layout.addLayout(top_bar)

        # 2. Waveform & Timeline Area
        wave_box = QGroupBox("Timeline & Waveform")
        wave_layout = QVBoxLayout(wave_box)
        wave_layout.setContentsMargins(8, 8, 8, 8)
        wave_layout.setSpacing(6)

        # Waveform toolbar (Zoom & view controls)
        wave_tools = QHBoxLayout()
        wave_tools.setContentsMargins(0, 0, 0, 0)
        self.btn_zoom_in = QPushButton("Zoom In (+)")
        self.btn_zoom_in.setFixedWidth(90)
        self.btn_zoom_in.clicked.connect(lambda: self.waveform.zoom_in())

        self.btn_zoom_out = QPushButton("Zoom Out (-)")
        self.btn_zoom_out.setFixedWidth(90)
        self.btn_zoom_out.clicked.connect(lambda: self.waveform.zoom_out())

        self.btn_zoom_fit = QPushButton("Fit Entire File")
        self.btn_zoom_fit.setFixedWidth(100)
        self.btn_zoom_fit.clicked.connect(lambda: self.waveform.reset_view())

        wave_tools.addStretch()
        wave_tools.addWidget(self.btn_zoom_in)
        wave_tools.addWidget(self.btn_zoom_out)
        wave_tools.addWidget(self.btn_zoom_fit)
        wave_layout.addLayout(wave_tools)

        # Waveform Canvas
        self.waveform = WaveformWidget()
        wave_layout.addWidget(self.waveform)

        # In / Out Range Selection Bar
        range_bar = QHBoxLayout()
        range_bar.setContentsMargins(0, 4, 0, 0)

        self.btn_set_in = QPushButton("[ Set IN (I)")
        self.btn_set_in.setToolTip("Set selection Start point at current playhead position (I)")
        self.btn_set_in.clicked.connect(self._set_in_to_current)

        self.txt_in = QLineEdit("00:00:00.000")
        self.txt_in.setFixedWidth(110)
        self.txt_in.editingFinished.connect(self._on_txt_in_changed)

        self.btn_set_out = QPushButton("Set OUT (O) ]")
        self.btn_set_out.setToolTip("Set selection End point at current playhead position (O)")
        self.btn_set_out.clicked.connect(self._set_out_to_current)

        self.txt_out = QLineEdit("00:00:00.000")
        self.txt_out.setFixedWidth(110)
        self.txt_out.editingFinished.connect(self._on_txt_out_changed)

        self.lbl_selection_dur = QLabel("Selection: 00:00:00.000")
        self.lbl_selection_dur.setStyleSheet("font-weight: bold; color: #00b4d8; margin-left: 6px;")

        self.btn_preview_selection = QPushButton("▶ Audition Selection")
        self.btn_preview_selection.setToolTip("Play only the selected range (Space / Enter)")
        self.btn_preview_selection.clicked.connect(self._preview_current_selection)

        range_bar.addWidget(self.btn_set_in)
        range_bar.addWidget(self.txt_in)
        range_bar.addSpacing(6)
        range_bar.addWidget(self.btn_set_out)
        range_bar.addWidget(self.txt_out)
        range_bar.addWidget(self.lbl_selection_dur)
        range_bar.addStretch()
        range_bar.addWidget(self.btn_preview_selection)

        wave_layout.addLayout(range_bar)
        main_layout.addWidget(wave_box)

        # 3. Main Transport / Playback Controls
        transport_layout = QHBoxLayout()
        transport_layout.setContentsMargins(4, 2, 4, 2)

        self.btn_seek_back_5 = QPushButton("⏪ -5s")
        self.btn_seek_back_5.setFixedWidth(60)
        self.btn_seek_back_5.clicked.connect(lambda: self._player.seek_relative(-5.0))

        self.btn_seek_back_1 = QPushButton("◀ -1s")
        self.btn_seek_back_1.setFixedWidth(55)
        self.btn_seek_back_1.clicked.connect(lambda: self._player.seek_relative(-1.0))

        self.btn_play_pause = QPushButton("▶ Play")
        self.btn_play_pause.setMinimumWidth(100)
        self.btn_play_pause.setFixedHeight(34)
        self.btn_play_pause.setStyleSheet(
            "font-weight: bold; font-size: 13px; background-color: #2b9348; color: white;"
        )
        self.btn_play_pause.clicked.connect(self._player.toggle_play_pause)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setFixedWidth(65)
        self.btn_stop.clicked.connect(self._player.stop)

        self.btn_seek_fwd_1 = QPushButton("+1s ▶")
        self.btn_seek_fwd_1.setFixedWidth(55)
        self.btn_seek_fwd_1.clicked.connect(lambda: self._player.seek_relative(1.0))

        self.btn_seek_fwd_5 = QPushButton("+5s ⏩")
        self.btn_seek_fwd_5.setFixedWidth(60)
        self.btn_seek_fwd_5.clicked.connect(lambda: self._player.seek_relative(5.0))

        self.lbl_time_display = QLabel("00:00:00.000 / 00:00:00.000")
        self.lbl_time_display.setStyleSheet("font-family: monospace; font-size: 14px; font-weight: bold; margin-left: 14px;")

        transport_layout.addWidget(self.btn_seek_back_5)
        transport_layout.addWidget(self.btn_seek_back_1)
        transport_layout.addWidget(self.btn_play_pause)
        transport_layout.addWidget(self.btn_stop)
        transport_layout.addWidget(self.btn_seek_fwd_1)
        transport_layout.addWidget(self.btn_seek_fwd_5)
        transport_layout.addWidget(self.lbl_time_display)
        transport_layout.addStretch()

        main_layout.addLayout(transport_layout)

        # 4. Segments Management Panel
        self.segment_panel = SegmentPanel(self)
        main_layout.addWidget(self.segment_panel, stretch=1)

        # 5. Bottom Export & Status Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 4, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #888899;")

        self.btn_export = QPushButton("⚡ Export & Merge Audio...")
        self.btn_export.setFixedHeight(38)
        self.btn_export.setStyleSheet(
            "background-color: #0077b6; color: white; font-weight: bold; font-size: 13px; padding: 0 20px;"
        )
        self.btn_export.clicked.connect(self._open_export_dialog)

        bottom_bar.addWidget(self.lbl_status)
        bottom_bar.addWidget(self.progress_bar)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_export)

        main_layout.addLayout(bottom_bar)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _setup_menus_and_shortcuts(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        act_open = QAction("&Open Audio File...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._open_file_dialog)
        file_menu.addAction(act_open)

        act_export = QAction("&Export / Merge Audio...", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self._open_export_dialog)
        file_menu.addAction(act_export)

        file_menu.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")

        act_add_seg = QAction("&Add Current Selection as Segment", self)
        act_add_seg.setShortcut(QKeySequence("A"))
        act_add_seg.triggered.connect(self._add_current_selection_to_segments)
        edit_menu.addAction(act_add_seg)

        act_split = QAction("&Split at Playhead", self)
        act_split.setShortcut(QKeySequence("S"))
        act_split.triggered.connect(self._split_at_playhead)
        edit_menu.addAction(act_split)

        act_del_seg = QAction("&Delete Selected Segment", self)
        act_del_seg.setShortcut(QKeySequence.StandardKey.Delete)
        act_del_seg.triggered.connect(self.segment_panel.delete_selected)
        edit_menu.addAction(act_del_seg)

        # Playback Menu
        play_menu = menubar.addMenu("&Playback")

        act_play_pause = QAction("&Play / Pause", self)
        act_play_pause.setShortcut(QKeySequence(Qt.Key.Key_Space))
        act_play_pause.triggered.connect(self._player.toggle_play_pause)
        play_menu.addAction(act_play_pause)

        act_set_in = QAction("Set &In Point", self)
        act_set_in.setShortcut(QKeySequence("I"))
        act_set_in.triggered.connect(self._set_in_to_current)
        play_menu.addAction(act_set_in)

        act_set_out = QAction("Set &Out Point", self)
        act_set_out.setShortcut(QKeySequence("O"))
        act_set_out.triggered.connect(self._set_out_to_current)
        play_menu.addAction(act_set_out)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._player.seek_relative(-1.0))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._player.seek_relative(1.0))
        QShortcut(QKeySequence("Shift+Left"), self, lambda: self._player.seek_relative(-5.0))
        QShortcut(QKeySequence("Shift+Right"), self, lambda: self._player.seek_relative(5.0))
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, self._add_current_selection_to_segments)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, self._add_current_selection_to_segments)

    def _connect_signals(self) -> None:
        # Player signals
        self._player.position_changed.connect(self._on_player_position_changed)
        self._player.duration_changed.connect(self._on_player_duration_changed)
        self._player.playback_state_changed.connect(self._on_playback_state_changed)
        self._player.error_occurred.connect(self._show_error)

        # Waveform signals
        self.waveform.seek_requested.connect(self._player.seek_to)
        self.waveform.selection_changed.connect(self._on_waveform_selection_changed)

        # Segment panel signals
        self.segment_panel.btn_add_selection.clicked.connect(self._add_current_selection_to_segments)
        self.segment_panel.btn_split_playhead.clicked.connect(self._split_at_playhead)
        self.segment_panel.preview_requested.connect(self._player.play_range)
        self.segment_panel.segments_updated.connect(self.waveform.set_segments)
        self.segment_panel.segment_selected.connect(self._on_segment_table_selected)

    # --- Loading Audio ---

    def _open_file_dialog(self) -> None:
        file_filter = (
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma *.aiff *.mp4 *.mkv *.mov);;"
            "All Files (*.*)"
        )
        filename, _ = QFileDialog.getOpenFileName(self, "Open Audio File", "", file_filter)
        if filename:
            self.load_audio_file(Path(filename))

    def load_audio_file(self, path: Path) -> None:
        if not path.exists():
            self._show_error(f"File not found: {path}")
            return

        self.lbl_status.setText(f"Loading '{path.name}'...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate

        # Background probe & waveform extraction
        worker = FunctionWorker(self._load_audio_worker, path)
        worker.signals.finished.connect(self._on_audio_loaded)
        worker.signals.failed.connect(self._on_audio_load_failed)
        self._thread_pool.start(worker)

    def _load_audio_worker(self, path: Path) -> tuple[AudioMetadata, list[tuple[float, float]]]:
        metadata = probe_audio(path)
        peaks = extract_waveform_peaks(path, num_peaks=1800)
        return metadata, peaks

    @Slot(object)
    def _on_audio_loaded(self, result: tuple[AudioMetadata, list[tuple[float, float]]]) -> None:
        metadata, peaks = result
        self._audio_path = metadata.path
        self._metadata = metadata
        self._peaks = peaks

        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Loaded '{metadata.filename}' successfully.")

        # Update Header label
        info = (
            f"<b>{metadata.filename}</b> | "
            f"Duration: {metadata.duration_formatted} | "
            f"Codec: {metadata.codec.upper()} | "
            f"{metadata.sample_rate} Hz | "
            f"{'Stereo' if metadata.channels == 2 else f'{metadata.channels} Ch'} | "
            f"{metadata.bit_rate // 1000} kbps"
        )
        self.lbl_file_info.setText(info)

        # Update Player & Waveform
        self._player.load(metadata.path)
        self.waveform.set_audio(metadata.duration, peaks)

        # Clear previous segments
        self.segment_panel.clear_all()

        self._update_ui_state()

    @Slot(str)
    def _on_audio_load_failed(self, error_msg: str) -> None:
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Failed to load audio.")
        self._show_error(f"Could not load audio file:\n{error_msg}")

    # --- UI Interactions & Slots ---

    def _update_ui_state(self) -> None:
        has_audio = self._metadata is not None
        self.btn_play_pause.setEnabled(has_audio)
        self.btn_stop.setEnabled(has_audio)
        self.btn_seek_back_1.setEnabled(has_audio)
        self.btn_seek_back_5.setEnabled(has_audio)
        self.btn_seek_fwd_1.setEnabled(has_audio)
        self.btn_seek_fwd_5.setEnabled(has_audio)
        self.btn_zoom_in.setEnabled(has_audio)
        self.btn_zoom_out.setEnabled(has_audio)
        self.btn_zoom_fit.setEnabled(has_audio)
        self.btn_set_in.setEnabled(has_audio)
        self.btn_set_out.setEnabled(has_audio)
        self.txt_in.setEnabled(has_audio)
        self.txt_out.setEnabled(has_audio)
        self.btn_preview_selection.setEnabled(has_audio)
        self.segment_panel.setEnabled(has_audio)
        self.btn_export.setEnabled(has_audio)

    @Slot(float)
    def _on_player_position_changed(self, pos_sec: float) -> None:
        self.waveform.set_position(pos_sec)
        dur = self._metadata.duration if self._metadata else 0.0
        self.lbl_time_display.setText(f"{format_timestamp(pos_sec)} / {format_timestamp(dur)}")

    @Slot(float)
    def _on_player_duration_changed(self, dur_sec: float) -> None:
        pass

    @Slot(bool)
    def _on_playback_state_changed(self, is_playing: bool) -> None:
        if is_playing:
            self.btn_play_pause.setText("⏸ Pause")
            self.btn_play_pause.setStyleSheet(
                "font-weight: bold; font-size: 13px; background-color: #d90429; color: white;"
            )
        else:
            self.btn_play_pause.setText("▶ Play")
            self.btn_play_pause.setStyleSheet(
                "font-weight: bold; font-size: 13px; background-color: #2b9348; color: white;"
            )

    @Slot(float, float)
    def _on_waveform_selection_changed(self, start: float, end: float) -> None:
        self.txt_in.setText(format_timestamp(start))
        self.txt_out.setText(format_timestamp(end))
        dur = max(0.0, end - start)
        self.lbl_selection_dur.setText(f"Selection: {format_timestamp(dur)}")

    def _set_in_to_current(self) -> None:
        pos = self._player.current_position
        self.waveform.set_in_point(pos)

    def _set_out_to_current(self) -> None:
        pos = self._player.current_position
        self.waveform.set_out_point(pos)

    def _on_txt_in_changed(self) -> None:
        try:
            t = parse_timestamp(self.txt_in.text())
            self.waveform.set_in_point(t)
        except ValueError:
            pass

    def _on_txt_out_changed(self) -> None:
        try:
            t = parse_timestamp(self.txt_out.text())
            self.waveform.set_out_point(t)
        except ValueError:
            pass

    def _preview_current_selection(self) -> None:
        try:
            s = parse_timestamp(self.txt_in.text())
            e = parse_timestamp(self.txt_out.text())
            if e > s:
                self._player.play_range(s, e)
        except ValueError:
            pass

    def _add_current_selection_to_segments(self) -> None:
        if not self._metadata:
            return
        try:
            s = parse_timestamp(self.txt_in.text())
            e = parse_timestamp(self.txt_out.text())
            if e <= s:
                e = min(self._metadata.duration, s + 5.0)

            seg = self.segment_panel.add_segment(s, e)
            self.status_bar.showMessage(
                f"Added '{seg.name}' ({format_timestamp(seg.start)} - {format_timestamp(seg.end)})",
                3000,
            )
        except ValueError as err:
            self._show_error(f"Invalid timestamp selection: {err}")

    def _split_at_playhead(self) -> None:
        if not self._metadata:
            return
        cur_pos = self._player.current_position
        segments = self.segment_panel.get_segments()

        # Find which segment contains cur_pos
        for i, seg in enumerate(segments):
            if seg.start + 0.1 < cur_pos < seg.end - 0.1:
                # Split this segment into two!
                orig_end = seg.end
                seg.end = cur_pos
                seg_b = AudioSegment(
                    start=cur_pos,
                    end=orig_end,
                    name=f"{seg.name or 'Segment'} (Part 2)",
                    enabled=seg.enabled,
                )
                segments.insert(i + 1, seg_b)
                self.segment_panel.set_segments(segments)
                self.status_bar.showMessage(f"Split segment at {format_timestamp(cur_pos)}", 3000)
                return

        # If not inside a segment, split from current playhead to end of file as a new segment
        self.waveform.set_in_point(cur_pos)

    def _on_segment_table_selected(self, seg: AudioSegment) -> None:
        # Sync selection to waveform handles
        self.waveform.set_selection(seg.start, seg.end)

    def _on_volume_slider_changed(self, value: int) -> None:
        vol = value / 100.0
        self._player.set_volume(vol)
        self.lbl_vol_icon.setText("🔇" if value == 0 else ("🔉" if value < 50 else "🔊"))

    # --- Export Processing ---

    def _open_export_dialog(self) -> None:
        if not self._audio_path or not self._metadata:
            self._show_error("Please load an audio file first.")
            return

        segments = self.segment_panel.get_segments()
        active = [s for s in segments if s.enabled and s.duration > 0.01]
        if not active:
            self._show_error(
                "No active segments to export. Please add at least one segment using '+ Add Selection as Segment'."
            )
            return

        dlg = ExportDialog(self._audio_path, segments, self)
        if dlg.exec() == ExportDialog.DialogCode.Accepted:
            settings = dlg.get_export_settings()
            self._start_export(settings, active)

    def _start_export(self, settings: ExportSettings, segments: list[AudioSegment]) -> None:
        self.btn_export.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.lbl_status.setText(f"Exporting ({settings.mode})...")

        if settings.mode == "merge":
            worker = FunctionWorker(
                merge_segments,
                self._audio_path,
                segments,
                settings,
            )
        else:
            worker = FunctionWorker(
                export_batch_segments,
                self._audio_path,
                segments,
                settings.output_path,
                settings,
            )

        worker.signals.finished.connect(lambda res: self._on_export_finished(res, settings))
        worker.signals.failed.connect(self._on_export_failed)
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_export_finished(self, result: object, settings: ExportSettings) -> None:
        self.btn_export.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Export completed successfully!")

        if settings.mode == "merge":
            out_file = Path(result)
            msg = f"Merged audio saved successfully to:\n\n{out_file}"
        else:
            files = list(result)
            msg = f"Exported {len(files)} segments to folder:\n\n{settings.output_path}"

        reply = QMessageBox.information(
            self,
            "Export Complete",
            msg,
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )
        if reply == QMessageBox.StandardButton.Open:
            target_dir = settings.output_path if settings.mode == "batch" else settings.output_path.parent
            from app.common import reveal_in_file_manager
            reveal_in_file_manager(target_dir)

    @Slot(str)
    def _on_export_failed(self, err_msg: str) -> None:
        self.btn_export.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Export failed.")
        self._show_error(f"Export operation failed:\n\n{err_msg}")

    # --- Drag and Drop ---

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = Path(urls[0].toLocalFile())
                if path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            self.load_audio_file(path)
            event.acceptProposedAction()

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)
