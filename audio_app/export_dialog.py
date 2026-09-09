from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from audio_app.models import AudioSegment, ExportSettings
from audio_app.utils import format_timestamp


class ExportDialog(QDialog):
    def __init__(
        self,
        source_path: Path,
        segments: list[AudioSegment],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Audio")
        self.resize(520, 420)
        self.setMinimumWidth(480)

        self.source_path = source_path
        self.segments = [s for s in segments if s.enabled and s.duration > 0.01]

        self._setup_ui()
        self._update_ui_state()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)

        # Overview Header
        total_dur = sum(s.duration for s in self.segments)
        summary_text = (
            f"<b>Source:</b> {escape(self.source_path.name)}<br>"
            f"<b>Active Segments:</b> {len(self.segments)} | <b>Total Duration:</b> {format_timestamp(total_dur)}"
        )
        self.lbl_summary = QLabel(summary_text)
        self.lbl_summary.setObjectName("exportSummary")
        main_layout.addWidget(self.lbl_summary)

        # Export Mode Group
        mode_group = QGroupBox("Export Mode")
        mode_layout = QVBoxLayout(mode_group)
        self.rb_merge = QRadioButton("Merge active segments into a single audio file")
        self.rb_merge.setChecked(True)
        self.rb_merge.toggled.connect(self._update_ui_state)

        self.rb_batch = QRadioButton("Export segments as separate individual files (Batch)")
        self.rb_batch.toggled.connect(self._update_ui_state)

        mode_layout.addWidget(self.rb_merge)
        mode_layout.addWidget(self.rb_batch)
        main_layout.addWidget(mode_group)

        # Format & Quality Settings Group
        settings_group = QGroupBox("Audio Format & Quality")
        form_layout = QFormLayout(settings_group)

        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP3", "WAV", "M4A (AAC)", "FLAC", "OGG"])
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        form_layout.addRow("Output Format:", self.combo_format)

        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItems(["320 kbps (High Quality)", "256 kbps", "192 kbps", "128 kbps"])
        form_layout.addRow("Bitrate:", self.combo_bitrate)

        self.combo_crossfade = QComboBox()
        self.combo_crossfade.addItem("None (Seamless Cut)", 0)
        self.combo_crossfade.addItem("50 ms", 50)
        self.combo_crossfade.addItem("100 ms", 100)
        self.combo_crossfade.addItem("250 ms", 250)
        self.combo_crossfade.addItem("500 ms", 500)
        self.combo_crossfade.addItem("1.0 second", 1000)
        form_layout.addRow("Transition Crossfade:", self.combo_crossfade)

        self.cb_normalize = QCheckBox("Normalize audio loudness (EBU R128)")
        form_layout.addRow("", self.cb_normalize)

        main_layout.addWidget(settings_group)

        # Destination Selection
        dest_group = QGroupBox("Destination")
        dest_layout = QHBoxLayout(dest_group)

        self.txt_destination = QLineEdit()
        default_dir = self.source_path.parent
        default_merged = default_dir / f"{self.source_path.stem}_merged.mp3"
        self.txt_destination.setText(str(default_merged))

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_destination)

        dest_layout.addWidget(self.txt_destination)
        dest_layout.addWidget(self.btn_browse)
        main_layout.addWidget(dest_group)

        # Dialog Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Export Now")
        button_box.button(QDialogButtonBox.StandardButton.Ok).setProperty("role", "primary")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _on_format_changed(self) -> None:
        fmt = self.get_format_extension()
        is_lossy = fmt in {"mp3", "m4a", "ogg"}
        self.combo_bitrate.setEnabled(is_lossy)

        # Update destination extension if path ends in an audio extension
        cur_text = self.txt_destination.text().strip()
        if cur_text and self.rb_merge.isChecked():
            p = Path(cur_text)
            new_path = p.with_suffix(f".{fmt}")
            self.txt_destination.setText(str(new_path))

    def _update_ui_state(self) -> None:
        is_merge = self.rb_merge.isChecked()
        self.combo_crossfade.setEnabled(is_merge)

        fmt = self.get_format_extension()
        cur_text = self.txt_destination.text().strip()

        if is_merge:
            if cur_text and Path(cur_text).is_dir():
                new_dest = Path(cur_text) / f"{self.source_path.stem}_merged.{fmt}"
                self.txt_destination.setText(str(new_dest))
        else:
            if cur_text and not Path(cur_text).is_dir():
                self.txt_destination.setText(str(Path(cur_text).parent))

    def _browse_destination(self) -> None:
        fmt = self.get_format_extension()
        if self.rb_merge.isChecked():
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save Merged Audio File",
                self.txt_destination.text() or str(self.source_path.parent / f"merged.{fmt}"),
                f"{fmt.upper()} Files (*.{fmt});;All Files (*.*)",
            )
            if filename:
                self.txt_destination.setText(filename)
        else:
            folder = QFileDialog.getExistingDirectory(
                self,
                "Select Output Folder for Segments",
                self.txt_destination.text() or str(self.source_path.parent),
            )
            if folder:
                self.txt_destination.setText(folder)

    def get_format_extension(self) -> str:
        text = self.combo_format.currentText()
        if "MP3" in text:
            return "mp3"
        elif "WAV" in text:
            return "wav"
        elif "M4A" in text or "AAC" in text:
            return "m4a"
        elif "FLAC" in text:
            return "flac"
        elif "OGG" in text:
            return "ogg"
        return "mp3"

    def get_bitrate(self) -> str:
        text = self.combo_bitrate.currentText()
        if "320" in text:
            return "320k"
        elif "256" in text:
            return "256k"
        elif "192" in text:
            return "192k"
        elif "128" in text:
            return "128k"
        return "320k"

    def get_export_settings(self) -> ExportSettings:
        dest_path = Path(self.txt_destination.text().strip())
        mode = "merge" if self.rb_merge.isChecked() else "batch"
        crossfade = int(self.combo_crossfade.currentData() or 0)
        normalize = self.cb_normalize.isChecked()

        return ExportSettings(
            output_path=dest_path,
            format=self.get_format_extension(),
            bitrate=self.get_bitrate(),
            crossfade_ms=crossfade if mode == "merge" else 0,
            normalize=normalize,
            mode=mode,
        )
