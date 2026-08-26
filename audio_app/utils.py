from __future__ import annotations

import re
from pathlib import Path

# Match HH:MM:SS.mmm, MM:SS.mmm, or SS.mmm
TIMESTAMP_RE = re.compile(
    r"^(?:(?:(?P<hours>\d+):)?(?P<minutes>[0-5]?\d):)?(?P<seconds>[0-5]?\d)(?:\.(?P<millis>\d{1,3}))?$"
)


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS.mmm."""
    seconds = max(0.0, float(seconds))
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def format_timestamp_short(seconds: float) -> str:
    """Format seconds into MM:SS or HH:MM:SS for compact UI labels."""
    seconds = max(0.0, float(seconds))
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_timestamp(text: str) -> float:
    """Parse time string into float seconds."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Empty timestamp string.")

    # Try direct float first
    try:
        val = float(cleaned)
        if val >= 0:
            return val
    except ValueError:
        pass

    match = TIMESTAMP_RE.match(cleaned)
    if not match:
        raise ValueError("Invalid timestamp format. Use HH:MM:SS.mmm, MM:SS.mmm, or seconds.")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    millis_raw = match.group("millis") or "0"
    millis = int(millis_raw.ljust(3, "0")[:3])

    return hours * 3600 + minutes * 60 + seconds + (millis / 1000.0)


def sanitize_filename(name: str) -> str:
    """Remove unsafe characters from a proposed filename."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return cleaned or "segment"


from app.common import ensure_app_cache_dir, get_app_cache_dir


def cache_dir() -> Path:
    return get_app_cache_dir("AudioCutterMerger")


def ensure_cache_dir() -> Path:
    return ensure_app_cache_dir("AudioCutterMerger")


SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".opus",
    ".wma",
    ".aiff",
    ".aif",
    # Also support extracting audio from video files:
    ".mp4",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
}
