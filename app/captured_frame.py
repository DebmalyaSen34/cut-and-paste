from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CropRect:
    x: int
    y: int
    width: int
    height: int

    def as_ffmpeg_filter(self) -> str:
        return f"crop={self.width}:{self.height}:{self.x}:{self.y}"


@dataclass(frozen=True)
class VideoMetadata:
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    avg_frame_rate: str
    r_frame_rate: str


@dataclass
class CapturedFrame:
    timestamp: float
    path: Path
    width: int
    height: int
    crop: CropRect | None = None

    @property
    def is_cropped(self) -> bool:
        return self.crop is not None

