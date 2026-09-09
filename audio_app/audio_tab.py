from __future__ import annotations

from html import escape
import shutil
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app.common import reveal_in_file_manager
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


class AudioCutterWidget(QWidget):
    status_message = Signal(str, int)  # message, timeout_ms

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        self._audio_path: Path | None = None
        self._metadata: AudioMetadata | None = None
        self._peaks: list[tuple[float, float]] = []
        self._load_generation = 0
        self._active_workers: set[FunctionWorker] = set()
        self._is_loading = False

        self._player = AudioPlayer(self)
        self._thread_pool = QThreadPool.globalInstance()
        self._cache_dir = ensure_cache_dir()

        self._setup_ui()
        self._connect_signals()
        self._update_ui_state()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 12)
        main_layout.setSpacing(12)

        # 1. Top Header & File Info Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        page_title = QLabel("Audio Editor")
        page_title.setObjectName("pageTitle")
        page_subtitle = QLabel("Shape a selection, arrange segments, and export one clean track.")
        page_subtitle.setObjectName("secondaryLabel")
        heading = QVBoxLayout()
        heading.setSpacing(1)
        heading.addWidget(page_title)
        heading.addWidget(page_subtitle)

        self.btn_open = QPushButton("Open Audio")
        self.btn_open.setProperty("role", "primary")
        self.btn_open.clicked.connect(self.open_file_dialog)

        self.lbl_file_info = QLabel("No file loaded. Open or drag & drop an audio file.")
        self.lbl_file_info.setObjectName("secondaryLabel")
        self.lbl_file_info.setMinimumWidth(0)
        self.lbl_file_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_file_info.setToolTip("Open an audio file or drop one anywhere in this window")

        # Volume control
        self.lbl_vol_icon = QLabel("Volume")
        self.lbl_vol_icon.setObjectName("secondaryLabel")
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(85)
        self.slider_volume.setFixedWidth(100)
        self.slider_volume.valueChanged.connect(self._on_volume_slider_changed)

        top_bar.addLayout(heading)
        top_bar.addSpacing(8)
        top_bar.addWidget(self.btn_open)
        top_bar.addStretch()
        top_bar.addWidget(self.lbl_vol_icon)
        top_bar.addWidget(self.slider_volume)
        main_layout.addLayout(top_bar)
        main_layout.addWidget(self.lbl_file_info)

        # 2. Waveform & Timeline Area
        wave_box = QGroupBox("Timeline")
        wave_layout = QVBoxLayout(wave_box)
        wave_layout.setContentsMargins(8, 8, 8, 8)
        wave_layout.setSpacing(6)

        # Waveform toolbar (Zoom & view controls)
        wave_tools = QHBoxLayout()
        wave_tools.setContentsMargins(0, 0, 0, 0)
        self.btn_zoom_in = QPushButton("Zoom In")
        self.btn_zoom_in.clicked.connect(lambda: self.waveform.zoom_in())

        self.btn_zoom_out = QPushButton("Zoom Out")
        self.btn_zoom_out.clicked.connect(lambda: self.waveform.zoom_out())

        self.btn_zoom_fit = QPushButton("Fit")
        self.btn_zoom_fit.setToolTip("Fit the entire file in the timeline")
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

        self.btn_set_in = QPushButton("Set In")
        self.btn_set_in.setToolTip("Set the selection start at the playhead (I)")
        self.btn_set_in.clicked.connect(self.set_in_to_current)

        self.txt_in = QLineEdit("00:00:00.000")
        self.txt_in.setFixedWidth(110)
        self.txt_in.editingFinished.connect(self._on_txt_in_changed)

        self.btn_set_out = QPushButton("Set Out")
        self.btn_set_out.setToolTip("Set the selection end at the playhead (O)")
        self.btn_set_out.clicked.connect(self.set_out_to_current)

        self.txt_out = QLineEdit("00:00:00.000")
        self.txt_out.setFixedWidth(110)
        self.txt_out.editingFinished.connect(self._on_txt_out_changed)

        self.lbl_selection_dur = QLabel("Selection: 00:00:00.000")
        self.lbl_selection_dur.setObjectName("accentLabel")

        self.btn_preview_selection = QPushButton("Audition Selection")
        self.btn_preview_selection.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_preview_selection.setToolTip("Play only the selected range")
        self.btn_preview_selection.clicked.connect(self.preview_current_selection)

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
        transport_layout.setContentsMargins(4, 0, 4, 0)
        transport_layout.setSpacing(7)

        self.btn_seek_back_5 = QPushButton("-5s")
        self.btn_seek_back_5.clicked.connect(lambda: self._player.seek_relative(-5.0))

        self.btn_seek_back_1 = QPushButton("-1s")
        self.btn_seek_back_1.clicked.connect(lambda: self._player.seek_relative(-1.0))

        self.btn_play_pause = QPushButton("Play")
        self.btn_play_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_play_pause.setMinimumWidth(90)
        self.btn_play_pause.setProperty("role", "primary")
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.btn_stop.clicked.connect(self._player.stop)

        self.btn_seek_fwd_1 = QPushButton("+1s")
        self.btn_seek_fwd_1.clicked.connect(lambda: self._player.seek_relative(1.0))

        self.btn_seek_fwd_5 = QPushButton("+5s")
        self.btn_seek_fwd_5.clicked.connect(lambda: self._player.seek_relative(5.0))

        self.lbl_time_display = QLabel("00:00:00.000 / 00:00:00.000")
        self.lbl_time_display.setObjectName("timeLabel")

        transport_layout.addWidget(self.btn_seek_back_5)
        transport_layout.addWidget(self.btn_seek_back_1)
        transport_layout.addWidget(self.btn_play_pause)
        transport_layout.addWidget(self.btn_stop)
        transport_layout.addWidget(self.btn_seek_fwd_1)
        transport_layout.addWidget(self.btn_seek_fwd_5)
        transport_layout.addStretch()
        transport_layout.addWidget(self.lbl_time_display)

        main_layout.addLayout(transport_layout)

        # 4. Segments Management Panel
        self.segment_panel = SegmentPanel(self)
        main_layout.addWidget(self.segment_panel, stretch=1)

        # 5. Bottom Export & Status Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 4, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setObjectName("secondaryLabel")

        self.btn_export = QPushButton("Export Audio…")
        self.btn_export.setProperty("role", "primary")
        self.btn_export.clicked.connect(self.open_export_dialog)

        bottom_bar.addWidget(self.lbl_status)
        bottom_bar.addWidget(self.progress_bar)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_export)

        main_layout.addLayout(bottom_bar)

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
        self.segment_panel.btn_add_selection.clicked.connect(self.add_current_selection_to_segments)
        self.segment_panel.btn_split_playhead.clicked.connect(self.split_at_playhead)
        self.segment_panel.preview_requested.connect(self._player.play_range)
        self.segment_panel.segments_updated.connect(self._on_segments_updated)
        self.segment_panel.segment_selected.connect(self._on_segment_table_selected)

    # --- Loading Audio ---

    def open_file_dialog(self) -> None:
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

        self._load_generation += 1
        generation = self._load_generation
        self._is_loading = True
        self.lbl_status.setText(f"Loading {path.name}…")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate
        self._update_ui_state()

        # Background probe & waveform extraction
        worker = FunctionWorker(self._load_audio_worker, path)
        self._active_workers.add(worker)
        worker.signals.finished.connect(
            lambda result, w=worker, g=generation: self._finish_audio_load(w, g, result)
        )
        worker.signals.failed.connect(
            lambda error, w=worker, g=generation: self._fail_audio_load(w, g, error)
        )
        self._thread_pool.start(worker)

    def _finish_audio_load(self, worker: FunctionWorker, generation: int, result: object) -> None:
        self._active_workers.discard(worker)
        if generation != self._load_generation:
            return
        self._on_audio_loaded(result)  # type: ignore[arg-type]

    def _fail_audio_load(self, worker: FunctionWorker, generation: int, error: str) -> None:
        self._active_workers.discard(worker)
        if generation != self._load_generation:
            return
        self._on_audio_load_failed(error)

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
        self._is_loading = False

        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Loaded '{metadata.filename}' successfully.")
        self.status_message.emit(f"Loaded '{metadata.filename}'", 4000)

        # Update Header label
        info = (
            f"<b>{escape(metadata.filename)}</b> | "
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
        self._is_loading = False
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Failed to load audio.")
        self._update_ui_state()
        self._show_error(f"Could not load audio file:\n{error_msg}")

    # --- UI Interactions & Public Control Methods ---

    def toggle_play_pause(self) -> None:
        self._player.toggle_play_pause()

    def seek_relative(self, delta_seconds: float) -> None:
        self._player.seek_relative(delta_seconds)

    def _update_ui_state(self) -> None:
        has_audio = self._metadata is not None and not self._is_loading
        self.btn_open.setEnabled(not self._is_loading)
        self.btn_play_pause.setEnabled(has_audio and not self._is_loading)
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
        has_exportable_segment = any(
            segment.enabled and segment.duration > 0.01
            for segment in self.segment_panel.get_segments()
        )
        self.btn_export.setEnabled(has_audio and has_exportable_segment)

    def _on_segments_updated(self, segments: list[AudioSegment]) -> None:
        self.waveform.set_segments(segments)
        self._update_ui_state()

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
            self.btn_play_pause.setText("Pause")
            self.btn_play_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.btn_play_pause.setText("Play")
            self.btn_play_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    @Slot(float, float)
    def _on_waveform_selection_changed(self, start: float, end: float) -> None:
        self.txt_in.setText(format_timestamp(start))
        self.txt_out.setText(format_timestamp(end))
        dur = max(0.0, end - start)
        self.lbl_selection_dur.setText(f"Selection: {format_timestamp(dur)}")

    def set_in_to_current(self) -> None:
        pos = self._player.current_position
        self.waveform.set_in_point(pos)

    def set_out_to_current(self) -> None:
        pos = self._player.current_position
        self.waveform.set_out_point(pos)

    def _on_txt_in_changed(self) -> None:
        try:
            t = parse_timestamp(self.txt_in.text())
            self.waveform.set_in_point(t)
        except ValueError:
            self.txt_in.setText(format_timestamp(self.waveform.selection_start))

    def _on_txt_out_changed(self) -> None:
        try:
            t = parse_timestamp(self.txt_out.text())
            self.waveform.set_out_point(t)
        except ValueError:
            self.txt_out.setText(format_timestamp(self.waveform.selection_end))

    def preview_current_selection(self) -> None:
        try:
            s = parse_timestamp(self.txt_in.text())
            e = parse_timestamp(self.txt_out.text())
            if e > s:
                self._player.play_range(s, e)
        except ValueError:
            self._show_error("Enter a valid In and Out timestamp to audition the selection.")

    def add_current_selection_to_segments(self) -> None:
        if not self._metadata:
            return
        try:
            s = parse_timestamp(self.txt_in.text())
            e = parse_timestamp(self.txt_out.text())
            if e <= s:
                e = min(self._metadata.duration, s + 5.0)

            seg = self.segment_panel.add_segment(s, e)
            self.status_message.emit(
                f"Added '{seg.name}' ({format_timestamp(seg.start)} - {format_timestamp(seg.end)})",
                3000,
            )
        except ValueError as err:
            self._show_error(f"Invalid timestamp selection: {err}")

    def split_at_playhead(self) -> None:
        if not self._metadata:
            return
        cur_pos = self._player.current_position
        segments = self.segment_panel.get_segments()

        # Find which segment contains cur_pos
        for i, seg in enumerate(segments):
            if seg.start + 0.1 < cur_pos < seg.end - 0.1:
                # Split this segment into two
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
                self.status_message.emit(f"Split segment at {format_timestamp(cur_pos)}", 3000)
                return

        # If not inside a segment, split from current playhead to end of file as a new segment
        self.waveform.set_in_point(cur_pos)

    def _on_segment_table_selected(self, seg: AudioSegment) -> None:
        self.waveform.set_selection(seg.start, seg.end)

    def _on_volume_slider_changed(self, value: int) -> None:
        vol = value / 100.0
        self._player.set_volume(vol)
        self.lbl_vol_icon.setText("Muted" if value == 0 else "Volume")

    # --- Export Processing ---

    def open_export_dialog(self) -> None:
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

    def cleanup(self) -> None:
        self._load_generation += 1
        self._player.stop()
        self._thread_pool.waitForDone(2000)
        try:
            shutil.rmtree(self._cache_dir)
        except OSError:
            pass
