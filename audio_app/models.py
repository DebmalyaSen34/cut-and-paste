from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AudioMetadata:
    path: Path
    duration: float
    sample_rate: int
    channels: int
    bit_rate: int
    codec: str
    format_name: str
    file_size: int

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def duration_formatted(self) -> str:
        from audio_app.utils import format_timestamp
        return format_timestamp(self.duration)


@dataclass
class AudioSegment:
    start: float
    end: float
    name: str = ""
    enabled: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def clamp(self, max_duration: float) -> AudioSegment:
        s = max(0.0, min(self.start, max_duration))
        e = max(s, min(self.end, max_duration))
        return AudioSegment(start=s, end=e, name=self.name, enabled=self.enabled, id=self.id)


@dataclass
class ExportSettings:
    output_path: Path
    format: str = "mp3"
    bitrate: str = "320k"
    crossfade_ms: int = 0
    normalize: bool = False
    mode: str = "merge"  # "merge" or "batch"
