from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
import tarfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def get_user_bin_dir() -> Path:
    """Return the persistent user-level bin directory for self-bootstrapped binaries."""
    base = Path.home() / ".mediastudio" / "bin"
    base.mkdir(parents=True, exist_ok=True)
    return base


def find_bundled_or_local_tool(name: str) -> Path | None:
    """
    Search for a binary (e.g. ffmpeg or ffprobe) in priority order:
    1. PyInstaller frozen _MEIPASS / bin
    2. Executable folder / bin
    3. App resources (macOS bundle)
    4. Project root / bin
    5. Persistent user bin directory ~/.mediastudio/bin
    6. System PATH
    """
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    target_filename = f"{name}{exe_suffix}"

    search_dirs: list[Path] = []

    # 1. PyInstaller extraction directory
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        search_dirs.append(Path(sys._MEIPASS) / "bin")
        search_dirs.append(Path(sys._MEIPASS))

    # 2. Executable parent folder
    exe_dir = Path(sys.executable).parent
    search_dirs.append(exe_dir / "bin")
    search_dirs.append(exe_dir)

    # 3. macOS App bundle Resources
    if sys.platform == "darwin":
        search_dirs.append(exe_dir.parent / "Resources" / "bin")
        search_dirs.append(exe_dir.parent / "Resources")

    # 4. Project root folder bin
    project_root = Path(__file__).resolve().parent.parent
    search_dirs.append(project_root / "bin")

    # 5. User app data bin folder
    search_dirs.append(get_user_bin_dir())

    for directory in search_dirs:
        candidate = directory / target_filename
        if candidate.is_file():
            _ensure_executable(candidate)
            return candidate

    # 6. System PATH
    system_path = shutil.which(name)
    if system_path:
        return Path(system_path)

    return None


def _ensure_executable(path: Path) -> None:
    """Ensure executable permission on POSIX systems."""
    if sys.platform != "win32":
        try:
            current = path.stat().st_mode
            path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass


def get_ffmpeg_and_ffprobe() -> tuple[Path | None, Path | None]:
    """Return paths to ffmpeg and ffprobe if available."""
    ffmpeg = find_bundled_or_local_tool("ffmpeg")
    ffprobe = find_bundled_or_local_tool("ffprobe")
    return ffmpeg, ffprobe


# --- In-App Auto-Downloader for Non-Technical Users ---

DOWNLOAD_URLS = {
    "win32": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "darwin": "https://evermeet.cx/ffmpeg/getrelease/zip",  # or static GitHub build
    "linux": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
}


class DownloadWorker(QObject):
    progress = Signal(int, str)  # percent, status
    finished = Signal()
    failed = Signal(str)

    def __init__(self, target_dir: Path) -> None:
        super().__init__()
        self.target_dir = target_dir

    @Slot()
    def run(self) -> None:
        try:
            url = DOWNLOAD_URLS.get(sys.platform)
            if not url:
                raise RuntimeError(f"Automatic binary download not supported for platform '{sys.platform}'.")

            self.progress.emit(10, "Downloading media tools...")

            with tempfile.TemporaryDirectory() as tmp_dir:
                archive_path = Path(tmp_dir) / "ffmpeg_archive"

                def reporthook(block_num: int, block_size: int, total_size: int) -> None:
                    if total_size > 0:
                        downloaded = block_num * block_size
                        percent = min(80, int((downloaded / total_size) * 70) + 10)
                        self.progress.emit(percent, f"Downloading: {downloaded // (1024 * 1024)}MB / {total_size // (1024 * 1024)}MB")

                urllib.request.urlretrieve(url, archive_path, reporthook=reporthook)

                self.progress.emit(85, "Unpacking media tools...")

                self.target_dir.mkdir(parents=True, exist_ok=True)

                if zipfile.is_zipfile(archive_path):
                    with zipfile.ZipFile(archive_path, "r") as z:
                        for member in z.namelist():
                            filename = os.path.basename(member)
                            if filename in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"):
                                target_file = self.target_dir / filename
                                with z.open(member) as src, open(target_file, "wb") as dst:
                                    shutil.copyfileobj(src, dst)
                                _ensure_executable(target_file)
                elif tarfile.is_tarfile(archive_path):
                    with tarfile.open(archive_path, "r:*") as t:
                        for member in t.getmembers():
                            filename = os.path.basename(member.name)
                            if filename in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"):
                                target_file = self.target_dir / filename
                                src = t.extractfile(member)
                                if src:
                                    with open(target_file, "wb") as dst:
                                        shutil.copyfileobj(src, dst)
                                    _ensure_executable(target_file)

            ffmpeg, ffprobe = get_ffmpeg_and_ffprobe()
            if not ffmpeg or not ffprobe:
                raise RuntimeError("Failed to extract ffmpeg or ffprobe from downloaded package.")

            self.progress.emit(100, "Setup complete!")
            self.finished.emit()

        except Exception as exc:
            self.failed.emit(str(exc))


class FFmpegBootstrapDialog(QDialog):
    """
    User-friendly dialog for non-technical users to download FFmpeg automatically with one click.
    """
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Initial Setup — Media Studio")
        self.setFixedSize(460, 220)
        self.setModal(True)

        self._thread: QThread | None = None
        self._worker: DownloadWorker | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        title = QLabel("<b>Media Engine Setup Required</b>")
        title.setStyleSheet("font-size: 15px; color: #ffffff;")
        layout.addWidget(title)

        desc = QLabel(
            "Media Studio requires FFmpeg to process video frames and audio files.<br><br>"
            "Click <b>Download & Setup Automatically</b> to configure everything automatically."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        layout.addWidget(desc)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #60a5fa; font-size: 11px;")
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_download = QPushButton("⚡ Download & Setup Automatically")
        self.btn_download.setStyleSheet(
            "background-color: #2563eb; color: white; font-weight: bold; padding: 8px 16px;"
        )
        self.btn_download.clicked.connect(self._start_download)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_download)
        layout.addLayout(btn_layout)

    def _start_download(self) -> None:
        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Connecting...")

        self._thread = QThread(self)
        self._worker = DownloadWorker(get_user_bin_dir())
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._thread.start()

    def _on_progress(self, percent: int, text: str) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(text)

    def _on_finished(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        QMessageBox.information(
            self,
            "Setup Complete",
            "Media tools have been configured successfully! You can now use Media Studio.",
        )
        self.accept()

    def _on_failed(self, error: str) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Download failed.")
        QMessageBox.critical(
            self,
            "Setup Failed",
            f"Could not automatically download media tools:\n\n{error}",
        )
