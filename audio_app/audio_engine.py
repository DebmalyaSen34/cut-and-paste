from __future__ import annotations

import json
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Callable

from app.common import ToolNotFoundError, get_subprocess_kwargs, require_ffmpeg_tools
from audio_app.models import AudioMetadata, AudioSegment, ExportSettings
from audio_app.utils import format_timestamp, sanitize_filename


class AudioEngineError(RuntimeError):
    pass


def require_audio_tools() -> tuple[str, str]:
    """Verify that ffmpeg and ffprobe are installed and discoverable."""
    try:
        return require_ffmpeg_tools()
    except ToolNotFoundError as exc:
        raise AudioEngineError(str(exc)) from exc


def probe_audio(audio_path: Path) -> AudioMetadata:
    """Extract technical audio metadata from any audio/video container using ffprobe."""
    _, ffprobe = require_audio_tools()
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(audio_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **get_subprocess_kwargs(),
    )
    if result.returncode != 0:
        raise AudioEngineError(result.stderr.strip() or f"Failed to probe file: {audio_path.name}")

    return parse_audio_probe(result.stdout, audio_path)


def parse_audio_probe(raw_json: str, audio_path: Path) -> AudioMetadata:
    """Parse ffprobe JSON output into AudioMetadata."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise AudioEngineError("Invalid metadata response from ffprobe.") from exc

    streams = data.get("streams", [])
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not audio_stream:
        raise AudioEngineError(f"No audio stream found in '{audio_path.name}'.")

    format_info = data.get("format", {})
    dur_str = audio_stream.get("duration") or format_info.get("duration") or "0"
    try:
        duration = max(0.0, float(dur_str))
    except (ValueError, TypeError):
        duration = 0.0

    sample_rate = int(audio_stream.get("sample_rate") or 44100)
    channels = int(audio_stream.get("channels") or 2)
    bit_rate_str = audio_stream.get("bit_rate") or format_info.get("bit_rate") or "0"
    try:
        bit_rate = int(bit_rate_str)
    except (ValueError, TypeError):
        bit_rate = 0

    codec = str(audio_stream.get("codec_name") or "unknown")
    format_name = str(format_info.get("format_name") or audio_path.suffix.lstrip("."))

    try:
        file_size = int(format_info.get("size") or (audio_path.stat().st_size if audio_path.exists() else 0))
    except Exception:
        file_size = 0

    return AudioMetadata(
        path=audio_path,
        duration=duration,
        sample_rate=sample_rate,
        channels=channels,
        bit_rate=bit_rate,
        codec=codec,
        format_name=format_name,
        file_size=file_size,
    )


def extract_waveform_peaks(audio_path: Path, num_peaks: int = 1500) -> list[tuple[float, float]]:
    """
    Extract downsampled audio waveform amplitude min/max peaks for UI rendering.
    Uses ffmpeg to pipe raw 16-bit mono PCM at 8000 Hz.
    Returns list of (min_peak, max_peak) in range [-1.0, 1.0].
    """
    ffmpeg, _ = require_audio_tools()
    target_hz = 8000
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-ac",
        "1",  # mono
        "-ar",
        str(target_hz),
        "-f",
        "s16le",  # 16-bit signed little-endian PCM
        "-",
    ]

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **get_subprocess_kwargs(),
    )
    raw_pcm, stderr_data = proc.communicate()
    if proc.returncode != 0 and not raw_pcm:
        raise AudioEngineError(stderr_data.decode("utf-8", errors="replace").strip() or "Waveform extraction failed.")

    if not raw_pcm:
        return [(0.0, 0.0)] * num_peaks

    # Unpack 16-bit signed integers (-32768 to 32767)
    sample_count = len(raw_pcm) // 2
    if sample_count == 0:
        return [(0.0, 0.0)] * num_peaks

    # Unpack samples efficiently
    samples = struct.unpack(f"<{sample_count}h", raw_pcm[: sample_count * 2])

    if num_peaks <= 0:
        num_peaks = 1000

    bucket_size = max(1, sample_count // num_peaks)
    peaks: list[tuple[float, float]] = []

    for i in range(num_peaks):
        start_idx = i * bucket_size
        end_idx = min(sample_count, (i + 1) * bucket_size)
        if start_idx >= sample_count:
            peaks.append((0.0, 0.0))
            continue

        chunk = samples[start_idx:end_idx]
        if not chunk:
            peaks.append((0.0, 0.0))
            continue

        min_val = min(chunk) / 32768.0
        max_val = max(chunk) / 32768.0
        peaks.append((min_val, max_val))

    return peaks


def _get_codec_args(export_format: str, bitrate: str) -> list[str]:
    """Return ffmpeg audio encoder arguments based on format and bitrate."""
    fmt = export_format.lower().lstrip(".")
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", bitrate or "320k"]
    elif fmt == "wav":
        return ["-c:a", "pcm_s16le"]
    elif fmt in {"m4a", "aac"}:
        return ["-c:a", "aac", "-b:a", bitrate or "256k"]
    elif fmt == "flac":
        return ["-c:a", "flac"]
    elif fmt == "ogg":
        return ["-c:a", "libvorbis", "-q:a", "6"]
    else:
        return ["-c:a", "libmp3lame", "-b:a", "320k"]


def build_filter_graph(
    segments: list[AudioSegment],
    crossfade_ms: int = 0,
    normalize: bool = False,
) -> tuple[str, str]:
    """
    Build ffmpeg complex filter graph string and the output audio map label.
    Returns (filter_complex_string, output_label).
    """
    if not segments:
        raise AudioEngineError("No segments provided for audio processing.")

    filter_parts: list[str] = []
    num_segs = len(segments)

    # Step 1: Trim all segments
    for idx, seg in enumerate(segments):
        start_s = f"{seg.start:.4f}"
        end_s = f"{seg.end:.4f}"
        filter_parts.append(
            f"[0:a]atrim=start={start_s}:end={end_s},asetpts=PTS-STARTPTS[seg{idx}]"
        )

    # Step 2: Combine segments (with or without crossfade)
    if num_segs == 1:
        current_label = "seg0"
    elif crossfade_ms <= 0:
        # Simple seamless concat
        inputs_str = "".join(f"[seg{i}]" for i in range(num_segs))
        filter_parts.append(f"{inputs_str}concat=n={num_segs}:v=0:a=1[concata]")
        current_label = "concata"
    else:
        # Crossfade daisy chain
        xfade_sec = max(0.01, crossfade_ms / 1000.0)
        current_label = "seg0"
        for i in range(1, num_segs):
            next_seg = f"seg{i}"
            out_label = f"xf{i}"
            filter_parts.append(
                f"[{current_label}][{next_seg}]acrossfade=d={xfade_sec:.3f}:c1=tri:c2=tri[{out_label}]"
            )
            current_label = out_label

    # Step 3: Loudness normalization if requested
    if normalize:
        norm_label = "norma"
        filter_parts.append(f"[{current_label}]loudnorm[{norm_label}]")
        current_label = norm_label

    return ";".join(filter_parts), f"[{current_label}]"


def cut_single_segment(
    source_path: Path,
    start: float,
    end: float,
    output_path: Path,
    export_format: str = "mp3",
    bitrate: str = "320k",
) -> Path:
    """Cut a single section from source audio file."""
    ffmpeg, _ = require_audio_tools()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = max(0.001, end - start)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.4f}",
        "-t",
        f"{duration:.4f}",
        "-i",
        str(source_path),
    ]
    command.extend(_get_codec_args(export_format, bitrate))
    command.append(str(output_path))

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **get_subprocess_kwargs(),
    )
    if result.returncode != 0:
        raise AudioEngineError(result.stderr.strip() or "Failed to cut audio segment.")

    return output_path


def merge_segments(
    source_path: Path,
    segments: list[AudioSegment],
    settings: ExportSettings,
    progress_callback: Callable[[str], None] | None = None,
) -> Path:
    """
    Merge multiple segments from source audio file into a single file in the exact given sequence.
    """
    ffmpeg, _ = require_audio_tools()
    active_segments = [s for s in segments if s.enabled and s.duration > 0.01]
    if not active_segments:
        raise AudioEngineError("No active segments selected to merge.")

    output_path = settings.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filter_complex, out_map = build_filter_graph(
        active_segments,
        crossfade_ms=settings.crossfade_ms,
        normalize=settings.normalize,
    )

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-filter_complex",
        filter_complex,
        "-map",
        out_map,
    ]
    command.extend(_get_codec_args(settings.format, settings.bitrate))
    command.append(str(output_path))

    if progress_callback:
        progress_callback(f"Merging {len(active_segments)} segments...")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **get_subprocess_kwargs(),
    )
    if result.returncode != 0:
        raise AudioEngineError(result.stderr.strip() or "Audio merge processing failed.")

    return output_path


def export_batch_segments(
    source_path: Path,
    segments: list[AudioSegment],
    output_dir: Path,
    settings: ExportSettings,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    """Export each active segment as an individual file into the output directory."""
    active_segments = [s for s in segments if s.enabled and s.duration > 0.01]
    if not active_segments:
        raise AudioEngineError("No active segments to export.")

    output_dir.mkdir(parents=True, exist_ok=True)
    exported_files: list[Path] = []
    ext = settings.format.lower().lstrip(".")

    for idx, seg in enumerate(active_segments, start=1):
        name = sanitize_filename(seg.name or f"segment_{idx:02d}")
        out_file = output_dir / f"{name}.{ext}"

        if progress_callback:
            progress_callback(idx, len(active_segments), out_file.name)

        cut_single_segment(
            source_path=source_path,
            start=seg.start,
            end=seg.end,
            output_path=out_file,
            export_format=settings.format,
            bitrate=settings.bitrate,
        )
        exported_files.append(out_file)

    return exported_files
