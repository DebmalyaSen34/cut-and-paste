from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices


class ToolNotFoundError(RuntimeError):
    pass


def get_subprocess_kwargs() -> dict:
    """Return platform-specific kwargs to suppress console window flashing on Windows."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def require_ffmpeg_tools(interactive: bool = True) -> tuple[str, str]:
    """
    Verify that ffmpeg and ffprobe are available (bundled, user data, or system PATH).
    If missing and interactive=True with an active Qt application, prompts to auto-download.
    Returns (ffmpeg_path, ffprobe_path) as string paths.
    """
    from app.ffmpeg_manager import FFmpegBootstrapDialog, get_ffmpeg_and_ffprobe
    from PySide6.QtWidgets import QApplication

    ffmpeg, ffprobe = get_ffmpeg_and_ffprobe()

    if (not ffmpeg or not ffprobe) and interactive and QApplication.instance():
        dialog = FFmpegBootstrapDialog()
        if dialog.exec() == FFmpegBootstrapDialog.DialogCode.Accepted:
            ffmpeg, ffprobe = get_ffmpeg_and_ffprobe()

    if not ffmpeg or not ffprobe:
        if sys.platform == "darwin":
            hint = "Install FFmpeg with Homebrew: brew install ffmpeg"
        elif sys.platform == "win32":
            hint = "Install FFmpeg on Windows using winget: winget install Gyan.FFmpeg\nOr via Chocolatey: choco install ffmpeg"
        else:
            hint = "Install FFmpeg with your package manager (e.g. sudo apt install ffmpeg)"
        raise ToolNotFoundError(f"FFmpeg or ffprobe was not found.\n\n{hint}")

    return str(ffmpeg), str(ffprobe)


def get_app_cache_dir(app_name: str = "MediaStudio") -> Path:
    """
    Return a cross-platform temporary cache directory.
    Uses QStandardPaths if available, otherwise tempfile.
    """
    try:
        base_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        if base_dir:
            return Path(base_dir) / app_name
    except Exception:
        pass
    return Path(tempfile.gettempdir()) / app_name


def ensure_app_cache_dir(app_name: str = "MediaStudio") -> Path:
    """Ensure that the cache directory exists and return its Path."""
    p = get_app_cache_dir(app_name)
    p.mkdir(parents=True, exist_ok=True)
    return p


def cleanup_app_cache_dir(app_name: str = "MediaStudio") -> None:
    """Safely remove temporary cache directory on shutdown."""
    cache = get_app_cache_dir(app_name)
    if cache.exists():
        try:
            shutil.rmtree(cache)
        except OSError:
            pass


def reveal_in_file_manager(target_path: Path) -> bool:
    """
    Cross-platform method to open a folder or reveal a file in Finder / Windows Explorer / Linux file manager.
    """
    p = Path(target_path).resolve()
    folder_to_open = p if p.is_dir() else p.parent
    if not folder_to_open.exists():
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_to_open)))
