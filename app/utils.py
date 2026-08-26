from __future__ import annotations

import math
import re
from fractions import Fraction
from pathlib import Path

from app.captured_frame import CropRect


TIMESTAMP_RE = re.compile(
    r"^(?:(?P<hours>\d+):)?(?P<minutes>[0-5]?\d):(?P<seconds>[0-5]?\d)(?:\.(?P<millis>\d{1,3}))?$"
)


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def parse_timestamp(text: str) -> float:
    cleaned = text.strip()
    match = TIMESTAMP_RE.match(cleaned)
    if not match:
        raise ValueError("Use HH:MM:SS.mmm, MM:SS.mmm, or MM:SS")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis_text = (match.group("millis") or "0").ljust(3, "0")
    millis = int(millis_text)
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_frame_rate(value: str) -> float:
    if not value or value == "0/0":
        return 0.0
    try:
        if "/" in value:
            rate = Fraction(value)
            return float(rate) if rate.denominator else 0.0
        return float(value)
    except (ValueError, ZeroDivisionError):
        return 0.0


def choose_fps(avg_frame_rate: str, r_frame_rate: str) -> float:
    avg = parse_frame_rate(avg_frame_rate)
    if math.isfinite(avg) and avg > 0:
        return avg
    real = parse_frame_rate(r_frame_rate)
    if math.isfinite(real) and real > 0:
        return real
    return 30.0


def timestamp_for_filename(seconds: float) -> str:
    return format_timestamp(seconds).replace(":", "-").replace(".", "-")


def export_filename(seconds: float, extension: str, cropped: bool = False) -> str:
    suffix = "_crop" if cropped else ""
    clean_ext = extension.lower().lstrip(".")
    return f"frame_{timestamp_for_filename(seconds)}{suffix}.{clean_ext}"


from app.common import ensure_app_cache_dir, get_app_cache_dir


def cache_dir() -> Path:
    return get_app_cache_dir("FrameExtractor")


def ensure_cache_dir() -> Path:
    return ensure_app_cache_dir("FrameExtractor")


def clamp_crop(crop: CropRect, image_width: int, image_height: int) -> CropRect:
    width = max(1, min(crop.width, image_width))
    height = max(1, min(crop.height, image_height))
    x = max(0, min(crop.x, image_width - width))
    y = max(0, min(crop.y, image_height - height))
    return CropRect(x=x, y=y, width=width, height=height)

