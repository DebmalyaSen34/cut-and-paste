from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
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
        self.setWindowTitle("Cut and Paste Studio")
        self.resize(1340, 850)
        # The editor needs enough vertical room for a directly manipulable
        # timeline and segment list without controls overlapping.
        self.setMinimumSize(900, 720)

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

        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.video_tab, "Video")
        self.tabs.addTab(self.audio_tab, "Audio")

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
        if self._focus_is_text_editor():
            return
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.step_frame(-1)
        else:
            self.audio_tab.seek_relative(-1.0)

    def _handle_right_arrow(self) -> None:
        if self._focus_is_text_editor():
            return
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.step_frame(1)
        else:
            self.audio_tab.seek_relative(1.0)

    def _handle_shift_left(self) -> None:
        if self._focus_is_text_editor():
            return
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.seek_relative(-5.0)
        else:
            self.audio_tab.seek_relative(-5.0)

    def _handle_shift_right(self) -> None:
        if self._focus_is_text_editor():
            return
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.video_player.seek_relative(5.0)
        else:
            self.audio_tab.seek_relative(5.0)

    def _handle_delete(self) -> None:
        if self._focus_is_text_editor():
            return
        if self.tabs.currentWidget() == self.video_tab:
            self.video_tab.delete_selected_frame()
        else:
            self.audio_tab.segment_panel.delete_selected()

    def _handle_enter(self) -> None:
        if self._focus_is_text_editor():
            return
        if self.tabs.currentWidget() == self.audio_tab:
            self.audio_tab.add_current_selection_to_segments()

    @staticmethod
    def _focus_is_text_editor() -> bool:
        """Do not steal editing keys from text fields and editable controls."""
        focus = QApplication.focusWidget()
        return isinstance(focus, (QLineEdit, QAbstractSpinBox, QComboBox))

    # --- Styling ---

    def _apply_styles(self) -> None:
        app_font = QFont()
        app_font.setFamilies(["SF Pro Text", ".AppleSystemUIFont", "Segoe UI", "sans-serif"])
        app_font.setPointSize(13)
        self.setFont(app_font)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #1c1c1e; color: #f5f5f7; font-size: 13px; }
            QLabel, QCheckBox, QRadioButton { background: transparent; }
            QWidget#tableCell { background: transparent; }
            QMenuBar { background: #121214; color: #f5f5f7; padding: 2px; }
            QMenuBar::item { background: transparent; padding: 4px 8px; }
            QMenuBar::item:selected { background: #3a3a3c; border-radius: 5px; }
            QMenu { background: #2c2c2e; color: #f5f5f7; border: 1px solid #48484a; padding: 5px; }
            QMenu::item { padding: 6px 28px 6px 10px; border-radius: 5px; }
            QMenu::item:selected { background: #0a84ff; }
            QTabWidget::pane { border: none; background: #1c1c1e; }
            QTabBar { background: #121214; qproperty-drawBase: 0; }
            QTabBar::tab {
                background: transparent;
                color: #98989d;
                font-weight: 600;
                font-size: 13px;
                min-width: 96px;
                padding: 11px 22px 10px 22px;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected {
                color: #f5f5f7;
                border-bottom: 2px solid #0a84ff;
            }
            QTabBar::tab:hover:!selected {
                background: #242426;
                color: #d1d1d6;
            }
            QPushButton {
                background: #363638; border: 1px solid #49494d; border-radius: 8px;
                min-height: 20px; padding: 6px 12px; color: #f5f5f7;
            }
            QPushButton:hover { background: #424245; border-color: #5a5a5f; }
            QPushButton:pressed { background: #2c2c2e; padding-top: 7px; padding-bottom: 5px; }
            QPushButton:focus { border: 1px solid #0a84ff; }
            QPushButton:disabled { color: #636366; background: #242426; border-color: #303033; }
            QPushButton[role="primary"] { background: #0a84ff; border-color: #2997ff; color: white; font-weight: 600; }
            QPushButton[role="primary"]:hover { background: #2294ff; }
            QPushButton[role="primary"]:pressed { background: #0071e3; }
            QPushButton[role="destructive"] { color: #ff6961; }
            QPushButton[role="iconButton"] { background: #3a3a3c; border-color: #505054; padding: 0; }
            QPushButton[role="iconButton"]:hover { background: #4a4a4d; border-color: #636366; }
            QPushButton[role="iconButton"]:pressed { background: #2c2c2e; }
            QPushButton[role="destructiveIcon"] {
                background: #ff453a; border-color: #ff6961; color: white; padding: 0;
            }
            QPushButton[role="destructiveIcon"]:hover { background: #ff5b52; border-color: #ff817a; }
            QPushButton[role="destructiveIcon"]:pressed { background: #d9362e; }
            QPushButton[role="primary"]:disabled,
            QPushButton[role="destructive"]:disabled {
                color: #636366; background: #242426; border-color: #303033;
            }
            QLineEdit, QComboBox {
                background: #2c2c2e; border: 1px solid #48484a; border-radius: 7px;
                min-height: 20px; padding: 5px 8px; color: #f5f5f7; selection-background-color: #0a84ff;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #0a84ff; }
            QLineEdit:disabled, QComboBox:disabled { color: #636366; background: #242426; border-color: #303033; }
            QGroupBox {
                background: #242426; border: 1px solid #38383a; border-radius: 10px;
                margin-top: 12px; padding-top: 12px; font-weight: 600;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #d1d1d6; }
            QListWidget, QTableWidget { background: #242426; border: 1px solid #38383a; border-radius: 9px; outline: none; }
            QTableWidget { alternate-background-color: #202022; gridline-color: transparent; }
            QListWidget::item { border-bottom: 1px solid #38383a; }
            QTableWidget::item { padding: 5px; }
            QListWidget::item:selected, QTableWidget::item:selected { background: #0a4f8a; color: white; }
            QHeaderView::section {
                background: #2c2c2e; color: #aeaeb2; padding: 7px 6px; border: none;
                border-right: 1px solid #3a3a3c; border-bottom: 1px solid #3a3a3c; font-weight: 600; font-size: 11px;
            }
            QSlider::groove:horizontal { height: 4px; background: #48484a; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #0a84ff; border-radius: 2px; }
            QSlider::handle:horizontal { width: 16px; margin: -6px 0; border-radius: 8px; background: #f5f5f7; }
            QProgressBar { background: #2c2c2e; border: none; border-radius: 3px; text-align: center; }
            QProgressBar::chunk { background: #0a84ff; border-radius: 3px; }
            QLabel#pageTitle { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
            QLabel#sectionTitle, QLabel#sidebarTitle { font-size: 15px; font-weight: 650; color: #f5f5f7; }
            QLabel#secondaryText, QLabel#secondaryLabel { color: #98989d; font-size: 12px; }
            QLabel#accentText, QLabel#accentLabel, QLabel#cropStatus { color: #64d2ff; font-weight: 600; }
            QLabel#timeLabel { font-size: 13px; font-weight: 600; color: #d1d1d6; }
            QLabel#exportSummary { background: #2c2c2e; padding: 11px; border-radius: 8px; }
            QWidget#surface, QWidget#sidebar { background: #242426; border: 1px solid #38383a; border-radius: 10px; }
            QLabel#previewLabel { background: #101012; color: #8e8e93; border: 1px solid #2c2c2e; border-radius: 10px; }
            QSplitter::handle { background: transparent; width: 8px; }
            QStatusBar { background: #161618; color: #98989d; border-top: 1px solid #2c2c2e; }
            QToolTip { background: #3a3a3c; color: #ffffff; border: 1px solid #545458; padding: 5px; }
            QScrollBar:vertical { background: transparent; width: 11px; margin: 2px; }
            QScrollBar::handle:vertical { background: #545458; min-height: 28px; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.video_tab.cleanup()
        self.audio_tab.cleanup()
        cleanup_app_cache_dir("FrameExtractor")
        cleanup_app_cache_dir("AudioCutterMerger")
        cleanup_app_cache_dir("MediaStudio")
        event.accept()
