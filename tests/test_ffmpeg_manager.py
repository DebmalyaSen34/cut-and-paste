from __future__ import annotations

import sys
from pathlib import Path
import pytest

from app.ffmpeg_manager import (
    find_bundled_or_local_tool,
    get_ffmpeg_and_ffprobe,
    get_user_bin_dir,
)


def test_get_user_bin_dir() -> None:
    user_bin = get_user_bin_dir()
    assert ".mediastudio" in str(user_bin)
    assert user_bin.exists()


def test_find_bundled_or_local_tool_with_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Create fake binary in temp dir
    fake_ffmpeg = tmp_path / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    fake_ffmpeg.write_text("#!/bin/sh\necho ffmpeg")

    # Set mock _MEIPASS
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    found = find_bundled_or_local_tool("ffmpeg")
    assert found is not None
    assert found == fake_ffmpeg


def test_get_ffmpeg_and_ffprobe() -> None:
    # Ensure call succeeds without crashing
    ffmpeg, ffprobe = get_ffmpeg_and_ffprobe()
    # On dev machine with ffmpeg installed, it should find paths; or None in isolated test
    if ffmpeg:
        assert isinstance(ffmpeg, Path)
    if ffprobe:
        assert isinstance(ffprobe, Path)
