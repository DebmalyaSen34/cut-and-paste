from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayer(QObject):
    position_changed = Signal(float)  # seconds
    duration_changed = Signal(float)  # seconds
    playback_state_changed = Signal(bool)  # True = playing, False = paused/stopped
    playback_range_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        self._preview_end: float | None = None
        self._current_path: Path | None = None

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)

        self.set_volume(0.85)

    @property
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @property
    def current_position(self) -> float:
        return max(0.0, self._player.position() / 1000.0)

    @property
    def duration(self) -> float:
        return max(0.0, self._player.duration() / 1000.0)

    def load(self, audio_path: Path) -> None:
        self.stop()
        self._current_path = audio_path
        self._preview_end = None
        self._player.setSource(QUrl.fromLocalFile(str(audio_path)))

    def play(self) -> None:
        self._preview_end = None
        self._player.play()

    def play_range(self, start: float, end: float) -> None:
        """Play a bounded range (e.g. previewing a segment) and stop at end."""
        self._preview_end = max(start + 0.05, end)
        self.seek_to(start)
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle_play_pause(self) -> None:
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._preview_end = None
        self._player.stop()

    def seek_to(self, seconds: float) -> None:
        target_ms = int(max(0.0, seconds) * 1000)
        self._player.setPosition(target_ms)

    def seek_relative(self, delta_seconds: float) -> None:
        cur = self.current_position
        self.seek_to(cur + delta_seconds)

    def set_volume(self, volume: float) -> None:
        # Clamped between 0.0 and 1.0
        v = max(0.0, min(1.0, volume))
        self._audio_output.setVolume(v)

    def get_volume(self) -> float:
        return self._audio_output.volume()

    @Slot(int)
    def _on_position_changed(self, position_ms: int) -> None:
        sec = position_ms / 1000.0
        if self._preview_end is not None and sec >= self._preview_end:
            self.pause()
            self._preview_end = None
            self.playback_range_finished.emit()
        self.position_changed.emit(sec)

    @Slot(int)
    def _on_duration_changed(self, duration_ms: int) -> None:
        self.duration_changed.emit(duration_ms / 1000.0)

    @Slot(QMediaPlayer.PlaybackState)
    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.playback_state_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    @Slot(QMediaPlayer.Error, str)
    def _on_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.error_occurred.emit(error_string or "Audio playback error.")
