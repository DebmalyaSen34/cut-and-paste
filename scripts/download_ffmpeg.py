#!/usr/bin/env python3
"""
Helper script to download static FFmpeg & FFprobe binaries into the local ./bin/ directory
for standalone PyInstaller packaging.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
import tarfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT_DIR / "bin"


def get_download_url() -> str:
    system = sys.platform
    arch = platform.machine().lower()

    if system == "win32":
        return "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    elif system == "darwin":
        # yt-dlp builds static universal/arm64 macOS ffmpeg builds
        if "arm" in arch or "aarch64" in arch:
            return "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-osxarm64-gpl.tar.xz"
        else:
            return "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-osx64-gpl.tar.xz"
    elif system == "linux":
        return "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
    else:
        raise RuntimeError(f"Unsupported OS: {system}")


def download_and_extract() -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    url = get_download_url()
    print(f"[*] Downloading static FFmpeg binaries from:\n    {url}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_path = Path(tmp_dir) / "ffmpeg_archive"

        def progress(block_num: int, block_size: int, total_size: int) -> None:
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, int((downloaded / total_size) * 100))
                sys.stdout.write(f"\rDownloading: {percent}% [{downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB]")
                sys.stdout.flush()

        urllib.request.urlretrieve(url, archive_path, reporthook=progress)
        print("\n[*] Unpacking binaries to ./bin/ ...")

        target_names = {"ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"}
        found = set()

        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as z:
                for member in z.namelist():
                    basename = os.path.basename(member)
                    if basename in target_names:
                        out_path = BIN_DIR / basename
                        with z.open(member) as src, open(out_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        _set_executable(out_path)
                        found.add(basename)
        else:
            with tarfile.open(archive_path, "r:*") as t:
                for member in t.getmembers():
                    basename = os.path.basename(member.name)
                    if basename in target_names:
                        out_path = BIN_DIR / basename
                        src = t.extractfile(member)
                        if src:
                            with open(out_path, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            _set_executable(out_path)
                            found.add(basename)

    print(f"[✓] Extracted: {', '.join(found)} into {BIN_DIR}")


def _set_executable(path: Path) -> None:
    if sys.platform != "win32":
        try:
            mode = path.stat().st_mode
            path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass


if __name__ == "__main__":
    download_and_extract()
