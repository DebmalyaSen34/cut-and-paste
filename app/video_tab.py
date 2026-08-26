from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.captured_frame import CapturedFrame, VideoMetadata
from app.crop_editor import CropEditor
from app.frame_extractor import FfmpegError, export_frame, extract_frame, probe_video, require_video_tools
from app.utils import ensure_cache_dir, export_filename, format_timestamp
from app.video_player import VideoPlayer

QT_PLAYER_SIZE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[[], object]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.function())
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class FrameItemWidget(QWidget):
    def __init__(self, frame: CapturedFrame) -> None:
        super().__init__()
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(148, 84)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(frame.path))
        if not pixmap.isNull():
            self.thumbnail.setPixmap(
                pixmap.scaled(
                    self.thumbnail.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        timestamp = QLabel(format_timestamp(frame.timestamp))
        resolution = QLabel(f"{frame.width} x {frame.height}")
        crop = QLabel("Cropped" if frame.is_cropped else "")
        crop.setObjectName("cropStatus")

        text_layout = QVBoxLayout()
        text_layout.addWidget(timestamp)
        text_layout.addWidget(resolution)
        text_layout.addWidget(crop)
        text_layout.addStretch()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.thumbnail)
        layout.addLayout(text_layout)


class VideoExtractorWidget(QWidget):
    status_message = Signal(str, int)  # text, timeout_ms

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.video_path: Path | None = None
        self.metadata: VideoMetadata | None = None
        self.frames: list[CapturedFrame] = []
        self.is_busy = False
        self.active_workers: set[FunctionWorker] = set()
        self.preview_in_progress = False
        self.pending_preview_timestamp: float | None = None
        self.preview_generation = 0
        self.thread_pool = QThreadPool.globalInstance()
        self.cache_dir = ensure_cache_dir()
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._start_pending_preview)

        self.video_player = VideoPlayer()
        self.video_player.capture_requested.connect(self.capture_current_frame)
        self.video_player.error_message.connect(self.show_error)
        self.video_player.preview_frame_requested.connect(self.update_preview_frame)

        self.open_button = QPushButton("Open Video")
        self.open_button.clicked.connect(self.open_video)
        self.export_all_top_button = QPushButton("Export All")
        self.export_all_top_button.clicked.connect(self.export_all)

        self.frame_list = QListWidget()
        self.frame_list.itemDoubleClicked.connect(lambda _item: self.open_crop_editor())
        self.frame_list.currentRowChanged.connect(self._update_actions)

        self.crop_button = QPushButton("Crop")
        self.crop_button.clicked.connect(self.open_crop_editor)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected_frame)
        self.export_selected_button = QPushButton("Export Selected")
        self.export_selected_button.clicked.connect(self.export_selected)
        self.export_all_button = QPushButton("Export All")
        self.export_all_button.clicked.connect(self.export_all)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPEG"])

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()

        self._build_ui()
        self._update_actions()
        self._check_tools_on_startup()

    def _build_ui(self) -> None:
        top_bar = QHBoxLayout()
        top_bar.addWidget(self.open_button)
        top_bar.addStretch()
        top_bar.addWidget(QLabel("Export Format:"))
        top_bar.addWidget(self.format_combo)
        top_bar.addWidget(self.export_all_top_button)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(top_bar)
        left_layout.addWidget(self.video_player, stretch=1)

        sidebar = QWidget()
        sidebar.setMinimumWidth(310)
        sidebar.setMaximumWidth(390)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Captured Frames")
        title.setObjectName("sidebarTitle")
        side_layout.addWidget(title)
        side_layout.addWidget(self.frame_list, stretch=1)
        side_layout.addWidget(self.progress)
        side_layout.addWidget(self.crop_button)
        side_layout.addWidget(self.export_selected_button)
        side_layout.addWidget(self.delete_button)
        side_layout.addWidget(self.export_all_button)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(sidebar)
        splitter.setSizes([960, 320])

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(splitter)

    def _check_tools_on_startup(self) -> None:
        try:
            require_video_tools()
        except FfmpegError as exc:
            self.show_error(str(exc))

    def open_video(self) -> None:
        path_text, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            str(Path.home()),
            "Video Files (*.mp4 *.mov *.mkv *.avi *.m4v *.webm *.flv *.ts);;All Files (*.*)",
        )
        if not path_text:
            return

        path = Path(path_text)
        self._set_busy(True, "Reading video metadata...")

        self._start_worker(
            FunctionWorker(lambda: probe_video(path)),
            on_finished=lambda metadata: self._video_loaded(path, metadata),
            on_failed=self._operation_failed,
        )

    def _video_loaded(self, path: Path, metadata: object) -> None:
        self.video_path = path
        self.metadata = metadata  # type: ignore[assignment]
        self.frames.clear()
        self.frame_list.clear()
        self.preview_generation += 1
        self.pending_preview_timestamp = None
        self.preview_in_progress = False
        self.preview_timer.stop()
        enable_player = self._should_enable_qt_player(path)
        self.video_player.load_video(path, self.metadata.fps, self.metadata.duration, enable_player=enable_player)
        mode = "large-file still preview" if not enable_player else "interactive preview"
        self._set_busy(False, f"Loaded {path.name} | {self.metadata.width} x {self.metadata.height} | {self.metadata.codec} | {mode}")
        self.update_preview_frame(0.0)
        self._update_actions()

    def _should_enable_qt_player(self, path: Path) -> bool:
        try:
            return path.stat().st_size < QT_PLAYER_SIZE_LIMIT_BYTES
        except OSError:
            return True

    def update_preview_frame(self, timestamp: float) -> None:
        if not self.video_path or self.is_busy:
            return
        self.pending_preview_timestamp = timestamp
        if not self.preview_timer.isActive():
            self.preview_timer.start(180)

    def _start_pending_preview(self) -> None:
        if not self.video_path or self.pending_preview_timestamp is None or self.is_busy:
            return
        if self.preview_in_progress:
            self.preview_timer.start(180)
            return

        timestamp = self.pending_preview_timestamp
        self.pending_preview_timestamp = None
        self.preview_in_progress = True
        self.preview_generation += 1
        generation = self.preview_generation
        output = self.cache_dir / f"preview_{generation}.png"
        video_path = self.video_path

        def task() -> tuple[int, Path, Path]:
            return generation, extract_frame(video_path, timestamp, output), video_path

        self._start_worker(
            FunctionWorker(task),
            on_finished=self._preview_finished,
            on_failed=self._preview_failed,
        )

    def _preview_finished(self, result: object) -> None:
        self.preview_in_progress = False
        if isinstance(result, tuple):
            generation, path, video_path = result
            if generation == self.preview_generation and video_path == self.video_path:
                self.video_player.set_static_preview(path)
        if self.pending_preview_timestamp is not None:
            self.preview_timer.start(80)

    def _preview_failed(self, message: str) -> None:
        self.preview_in_progress = False
        self.status_message.emit(f"Preview unavailable: {message}", 5000)
        if self.pending_preview_timestamp is not None:
            self.preview_timer.start(250)

    def capture_current_frame(self, timestamp: float | None = None) -> None:
        if timestamp is None:
            timestamp = self.video_player.current_seconds()
        if not self.video_path or not self.metadata:
            self.show_error("Open a video before capturing a frame.")
            return

        output = self.cache_dir / f"capture_{uuid.uuid4().hex}.png"
        video_path = self.video_path
        metadata = self.metadata
        self._set_busy(True, f"Extracting {format_timestamp(timestamp)}...")

        def task() -> CapturedFrame:
            extract_frame(video_path, timestamp, output)
            return CapturedFrame(timestamp=timestamp, path=output, width=metadata.width, height=metadata.height)

        self._start_worker(
            FunctionWorker(task),
            on_finished=self._capture_finished,
            on_failed=self._operation_failed,
        )

    def _capture_finished(self, result: object) -> None:
        frame = result
        assert isinstance(frame, CapturedFrame)
        self.frames.append(frame)
        self._append_frame_item(frame)
        self.frame_list.setCurrentRow(len(self.frames) - 1)
        self._set_busy(False, f"Captured {format_timestamp(frame.timestamp)}")
        self._update_actions()

    def _append_frame_item(self, frame: CapturedFrame) -> None:
        item = QListWidgetItem()
        widget = FrameItemWidget(frame)
        item.setSizeHint(widget.sizeHint())
        self.frame_list.addItem(item)
        self.frame_list.setItemWidget(item, widget)

    def _refresh_frame_item(self, row: int) -> None:
        item = self.frame_list.item(row)
        if not item:
            return
        widget = FrameItemWidget(self.frames[row])
        item.setSizeHint(widget.sizeHint())
        self.frame_list.setItemWidget(item, widget)

    def selected_frame(self) -> CapturedFrame | None:
        row = self.frame_list.currentRow()
        if row < 0 or row >= len(self.frames):
            return None
        return self.frames[row]

    def open_crop_editor(self) -> None:
        frame = self.selected_frame()
        row = self.frame_list.currentRow()
        if not frame:
            return
        dialog = CropEditor(frame.path, frame.crop, self)
        if dialog.exec() == CropEditor.DialogCode.Accepted:
            frame.crop = dialog.result_crop
            self._refresh_frame_item(row)
            self.status_message.emit("Crop saved as metadata.", 4000)

    def delete_selected_frame(self) -> None:
        row = self.frame_list.currentRow()
        if row < 0 or row >= len(self.frames):
            return
        frame = self.frames.pop(row)
        self.frame_list.takeItem(row)
        try:
            frame.path.unlink(missing_ok=True)
        except OSError:
            pass
        self._update_actions()

    def export_selected(self) -> None:
        frame = self.selected_frame()
        if frame:
            self._export_frames([frame])

    def export_all(self) -> None:
        if self.frames:
            self._export_frames(list(self.frames))

    def _export_frames(self, frames: list[CapturedFrame]) -> None:
        if not self.video_path:
            return
        directory_text = QFileDialog.getExistingDirectory(self, "Choose Output Directory", str(Path.home()))
        if not directory_text:
            return

        extension = "jpg" if self.format_combo.currentText() == "JPEG" else "png"
        output_dir = Path(directory_text)
        planned: list[tuple[CapturedFrame, Path]] = [
            (frame, output_dir / export_filename(frame.timestamp, extension, frame.is_cropped)) for frame in frames
        ]
        existing = [path for _, path in planned if path.exists()]
        if existing:
            response = QMessageBox.question(
                self,
                "Overwrite files?",
                f"{len(existing)} file(s) already exist. Overwrite them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        else:
            overwrite = False

        video_path = self.video_path
        self._set_busy(True, f"Exporting {len(planned)} frame(s)...")

        def task() -> list[Path]:
            paths: list[Path] = []
            for frame, output_path in planned:
                export_frame(video_path, frame.timestamp, output_path, frame.crop, overwrite=overwrite)
                paths.append(output_path)
            return paths

        self._start_worker(
            FunctionWorker(task),
            on_finished=self._export_finished,
            on_failed=self._operation_failed,
        )

    def _export_finished(self, paths: object) -> None:
        count = len(paths) if isinstance(paths, list) else 0
        self._set_busy(False, f"Exported {count} frame(s).")

    def _operation_failed(self, message: str) -> None:
        self._set_busy(False, "Ready")
        self.show_error(message)

    def _set_busy(self, busy: bool, message: str) -> None:
        self.is_busy = busy
        self.progress.setVisible(busy)
        self.status_message.emit(message, 5000 if not busy else 0)
        self._update_actions()

    def _update_actions(self) -> None:
        has_video = self.video_path is not None
        has_selection = self.selected_frame() is not None
        has_frames = bool(self.frames)
        can_act = not self.is_busy
        self.open_button.setEnabled(can_act)
        self.video_player.capture_button.setEnabled(can_act and has_video)
        self.crop_button.setEnabled(can_act and has_selection)
        self.delete_button.setEnabled(can_act and has_selection)
        self.export_selected_button.setEnabled(can_act and has_selection)
        self.export_all_button.setEnabled(can_act and has_frames)
        self.export_all_top_button.setEnabled(can_act and has_frames)

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Frame Extractor", message or "Something went wrong.")

    def _start_worker(
        self,
        worker: FunctionWorker,
        on_finished: Callable[[object], None],
        on_failed: Callable[[str], None],
    ) -> None:
        self.active_workers.add(worker)

        def finish(result: object, finished_worker: FunctionWorker = worker) -> None:
            self.active_workers.discard(finished_worker)
            on_finished(result)

        def fail(message: str, failed_worker: FunctionWorker = worker) -> None:
            self.active_workers.discard(failed_worker)
            on_failed(message)

        worker.signals.finished.connect(finish)
        worker.signals.failed.connect(fail)
        self.thread_pool.start(worker)

    def cleanup(self) -> None:
        self.preview_timer.stop()
        self.video_player.player.stop()
        self.thread_pool.waitForDone(2000)
        try:
            shutil.rmtree(self.cache_dir)
        except OSError:
            pass
