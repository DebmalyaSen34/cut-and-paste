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


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def create_macos_archive(app_path: Path, archive_path: Path) -> None:
    """Create a macOS-safe ZIP without flattening framework symlinks."""
    if archive_path.exists():
        archive_path.unlink()
    subprocess.check_call(
        [
            "/usr/bin/ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(app_path),
            str(archive_path),
        ]
    )


def verify_macos_app(app_path: Path) -> None:
    """Fail packaging when any nested framework or executable is malformed."""
    subprocess.check_call(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_path)]
    )


def sign_macos_app(app_path: Path) -> bool:
    """Sign with Developer ID when configured, otherwise create a valid ad-hoc signature."""
    identity = os.environ.get("MACOS_CODESIGN_IDENTITY", "").strip() or "-"
    command = ["/usr/bin/codesign", "--force", "--deep", "--sign", identity]
    if identity != "-":
        command[3:3] = ["--options", "runtime", "--timestamp"]
        print(f"\n[*] Signing macOS app with identity: {identity}")
    else:
        print("\n[!] No Developer ID configured; applying a valid ad-hoc signature.")
        print("    The app will require right-click > Open on first launch.")
    command.append(str(app_path))
    subprocess.check_call(command)
    verify_macos_app(app_path)
    return identity != "-"


def notarize_macos_app(app_path: Path, archive_path: Path) -> bool:
    """Notarize and staple when all Apple credentials are available."""
    apple_id = os.environ.get("APPLE_ID", "").strip()
    password = os.environ.get("APPLE_APP_SPECIFIC_PASSWORD", "").strip()
    team_id = os.environ.get("APPLE_TEAM_ID", "").strip()
    if not all((apple_id, password, team_id)):
        return False

    print("\n[*] Submitting macOS app to Apple for notarization...")
    subprocess.check_call(
        [
            "/usr/bin/xcrun",
            "notarytool",
            "submit",
            str(archive_path),
            "--apple-id",
            apple_id,
            "--password",
            password,
            "--team-id",
            team_id,
            "--wait",
        ]
    )
    subprocess.check_call(["/usr/bin/xcrun", "stapler", "staple", str(app_path)])
    subprocess.check_call(["/usr/bin/xcrun", "stapler", "validate", str(app_path)])
    verify_macos_app(app_path)
    subprocess.check_call(
        ["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=2", str(app_path)]
    )
    create_macos_archive(app_path, archive_path)
    return True


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
        print(f"\n[OK] Found bundled FFmpeg binaries in {BIN_DIR}")

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
            archive_path = DIST_DIR / "MediaStudio-macOS.zip"
            has_developer_signature = sign_macos_app(app_path)
            create_macos_archive(app_path, archive_path)
            notarized = has_developer_signature and notarize_macos_app(app_path, archive_path)
            if has_developer_signature and not notarized:
                print("\n[!] Developer ID signature applied, but notarization credentials were not provided.")
            print(f"\n[SUCCESS] macOS standalone app created:")
            print(f"     -> {DIST_DIR / 'MediaStudio.app'}")
            print(f"     -> {archive_path}")
    elif sys.platform == "win32":
        exe_path = DIST_DIR / "MediaStudio.exe"
        if exe_path.exists():
            zip_out = DIST_DIR / "MediaStudio-Windows"
            shutil.make_archive(str(zip_out), "zip", root_dir=str(DIST_DIR), base_dir="MediaStudio.exe")
            print(f"\n[SUCCESS] Windows standalone executable created:")
            print(f"     -> {DIST_DIR / 'MediaStudio.exe'}")
            print(f"     -> {DIST_DIR / 'MediaStudio-Windows.zip'}")
    else:
        print(f"\n[SUCCESS] Build output located in {DIST_DIR}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
