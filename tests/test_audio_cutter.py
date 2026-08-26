from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_app.audio_engine import _get_codec_args, build_filter_graph, parse_audio_probe
from audio_app.models import AudioMetadata, AudioSegment
from audio_app.utils import (
    format_timestamp,
    format_timestamp_short,
    parse_timestamp,
    sanitize_filename,
)


def test_format_timestamp() -> None:
    assert format_timestamp(0) == "00:00:00.000"
    assert format_timestamp(65.432) == "00:01:05.432"
    assert format_timestamp(3661.05) == "01:01:01.050"


def test_format_timestamp_short() -> None:
    assert format_timestamp_short(45.2) == "00:45"
    assert format_timestamp_short(125.0) == "02:05"
    assert format_timestamp_short(3665.0) == "01:01:05"


def test_parse_timestamp() -> None:
    assert parse_timestamp("00:01:05.432") == pytest.approx(65.432)
    assert parse_timestamp("01:05.432") == pytest.approx(65.432)
    assert parse_timestamp("65.432") == pytest.approx(65.432)
    assert parse_timestamp("02:30") == pytest.approx(150.0)
    assert parse_timestamp("01:00:00") == pytest.approx(3600.0)


def test_sanitize_filename() -> None:
    assert sanitize_filename("my / segment * 1 ?") == "my  segment  1"
    assert sanitize_filename("   ") == "segment"


def test_audio_segment_properties() -> None:
    seg = AudioSegment(start=10.0, end=25.5, name="Intro")
    assert seg.duration == pytest.approx(15.5)

    clamped = seg.clamp(20.0)
    assert clamped.start == 10.0
    assert clamped.end == 20.0
    assert clamped.duration == 10.0


def test_parse_audio_probe() -> None:
    payload = {
        "format": {
            "duration": "180.5",
            "format_name": "mp3",
            "size": "5776000",
            "bit_rate": "256000",
        },
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "mp3",
                "sample_rate": "48000",
                "channels": 2,
                "bit_rate": "256000",
                "duration": "180.5",
            }
        ],
    }
    meta = parse_audio_probe(json.dumps(payload), Path("/fake/audio.mp3"))
    assert meta.duration == 180.5
    assert meta.sample_rate == 48000
    assert meta.channels == 2
    assert meta.codec == "mp3"
    assert meta.bit_rate == 256000


def test_get_codec_args() -> None:
    assert _get_codec_args("mp3", "320k") == ["-c:a", "libmp3lame", "-b:a", "320k"]
    assert _get_codec_args("wav", "") == ["-c:a", "pcm_s16le"]
    assert _get_codec_args("flac", "") == ["-c:a", "flac"]
    assert _get_codec_args("m4a", "256k") == ["-c:a", "aac", "-b:a", "256k"]


def test_build_filter_graph_single_segment() -> None:
    segs = [AudioSegment(start=5.0, end=15.0)]
    filter_str, out_label = build_filter_graph(segs, crossfade_ms=0, normalize=False)
    assert "[0:a]atrim=start=5.0000:end=15.0000,asetpts=PTS-STARTPTS[seg0]" in filter_str
    assert out_label == "[seg0]"


def test_build_filter_graph_concat_multiple() -> None:
    segs = [
        AudioSegment(start=0.0, end=10.0),
        AudioSegment(start=30.0, end=45.0),
        AudioSegment(start=60.0, end=75.0),
    ]
    filter_str, out_label = build_filter_graph(segs, crossfade_ms=0, normalize=False)
    assert "concat=n=3:v=0:a=1[concata]" in filter_str
    assert out_label == "[concata]"


def test_build_filter_graph_crossfade() -> None:
    segs = [
        AudioSegment(start=0.0, end=10.0),
        AudioSegment(start=30.0, end=45.0),
    ]
    filter_str, out_label = build_filter_graph(segs, crossfade_ms=200, normalize=False)
    assert "acrossfade=d=0.200:c1=tri:c2=tri[xf1]" in filter_str
    assert out_label == "[xf1]"


def test_build_filter_graph_normalize() -> None:
    segs = [AudioSegment(start=0.0, end=10.0)]
    filter_str, out_label = build_filter_graph(segs, crossfade_ms=0, normalize=True)
    assert "loudnorm[norma]" in filter_str
    assert out_label == "[norma]"
