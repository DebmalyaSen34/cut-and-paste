from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.common import cleanup_app_cache_dir
from app.video_tab import VideoExtractorWidget
from audio_app.audio_tab import AudioCutterWidget


class MainWindow(QMainWindow):
    def __init__(self, initial_tab: int = 0) -> None:
        super().__init__()
        self.setWindowTitle("Media Studio — Frame Extractor & Audio Merger")
        self.resize(1340, 850)
        self.setMinimumSize(950, 650)

        self._setup_ui()
        self._setup_menus_and_shortcuts()
        self._apply_styles()

        if initial_tab in (0, 1):
            self.tabs.setCurrentIndex(initial_tab)

    def _setup_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")

        self.video_tab = VideoExtractorWidget(self)
        self.audio_tab = AudioCutterWidget(self)

        self.tabs.addTab(self.video_tab, "🎬  Video Frame Extractor")
        self.tabs.addTab(self.audio_tab, "🎵  Audio Cutter & Merger")

        layout.addWidget(self.tabs)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.video_tab.status_message.connect(self._show_status)
        self.audio_tab.status_message.connect(self._show_status)

    def _show_status(self, message: str, timeout_ms: int = 0) -> None:
        self.status.showMessage(message, timeout_ms)

    def _setup_menus_and_shortcuts(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        act_open_video = QAction("Open &Video...", self)
        act_open_video.setShortcut(QKeySequence("Ctrl+Shift+O"))
        act_open_video.triggered.connect(self._action_open_video)
        file_menu.addAction(act_open_video)

        act_open_audio = QAction("Open &Audio File...", self)
        act_open_audio.setShortcut(QKeySequence.StandardKey.Open)
        act_open_audio.triggered.connect(self._action_open_audio)
        file_menu.addAction(act_open_audio)

        file_menu.addSeparator()

        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Video Menu
        video_menu = menubar.addMenu("&Video")

        act_capture = QAction("&Capture Frame", self)
        act_capture.setShortcut(QKeySequence("C"))
        act_capture.triggered.connect(self._action_capture_frame)
        video_menu.addAction(act_capture)

        act_crop = QAction("Crop Selected &Frame", self)
        act_crop.triggered.connect(lambda: self.video_tab.open_crop_editor())
        video_menu.addAction(act_crop)

        act_export_sel_video = QAction("Export &Selected Frame", self)
        act_export_sel_video.triggered.connect(lambda: self.video_tab.export_selected())
        video_menu.addAction(act_export_sel_video)

        act_export_all_video = QAction("Export &All Frames", self)
        act_export_all_video.triggered.connect(lambda: self.video_tab.export_all())
        video_menu.addAction(act_export_all_video)

        # Audio Menu
        audio_menu = menubar.addMenu("&Audio")

        act_set_in = QAction("Set &In Point", self)
        act_set_in.setShortcut(QKeySequence("I"))
        act_set_in.triggered.connect(self._action_set_in)
        audio_menu.addAction(act_set_in)

        act_set_out = QAction("Set &Out Point", self)
        act_set_out.setShortcut(QKeySequence("O"))
        act_set_out.triggered.connect(self._action_set_out)
        audio_menu.addAction(act_set_out)

        act_add_seg = QAction("&Add Current Selection as Segment", self)
        act_add_seg.setShortcut(QKeySequence("A"))
        act_add_seg.triggered.connect(self._action_add_segment)
        audio_menu.addAction(act_add_seg)

        act_split = QAction("&Split at Playhead", self)
        act_split.setShortcut(QKeySequence("S"))
        act_split.triggered.connect(self._action_split)
        audio_menu.addAction(act_split)

        act_export_audio = QAction("&Export / Merge Audio...", self)
        act_export_audio.setShortcut(QKeySequence("Ctrl+E"))
        act_export_audio.triggered.connect(lambda: self.audio_tab.open_export_dialog())
        audio_menu.addAction(act_export_audio)

        # Playback Menu
        playback_menu = menubar.addMenu("&Playback")

        act_play_pause = QAction("&Play / Pause", self)
        act_play_pause.setShortcut(QKeySequence(Qt.Key.Key_Space))
        act_play_pause.triggered.connect(self._handle_space_shortcut)
        playback_menu.addAction(act_play_pause)

        # Global context-aware Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self._handle_left_arrow)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self._handle_right_arrow)
        QShortcut(QKeySequence(Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Left), self, activated=self._handle_shift_left)
        QShortcut(QKeySequence(Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Right), self, activated=self._handle_shift_right)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._handle_delete)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._handle_enter)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self._handle_enter)

    # --- Routed Action Handlers ---

    def _action_open_video(self) -> None:
        self.tabs.setCurrentWidget(self.video_tab)
        self.video_tab.open_video()

    def _action_open_audio(self) -> None:
        self.tabs.setCurrentWidget(self.audio_tab)
        self.audio_tab.open_file_dialog()

    def _action_capture_frame(self) -> None:
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.capture_current_frame()

    def _action_set_in(self) -> None:
        if self.tabs.currentWidget() == self.audio_tab:
            self.audio_tab.set_in_to_current()

    def _action_set_out(self) -> None:
        if self.tabs.currentWidget() == self.audio_tab:
            self.audio_tab.set_out_to_current()

    def _action_add_segment(self) -> None:
        if self.tabs.currentWidget() == self.audio_tab:
            self.audio_tab.add_current_selection_to_segments()

    def _action_split(self) -> None:
        if self.tabs.currentWidget() == self.audio_tab:
            self.audio_tab.split_at_playhead()

    def _handle_space_shortcut(self) -> None:
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.toggle_playback()
        else:
            self.audio_tab.toggle_play_pause()

    def _handle_left_arrow(self) -> None:
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.step_frame(-1)
        else:
            self.audio_tab.seek_relative(-1.0)

    def _handle_right_arrow(self) -> None:
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.step_frame(1)
        else:
            self.audio_tab.seek_relative(1.0)

    def _handle_shift_left(self) -> None:
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.seek_relative(-5.0)
        else:
            self.audio_tab.seek_relative(-5.0)

    def _handle_shift_right(self) -> None:
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.seek_relative(5.0)
        else:
            self.audio_tab.seek_relative(5.0)

    def _handle_delete(self) -> None:
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.delete_selected_frame()
        else:
            self.audio_tab.segment_panel.delete_selected()

    def _handle_enter(self) -> None:
        if self.tabs.currentWidget() == self.audio_tab:
            self.audio_tab.add_current_selection_to_segments()

    # --- Styling ---

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #111318; color: #eef2f7; font-size: 13px; }
            QTabWidget::pane { border: none; background: #111318; }
            QTabBar::tab {
                background: #181b22;
                color: #8b949e;
                font-weight: 600;
                font-size: 13px;
                padding: 10px 24px;
                border: 1px solid #232730;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #242936;
                color: #ffffff;
                border-color: #3b82f6;
                border-bottom: 2px solid #3b82f6;
            }
            QTabBar::tab:hover:!selected {
                background: #1e232e;
                color: #c9d1d9;
            }
            QPushButton { background: #242936; border: 1px solid #3a4150; border-radius: 6px; padding: 7px 12px; }
            QPushButton:hover { background: #303746; }
            QPushButton:disabled { color: #737b8a; background: #1a1d24; }
            QPushButton#captureButton { background: #2563eb; border-color: #3b82f6; font-weight: 600; }
            QLineEdit, QComboBox { background: #191d25; border: 1px solid #3a4150; border-radius: 6px; padding: 6px; color: #f8fafc; }
            QGroupBox { border: 1px solid #2b3140; border-radius: 6px; margin-top: 10px; font-weight: 600; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QListWidget, QTableWidget { background: #151922; border: 1px solid #2b3140; border-radius: 6px; }
            QListWidget::item { border-bottom: 1px solid #252b38; }
            QListWidget::item:selected, QTableWidget::item:selected { background: #263246; }
            QHeaderView::section { background: #1c212c; color: #c9d1d9; padding: 4px; border: 1px solid #2b3140; font-weight: 600; font-size: 11px; }
            QSlider::groove:horizontal { height: 6px; background: #2b3140; border-radius: 3px; }
            QSlider::handle:horizontal { width: 16px; margin: -6px 0; border-radius: 8px; background: #60a5fa; }
            QLabel#sidebarTitle { font-size: 16px; font-weight: 700; padding: 4px; }
            QLabel#cropStatus { color: #5eead4; font-weight: 600; }
            QStatusBar { background: #0f1117; color: #cbd5e1; border-top: 1px solid #1f242f; }
            """
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.video_tab.cleanup()
        self.audio_tab.cleanup()
        cleanup_app_cache_dir("FrameExtractor")
        cleanup_app_cache_dir("AudioCutterMerger")
        cleanup_app_cache_dir("MediaStudio")
        event.accept()
