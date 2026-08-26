from __future__ import annotations

import json

import pytest

from app.captured_frame import CropRect
from app.frame_extractor import parse_probe_output
from app.utils import clamp_crop, export_filename, format_timestamp, parse_frame_rate, parse_timestamp


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00.000"),
        (201.42, "00:03:21.420"),
        (1062.105, "00:17:42.105"),
        (4375.33, "01:12:55.330"),
    ],
)
def test_format_timestamp(seconds: float, expected: str) -> None:
    assert format_timestamp(seconds) == expected


def test_parse_timestamp() -> None:
    assert parse_timestamp("00:03:21.420") == pytest.approx(201.42)
    assert parse_timestamp("03:21.4") == pytest.approx(201.4)


def test_parse_frame_rate() -> None:
    assert parse_frame_rate("30000/1001") == pytest.approx(29.97002997)
    assert parse_frame_rate("24") == pytest.approx(24)
    assert parse_frame_rate("0/0") == 0


def test_export_filename() -> None:
    assert export_filename(201.42, "png") == "frame_00-03-21-420.png"
    assert export_filename(1062.105, ".jpg", cropped=True) == "frame_00-17-42-105_crop.jpg"


def test_clamp_crop() -> None:
    crop = clamp_crop(CropRect(x=1900, y=1000, width=400, height=200), 1920, 1080)
    assert crop == CropRect(x=1520, y=880, width=400, height=200)


def test_parse_probe_output() -> None:
    payload = {
        "format": {"duration": "12.5"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "r_frame_rate": "30000/1001",
            }
        ],
    }
    metadata = parse_probe_output(json.dumps(payload))
    assert metadata.duration == 12.5
    assert metadata.width == 1920
    assert metadata.height == 1080
    assert metadata.codec == "h264"
    assert metadata.fps == pytest.approx(29.97002997)


def test_common_subprocess_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.common import get_subprocess_kwargs
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    kwargs = get_subprocess_kwargs()
    assert "creationflags" in kwargs

    monkeypatch.setattr(sys, "platform", "darwin")
    kwargs_mac = get_subprocess_kwargs()
    assert kwargs_mac == {}


def test_common_cache_dir() -> None:
    from app.common import ensure_app_cache_dir, get_app_cache_dir

    p = get_app_cache_dir("TestApp")
    assert "TestApp" in str(p)

    ensured = ensure_app_cache_dir("TestApp")
    assert ensured.exists()


