from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from audio_app.models import AudioSegment
from audio_app.utils import format_timestamp_short


class WaveformWidget(QWidget):
    selection_changed = Signal(float, float)  # (start_sec, end_sec)
    seek_requested = Signal(float)  # target_sec

    HANDLE_WIDTH = 10
    RULER_HEIGHT = 26

    # Distinct colors for segment overlays
    SEGMENT_COLORS = [
        QColor(10, 132, 255, 74),
        QColor(48, 209, 88, 74),
        QColor(191, 90, 242, 74),
        QColor(255, 159, 10, 74),
        QColor(255, 214, 10, 74),
        QColor(255, 69, 58, 74),
        QColor(100, 210, 255, 74),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._duration: float = 0.0
        self._peaks: list[tuple[float, float]] = []
        self._current_pos: float = 0.0

        self._selection_start: float = 0.0
        self._selection_end: float = 0.0

        self._segments: list[AudioSegment] = []

        # Zoom & Scroll state
        self._zoom: float = 1.0  # 1.0 = fit entire audio, up to 20.0
        self._scroll_offset: float = 0.0  # seconds offset

        # Interaction state
        self._drag_mode: str | None = None  # "playhead", "in_handle", "out_handle", "select_range", "pan"
        self._drag_anchor_time: float = 0.0
        self._last_mouse_pos = QPointF()

    # --- Public Setters ---

    @property
    def selection_start(self) -> float:
        return self._selection_start

    @property
    def selection_end(self) -> float:
        return self._selection_end

    def set_audio(self, duration: float, peaks: list[tuple[float, float]]) -> None:
        self._duration = max(0.0, duration)
        self._peaks = peaks
        self._current_pos = 0.0
        self._selection_start = 0.0
        self._selection_end = self._duration
        self._zoom = 1.0
        self._scroll_offset = 0.0
        self.selection_changed.emit(self._selection_start, self._selection_end)
        self.update()

    def set_position(self, seconds: float) -> None:
        self._current_pos = max(0.0, min(seconds, self._duration))
        # If zooming in, keep playhead in view during playback
        if self._zoom > 1.0 and self._drag_mode is None:
            visible_dur = self._visible_duration()
            if self._current_pos < self._scroll_offset or self._current_pos > self._scroll_offset + visible_dur:
                self._scroll_offset = max(0.0, min(self._current_pos - visible_dur * 0.2, self._duration - visible_dur))
        self.update()

    def set_selection(self, start: float, end: float) -> None:
        s = max(0.0, min(start, self._duration))
        e = max(s, min(end, self._duration))
        self._selection_start = s
        self._selection_end = e
        self.selection_changed.emit(self._selection_start, self._selection_end)
        self.update()

    def set_in_point(self, start: float) -> None:
        s = max(0.0, min(start, self._duration))
        e = self._selection_end
        if self._duration > 0 and s >= e:
            s = self._selection_start
        self.set_selection(s, e)

    def set_out_point(self, end: float) -> None:
        e = max(0.0, min(end, self._duration))
        s = self._selection_start
        if self._duration > 0 and e <= s:
            e = self._selection_end
        self.set_selection(s, e)

    def set_segments(self, segments: list[AudioSegment]) -> None:
        self._segments = segments
        self.update()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.3)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.3)

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(1.0, min(zoom, 30.0))
        if self._zoom == 1.0:
            self._scroll_offset = 0.0
        else:
            # Zoom centered around current position or center of view
            visible = self._visible_duration()
            self._scroll_offset = max(0.0, min(self._current_pos - visible / 2.0, self._duration - visible))
        self.update()

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._scroll_offset = 0.0
        self.update()

    # --- Coordinate Transformations ---

    def _visible_duration(self) -> float:
        if self._duration <= 0:
            return 1.0
        return self._duration / self._zoom

    def _time_to_x(self, time_sec: float) -> float:
        if self._duration <= 0:
            return 0.0
        vis_dur = self._visible_duration()
        rel_time = time_sec - self._scroll_offset
        return (rel_time / vis_dur) * self.width()

    def _x_to_time(self, x: float) -> float:
        if self.width() <= 0 or self._duration <= 0:
            return 0.0
        vis_dur = self._visible_duration()
        time = self._scroll_offset + (x / self.width()) * vis_dur
        return max(0.0, min(time, self._duration))

    # --- Painting ---

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = self.width()
        height = self.height()
        ruler_h = self.RULER_HEIGHT
        wave_h = height - ruler_h
        wave_top = ruler_h
        mid_y = wave_top + wave_h / 2.0

        # Background
        painter.fillRect(0, 0, width, height, QColor("#18181a"))
        painter.fillRect(0, 0, width, ruler_h, QColor("#202022"))

        # Time Ruler
        self._draw_ruler(painter, width, ruler_h)

        if self._duration <= 0 or not self._peaks:
            painter.setPen(QColor("#8e8e93"))
            painter.drawText(
                QRectF(0, ruler_h, width, wave_h),
                Qt.AlignmentFlag.AlignCenter,
                "Drop or open an audio file to view waveform",
            )
            return

        # Draw Saved Segments Overlay
        self._draw_saved_segments(painter, wave_top, wave_h)

        # Draw Active Selection Region
        self._draw_selection(painter, wave_top, wave_h)

        # Draw Waveform Peaks
        self._draw_peaks(painter, wave_top, wave_h, mid_y)

        # Draw Selection Handles (In / Out)
        self._draw_selection_handles(painter, wave_top, wave_h)

        # Draw Playhead Cursor
        self._draw_playhead(painter, wave_top, wave_h)

    def _draw_ruler(self, painter: QPainter, width: int, ruler_h: int) -> None:
        painter.setPen(QPen(QColor("#3a3a3c"), 1))
        painter.drawLine(0, ruler_h - 1, width, ruler_h - 1)

        if self._duration <= 0:
            return

        vis_dur = self._visible_duration()
        # Choose appropriate tick step based on zoom / visible duration
        candidate_steps = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0]
        step = candidate_steps[-1]
        for s in candidate_steps:
            if (width / vis_dur) * s >= 65:  # at least 65px apart
                step = s
                break

        start_time = (int(self._scroll_offset / step)) * step
        end_time = self._scroll_offset + vis_dur

        font = QFont("SF Pro Text", 9)
        painter.setFont(font)
        painter.setPen(QColor("#98989d"))

        t = start_time
        while t <= end_time:
            x = self._time_to_x(t)
            if 0 <= x <= width:
                painter.drawLine(int(x), ruler_h - 6, int(x), ruler_h - 1)
                label = format_timestamp_short(t)
                label_x = max(0.0, min(x - 30, width - 60.0))
                painter.drawText(QRectF(label_x, 2, 60, ruler_h - 8), Qt.AlignmentFlag.AlignCenter, label)
            t += step

    def _draw_saved_segments(self, painter: QPainter, top: int, height: int) -> None:
        for idx, seg in enumerate(self._segments):
            if not seg.enabled or seg.duration <= 0:
                continue
            x1 = self._time_to_x(seg.start)
            x2 = self._time_to_x(seg.end)
            if x2 < 0 or x1 > self.width():
                continue

            w = max(2.0, x2 - x1)
            color = self.SEGMENT_COLORS[idx % len(self.SEGMENT_COLORS)]
            painter.fillRect(QRectF(x1, top, w, height), color)

            # Segment border & label
            border_color = QColor(color.red(), color.green(), color.blue(), 220)
            painter.setPen(QPen(border_color, 1.5, Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(x1, top + 1, w, height - 2))

            # Segment label badge
            badge_text = seg.name or f"Seg {idx + 1}"
            painter.setPen(QColor("#f5f5f7"))
            painter.setFont(QFont("SF Pro Text", 9, QFont.Weight.DemiBold))
            painter.drawText(QRectF(x1 + 4, top + 4, w - 8, 16), Qt.AlignmentFlag.AlignLeft, badge_text)

    def _draw_selection(self, painter: QPainter, top: int, height: int) -> None:
        if self._selection_end <= self._selection_start:
            return

        x1 = self._time_to_x(self._selection_start)
        x2 = self._time_to_x(self._selection_end)
        w = max(1.0, x2 - x1)

        # Highlight box for active cut region
        selection_brush = QBrush(QColor(10, 132, 255, 54))
        painter.fillRect(QRectF(x1, top, w, height), selection_brush)

        # Dim regions outside selection
        dim_brush = QBrush(QColor(0, 0, 0, 82))
        if x1 > 0:
            painter.fillRect(QRectF(0, top, x1, height), dim_brush)
        if x2 < self.width():
            painter.fillRect(QRectF(x2, top, self.width() - x2, height), dim_brush)

    def _draw_peaks(self, painter: QPainter, top: int, height: int, mid_y: float) -> None:
        if not self._peaks:
            return

        width = self.width()
        num_peaks = len(self._peaks)
        half_h = (height / 2.0) * 0.90

        # Waveform center baseline
        painter.setPen(QPen(QColor("#38383a"), 1))
        painter.drawLine(0, int(mid_y), width, int(mid_y))

        # Render vertical bars across width
        painter.setPen(QPen(QColor("#64d2ff"), 1.2))
        for x in range(width):
            t = self._x_to_time(x)
            peak_idx = int((t / self._duration) * num_peaks)
            if 0 <= peak_idx < num_peaks:
                min_v, max_v = self._peaks[peak_idx]
                y_top = mid_y - (max_v * half_h)
                y_bot = mid_y - (min_v * half_h)
                if abs(y_bot - y_top) < 1:
                    y_bot = y_top + 1
                painter.drawLine(QPointF(x, y_top), QPointF(x, y_bot))

    def _draw_selection_handles(self, painter: QPainter, top: int, height: int) -> None:
        if self._selection_end <= self._selection_start:
            return

        x_in = self._time_to_x(self._selection_start)
        x_out = self._time_to_x(self._selection_end)

        # IN Handle (Start)
        if 0 <= x_in <= self.width():
            painter.setPen(QPen(QColor("#30d158"), 2))
            painter.drawLine(int(x_in), top, int(x_in), top + height)

            # In Handle flag/tab at top
            painter.setBrush(QBrush(QColor("#30d158")))
            in_flag = QPainterPath()
            in_flag.moveTo(x_in, top)
            in_flag.lineTo(x_in + self.HANDLE_WIDTH, top)
            in_flag.lineTo(x_in + self.HANDLE_WIDTH, top + 14)
            in_flag.lineTo(x_in, top + 18)
            in_flag.closeSubpath()
            painter.drawPath(in_flag)
            painter.setPen(QColor("#000000"))
            painter.setFont(QFont("SF Pro Text", 8, QFont.Weight.Bold))
            painter.drawText(QRectF(x_in + 1, top + 2, self.HANDLE_WIDTH - 2, 12), Qt.AlignmentFlag.AlignCenter, "I")

        # OUT Handle (End)
        if 0 <= x_out <= self.width():
            painter.setPen(QPen(QColor("#ff453a"), 2))
            painter.drawLine(int(x_out), top, int(x_out), top + height)

            # Out Handle flag/tab at top
            painter.setBrush(QBrush(QColor("#ff453a")))
            out_flag = QPainterPath()
            out_flag.moveTo(x_out, top)
            out_flag.lineTo(x_out - self.HANDLE_WIDTH, top)
            out_flag.lineTo(x_out - self.HANDLE_WIDTH, top + 14)
            out_flag.lineTo(x_out, top + 18)
            out_flag.closeSubpath()
            painter.drawPath(out_flag)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("SF Pro Text", 8, QFont.Weight.Bold))
            painter.drawText(QRectF(x_out - self.HANDLE_WIDTH + 1, top + 2, self.HANDLE_WIDTH - 2, 12), Qt.AlignmentFlag.AlignCenter, "O")

    def _draw_playhead(self, painter: QPainter, top: int, height: int) -> None:
        if self._duration <= 0:
            return

        x = self._time_to_x(self._current_pos)
        if not (0 <= x <= self.width()):
            return

        # Cursor line
        painter.setPen(QPen(QColor("#ffd60a"), 2))
        painter.drawLine(int(x), top - 6, int(x), top + height)

        # Playhead top triangle indicator
        painter.setBrush(QBrush(QColor("#ffd60a")))
        painter.setPen(Qt.PenStyle.NoPen)
        playhead_poly = QPainterPath()
        playhead_poly.moveTo(x - 5, top - 6)
        playhead_poly.lineTo(x + 5, top - 6)
        playhead_poly.lineTo(x, top + 4)
        playhead_poly.closeSubpath()
        painter.drawPath(playhead_poly)

    # --- Mouse & Wheel Interactions ---

    def _is_near_x(self, mouse_x: float, target_x: float, threshold: float = 8.0) -> bool:
        return abs(mouse_x - target_x) <= threshold

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._duration <= 0:
            return

        pos = event.position()
        mx = pos.x()
        my = pos.y()
        self._last_mouse_pos = pos

        if event.button() == Qt.MouseButton.RightButton or (event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.AltModifier)):
            # Panning
            self._drag_mode = "pan"
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            x_in = self._time_to_x(self._selection_start)
            x_out = self._time_to_x(self._selection_end)
            x_play = self._time_to_x(self._current_pos)

            # Check handles first
            if self._is_near_x(mx, x_in, 10.0) and my >= self.RULER_HEIGHT:
                self._drag_mode = "in_handle"
            elif self._is_near_x(mx, x_out, 10.0) and my >= self.RULER_HEIGHT:
                self._drag_mode = "out_handle"
            elif self._is_near_x(mx, x_play, 8.0):
                self._drag_mode = "playhead"
            elif my < self.RULER_HEIGHT:
                # Clicking ruler seeks playhead directly
                t = self._x_to_time(mx)
                self.seek_requested.emit(t)
                self._drag_mode = "playhead"
            else:
                # Dragging on waveform to select a new region or seek
                t = self._x_to_time(mx)
                self._drag_anchor_time = t
                self._drag_mode = "select_range"
                self.seek_requested.emit(t)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        mx = pos.x()
        my = pos.y()

        # Update cursor based on hover
        if self._duration > 0 and self._drag_mode is None:
            x_in = self._time_to_x(self._selection_start)
            x_out = self._time_to_x(self._selection_end)
            x_play = self._time_to_x(self._current_pos)

            if self._is_near_x(mx, x_in, 10.0) or self._is_near_x(mx, x_out, 10.0):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif self._is_near_x(mx, x_play, 8.0):
                self.setCursor(Qt.CursorShape.SplitHCursor)
            elif my < self.RULER_HEIGHT:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

        if self._drag_mode == "pan":
            dx = pos.x() - self._last_mouse_pos.x()
            time_delta = (dx / self.width()) * self._visible_duration()
            vis_dur = self._visible_duration()
            self._scroll_offset = max(0.0, min(self._scroll_offset - time_delta, self._duration - vis_dur))
            self._last_mouse_pos = pos
            self.update()

        elif self._drag_mode == "in_handle":
            t = self._x_to_time(mx)
            self.set_in_point(t)

        elif self._drag_mode == "out_handle":
            t = self._x_to_time(mx)
            self.set_out_point(t)

        elif self._drag_mode == "playhead":
            t = self._x_to_time(mx)
            self.seek_requested.emit(t)

        elif self._drag_mode == "select_range":
            t = self._x_to_time(mx)
            s = min(self._drag_anchor_time, t)
            e = max(self._drag_anchor_time, t)
            self.set_selection(s, e)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_mode = None
        self.unsetCursor()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._duration <= 0:
            return

        angle_delta = event.angleDelta()
        pixel_delta = event.pixelDelta()
        vertical_delta = pixel_delta.y() if not pixel_delta.isNull() else angle_delta.y()

        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            # Zoom in/out at mouse location
            if vertical_delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            # Horizontal scroll
            h_delta = pixel_delta.x() or pixel_delta.y() or angle_delta.x() or angle_delta.y()
            time_delta = (h_delta / 300.0) * self._visible_duration()
            vis_dur = self._visible_duration()
            self._scroll_offset = max(0.0, min(self._scroll_offset - time_delta, self._duration - vis_dur))
            self.update()
        event.accept()
