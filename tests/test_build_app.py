from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_app import create_macos_archive


@pytest.mark.skipif(sys.platform != "darwin", reason="ditto is a macOS packaging tool")
def test_macos_archive_preserves_framework_symlinks(tmp_path: Path) -> None:
    app_path = tmp_path / "Example.app"
    framework = app_path / "Contents" / "Frameworks" / "Example.framework"
    version = framework / "Versions" / "A"
    resources = version / "Resources"
    resources.mkdir(parents=True)
    executable = version / "Example"
    executable.write_bytes(b"test executable")

    (framework / "Versions" / "Current").symlink_to("A", target_is_directory=True)
    (framework / "Example").symlink_to("Versions/Current/Example")
    (framework / "Resources").symlink_to("Versions/Current/Resources", target_is_directory=True)

    archive_path = tmp_path / "Example.zip"
    create_macos_archive(app_path, archive_path)

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    subprocess.check_call(["/usr/bin/ditto", "-x", "-k", str(archive_path), str(extracted)])

    restored_framework = extracted / "Example.app" / "Contents" / "Frameworks" / "Example.framework"
    assert (restored_framework / "Versions" / "Current").is_symlink()
    assert (restored_framework / "Example").is_symlink()
    assert (restored_framework / "Resources").is_symlink()
