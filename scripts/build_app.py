#!/usr/bin/env python3
"""
One-command builder to create standalone, zero-install distribution packages
for non-technical users on macOS and Windows.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT_DIR / "bin"
DIST_DIR = ROOT_DIR / "dist"


def main() -> int:
    print("==================================================")
    print("  Media Studio Standalone Packaging Builder")
    print("==================================================")

    # Step 1: Ensure static FFmpeg binaries exist
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    ffmpeg_bin = BIN_DIR / f"ffmpeg{exe_suffix}"
    ffprobe_bin = BIN_DIR / f"ffprobe{exe_suffix}"

    if not (ffmpeg_bin.is_file() and ffprobe_bin.is_file()):
        print("\n[*] Bundled FFmpeg binaries not found. Downloading...")
        from download_ffmpeg import download_and_extract
        download_and_extract()
    else:
        print(f"\n[✓] Found bundled FFmpeg binaries in {BIN_DIR}")

    # Step 2: Run PyInstaller
    print("\n[*] Building standalone application with PyInstaller...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "MediaStudio.spec",
        "--clean",
        "-y",
    ]
    subprocess.check_call(cmd, cwd=str(ROOT_DIR))

    # Step 3: Package final archive
    print("\n[*] Packaging distribution archive...")
    if sys.platform == "darwin":
        app_path = DIST_DIR / "MediaStudio.app"
        if app_path.exists():
            zip_out = DIST_DIR / "MediaStudio-macOS"
            shutil.make_archive(str(zip_out), "zip", root_dir=str(DIST_DIR), base_dir="MediaStudio.app")
            print(f"\n[🎉] SUCCESS! macOS standalone app created:")
            print(f"     -> {DIST_DIR / 'MediaStudio.app'}")
            print(f"     -> {DIST_DIR / 'MediaStudio-macOS.zip'}")
    elif sys.platform == "win32":
        exe_path = DIST_DIR / "MediaStudio.exe"
        if exe_path.exists():
            zip_out = DIST_DIR / "MediaStudio-Windows"
            shutil.make_archive(str(zip_out), "zip", root_dir=str(DIST_DIR), base_dir="MediaStudio.exe")
            print(f"\n[🎉] SUCCESS! Windows standalone executable created:")
            print(f"     -> {DIST_DIR / 'MediaStudio.exe'}")
            print(f"     -> {DIST_DIR / 'MediaStudio-Windows.zip'}")
    else:
        print(f"\n[🎉] SUCCESS! Build output located in {DIST_DIR}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
