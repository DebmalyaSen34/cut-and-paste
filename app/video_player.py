from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QStackedLayout,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app.utils import format_timestamp, parse_timestamp


class VideoPlayer(QWidget):
    capture_requested = Signal(float)
    error_message = Signal(str)
    position_seconds_changed = Signal(float)
    preview_frame_requested = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self._duration_ms = 0
        self._fps = 30.0
        self._slider_is_pressed = False
        self._player_enabled = True
        self._manual_position_ms = 0
        self._preview_path: Path | None = None

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setMuted(True)
        self.player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setMinimumHeight(420)
        self.player.setVideoOutput(self.video_widget)
        self.preview_label = QLabel("Open a video to preview frames")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(420)
        self.preview_label.setObjectName("previewLabel")
        self.preview_stack = QStackedLayout()
        preview_container = QWidget()
        preview_container.setLayout(self.preview_stack)
        self.preview_stack.addWidget(self.video_widget)
        self.preview_stack.addWidget(self.preview_label)
        self.preview_stack.setCurrentWidget(self.preview_label)

        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.back_5_button = QPushButton("-5s")
        self.forward_5_button = QPushButton("+5s")
        self.prev_frame_button = QPushButton("Prev frame")
        self.next_frame_button = QPushButton("Next frame")
        self.capture_button = QPushButton("Capture Frame")
        self.capture_button.setObjectName("captureButton")
        self.seek_button = QPushButton("Seek")
        self.timestamp_input = QLineEdit("00:00:00.000")
        self.timestamp_input.setFixedWidth(130)
        self.position_label = QLabel("00:00:00.000")
        self.duration_label = QLabel("00:00:00.000")
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)

        controls = QHBoxLayout()
        controls.addWidget(self.back_5_button)
        controls.addWidget(self.prev_frame_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_frame_button)
        controls.addWidget(self.forward_5_button)
        controls.addStretch()
        controls.addWidget(QLabel("Go to"))
        controls.addWidget(self.timestamp_input)
        controls.addWidget(self.seek_button)

        time_row = QHBoxLayout()
        time_row.addWidget(self.position_label)
        time_row.addWidget(QLabel("/"))
        time_row.addWidget(self.duration_label)
        time_row.addStretch()
        time_row.addWidget(self.capture_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(preview_container, stretch=1)
        layout.addWidget(self.timeline)
        layout.addLayout(controls)
        layout.addLayout(time_row)

        self.play_button.clicked.connect(self.toggle_playback)
        self.back_5_button.clicked.connect(lambda: self.seek_relative(-5.0))
        self.forward_5_button.clicked.connect(lambda: self.seek_relative(5.0))
        self.prev_frame_button.clicked.connect(lambda: self.step_frame(-1))
        self.next_frame_button.clicked.connect(lambda: self.step_frame(1))
        self.capture_button.clicked.connect(self._emit_capture)
        self.seek_button.clicked.connect(self.seek_from_input)
        self.timestamp_input.returnPressed.connect(self.seek_from_input)
        self.timeline.sliderPressed.connect(self._on_slider_pressed)
        self.timeline.sliderReleased.connect(self._on_slider_released)
        self.timeline.sliderMoved.connect(self._on_slider_moved)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.errorOccurred.connect(self._on_player_error)

    def load_video(self, path: Path, fps: float, duration: float, enable_player: bool = True) -> None:
        self._fps = fps if fps > 0 else 30.0
        self._duration_ms = int(duration * 1000)
        self._manual_position_ms = 0
        self._player_enabled = enable_player
        self.player.stop()
        self.player.setSource(QUrl())
        if enable_player:
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.play_button.setEnabled(True)
        else:
            self.play_button.setEnabled(False)
        self.timeline.setRange(0, max(0, self._duration_ms))
        self.duration_label.setText(format_timestamp(duration))
        self.seek_seconds(0)
        self.preview_stack.setCurrentWidget(self.preview_label)
        self.preview_frame_requested.emit(0.0)

    def current_seconds(self) -> float:
        if self._player_enabled:
            return self.player.position() / 1000
        return self._manual_position_ms / 1000

    def toggle_playback(self) -> None:
        if not self._player_enabled:
            self.error_message.emit("Playback preview is disabled for this large file. Scrubbing, seeking, capture, crop, and export still work.")
            return
        self.preview_stack.setCurrentWidget(self.video_widget)
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek_seconds(self, seconds: float) -> None:
        clamped = max(0, min(int(seconds * 1000), self._duration_ms if self._duration_ms else int(seconds * 1000)))
        self._manual_position_ms = clamped
        if self._player_enabled:
            self.player.setPosition(clamped)
        else:
            self.timeline.setValue(clamped)
            self.position_seconds_changed.emit(clamped / 1000)
        self._set_position_labels(clamped)
        self.preview_frame_requested.emit(clamped / 1000)

    def seek_relative(self, delta_seconds: float) -> None:
        self.seek_seconds(self.current_seconds() + delta_seconds)

    def step_frame(self, direction: int) -> None:
        if self._player_enabled:
            self.player.pause()
        frame_delta = 1.0 / self._fps
        self.seek_relative(frame_delta * direction)

    def seek_from_input(self) -> None:
        try:
            self.seek_seconds(parse_timestamp(self.timestamp_input.text()))
        except ValueError as exc:
            self.error_message.emit(str(exc))

    def _emit_capture(self) -> None:
        self.capture_requested.emit(self.current_seconds())

    def _on_slider_pressed(self) -> None:
        self._slider_is_pressed = True

    def _on_slider_released(self) -> None:
        self._slider_is_pressed = False
        self.seek_seconds(self.timeline.value() / 1000)

    def _on_slider_moved(self, value: int) -> None:
        self._set_position_labels(value)

    def _on_position_changed(self, position_ms: int) -> None:
        self._manual_position_ms = position_ms
        if not self._slider_is_pressed:
            self.timeline.setValue(position_ms)
            self._set_position_labels(position_ms)
        self.position_seconds_changed.emit(position_ms / 1000)

    def _on_duration_changed(self, duration_ms: int) -> None:
        if duration_ms > 0:
            self._duration_ms = duration_ms
            self.timeline.setRange(0, duration_ms)
            self.duration_label.setText(format_timestamp(duration_ms / 1000))

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        icon = QStyle.StandardPixmap.SP_MediaPause if state == QMediaPlayer.PlaybackState.PlayingState else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))

    def _on_player_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        if message:
            self.error_message.emit(message)
            self.preview_stack.setCurrentWidget(self.preview_label)

    def _set_position_labels(self, position_ms: int) -> None:
        text = format_timestamp(position_ms / 1000)
        self.position_label.setText(text)
        if not self.timestamp_input.hasFocus():
            self.timestamp_input.setText(text)

    def set_static_preview(self, path: Path) -> None:
        self._preview_path = path
        self._paint_static_preview()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._preview_path:
            self._paint_static_preview()

    def _paint_static_preview(self) -> None:
        if not self._preview_path:
            return
        path = self._preview_path
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.preview_stack.setCurrentWidget(self.preview_label)
