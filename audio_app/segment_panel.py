from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from audio_app.models import AudioSegment
from audio_app.utils import format_timestamp, parse_timestamp


class SegmentPanel(QWidget):
    segments_updated = Signal(list)  # list[AudioSegment]
    segment_selected = Signal(object)  # AudioSegment
    preview_requested = Signal(float, float)  # (start, end)
    seek_requested = Signal(float)  # timestamp

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._segments: list[AudioSegment] = []
        self._is_updating_table = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header Bar
        header_layout = QHBoxLayout()
        title_label = QLabel("Audio Segments & Merge Order")
        title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.summary_label = QLabel("0 segments | 00:00:00.000 total")
        self.summary_label.setStyleSheet("color: #8888aa; font-size: 11px;")

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.summary_label)
        layout.addLayout(header_layout)

        # Segments Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Use",
            "#",
            "Name",
            "Start Time",
            "End Time",
            "Duration",
            "Actions",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setColumnWidth(0, 42)
        self.table.setColumnWidth(1, 32)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self.table)

        # Action Buttons Toolbar
        btn_layout = QHBoxLayout()

        self.btn_add_selection = QPushButton("+ Add Selection as Segment")
        self.btn_add_selection.setStyleSheet(
            "background-color: #2a75d3; color: white; font-weight: bold; padding: 5px 10px;"
        )
        self.btn_add_selection.setToolTip("Add current In/Out selection to the segments list (A or Enter)")

        self.btn_split_playhead = QPushButton("Split at Playhead")
        self.btn_split_playhead.setToolTip("Split selected segment at current playback cursor (S)")

        self.btn_move_up = QPushButton("▲ Move Up")
        self.btn_move_up.setToolTip("Move selected segment earlier in the merge order")
        self.btn_move_up.clicked.connect(self.move_selected_up)

        self.btn_move_down = QPushButton("▼ Move Down")
        self.btn_move_down.setToolTip("Move selected segment later in the merge order")
        self.btn_move_down.clicked.connect(self.move_selected_down)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setToolTip("Remove selected segment (Delete)")
        self.btn_delete.clicked.connect(self.delete_selected)

        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self.clear_all)

        btn_layout.addWidget(self.btn_add_selection)
        btn_layout.addWidget(self.btn_split_playhead)
        btn_layout.addSpacing(10)
        btn_layout.addWidget(self.btn_move_up)
        btn_layout.addWidget(self.btn_move_down)
        btn_layout.addSpacing(10)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    # --- Public Accessors ---

    def get_segments(self) -> list[AudioSegment]:
        return list(self._segments)

    def set_segments(self, segments: list[AudioSegment]) -> None:
        self._segments = list(segments)
        self._refresh_table()
        self._notify_update()

    def add_segment(self, start: float, end: float, name: str = "") -> AudioSegment:
        s = min(start, end)
        e = max(start, end)
        if e - s < 0.01:
            e = s + 1.0

        if not name:
            name = f"Segment {len(self._segments) + 1}"

        seg = AudioSegment(start=s, end=e, name=name, enabled=True)
        self._segments.append(seg)
        self._refresh_table()
        # Select newly added row
        self.table.selectRow(len(self._segments) - 1)
        self._notify_update()
        return seg

    def delete_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._segments):
            del self._segments[row]
            self._refresh_table()
            if row < len(self._segments):
                self.table.selectRow(row)
            elif self._segments:
                self.table.selectRow(len(self._segments) - 1)
            self._notify_update()

    def clear_all(self) -> None:
        if not self._segments:
            return
        self._segments.clear()
        self._refresh_table()
        self._notify_update()

    def move_selected_up(self) -> None:
        row = self.table.currentRow()
        if row > 0 and row < len(self._segments):
            self._segments[row - 1], self._segments[row] = self._segments[row], self._segments[row - 1]
            self._refresh_table()
            self.table.selectRow(row - 1)
            self._notify_update()

    def move_selected_down(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._segments) - 1:
            self._segments[row + 1], self._segments[row] = self._segments[row], self._segments[row + 1]
            self._refresh_table()
            self.table.selectRow(row + 1)
            self._notify_update()

    # --- Internal Table Management ---

    def _refresh_table(self) -> None:
        self._is_updating_table = True
        self.table.setRowCount(len(self._segments))

        total_active_duration = 0.0
        active_count = 0

        for row, seg in enumerate(self._segments):
            if seg.enabled:
                total_active_duration += seg.duration
                active_count += 1

            # Column 0: Checkbox
            cb = QCheckBox()
            cb.setChecked(seg.enabled)
            cb.stateChanged.connect(self._make_checkbox_handler(row))
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, cb_container)

            # Column 1: Index Number (#)
            item_num = QTableWidgetItem(str(row + 1))
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_num.setFlags(item_num.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, item_num)

            # Column 2: Name
            item_name = QTableWidgetItem(seg.name)
            self.table.setItem(row, 2, item_name)

            # Column 3: Start Time
            item_start = QTableWidgetItem(format_timestamp(seg.start))
            self.table.setItem(row, 3, item_start)

            # Column 4: End Time
            item_end = QTableWidgetItem(format_timestamp(seg.end))
            self.table.setItem(row, 4, item_end)

            # Column 5: Duration
            item_dur = QTableWidgetItem(format_timestamp(seg.duration))
            item_dur.setFlags(item_dur.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 5, item_dur)

            # Column 6: Action Buttons (Preview, Delete)
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(4)

            btn_play = QPushButton("▶ Play")
            btn_play.setFixedHeight(22)
            btn_play.setToolTip("Audition this segment")
            btn_play.clicked.connect(self._make_play_handler(seg))

            btn_del = QPushButton("✖")
            btn_del.setFixedSize(22, 22)
            btn_del.setToolTip("Delete this segment")
            btn_del.clicked.connect(self._make_del_handler(row))

            actions_layout.addWidget(btn_play)
            actions_layout.addWidget(btn_del)
            self.table.setCellWidget(row, 6, actions_widget)

        self.summary_label.setText(
            f"{active_count} of {len(self._segments)} segments active | {format_timestamp(total_active_duration)} merged duration"
        )
        self._is_updating_table = False

    def _make_checkbox_handler(self, row: int) -> Callable[[int], None]:
        def handler(state: int) -> None:
            if 0 <= row < len(self._segments):
                self._segments[row].enabled = bool(state == Qt.CheckState.Checked.value or state == 2)
                self._refresh_table()
                self._notify_update()
        return handler

    def _make_play_handler(self, seg: AudioSegment) -> Callable[[], None]:
        def handler() -> None:
            self.preview_requested.emit(seg.start, seg.end)
        return handler

    def _make_del_handler(self, row: int) -> Callable[[], None]:
        def handler() -> None:
            if 0 <= row < len(self._segments):
                del self._segments[row]
                self._refresh_table()
                self._notify_update()
        return handler

    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._is_updating_table or not (0 <= row < len(self._segments)):
            return

        seg = self._segments[row]
        item = self.table.item(row, column)
        if not item:
            return

        text = item.text().strip()

        try:
            if column == 2:  # Name
                seg.name = text
            elif column == 3:  # Start Time
                new_start = parse_timestamp(text)
                if new_start < seg.end:
                    seg.start = new_start
            elif column == 4:  # End Time
                new_end = parse_timestamp(text)
                if new_end > seg.start:
                    seg.end = new_end
        except ValueError:
            pass

        self._refresh_table()
        self._notify_update()

    def _on_selection_changed(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._segments):
            seg = self._segments[row]
            self.segment_selected.emit(seg)

    def _notify_update(self) -> None:
        self.segments_updated.emit(self._segments)
