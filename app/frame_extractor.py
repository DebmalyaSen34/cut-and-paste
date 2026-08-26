from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.captured_frame import CropRect, VideoMetadata
from app.common import ToolNotFoundError, get_subprocess_kwargs, require_ffmpeg_tools
from app.utils import choose_fps, format_timestamp


class FfmpegError(RuntimeError):
    pass


def require_video_tools() -> tuple[str, str]:
    try:
        return require_ffmpeg_tools()
    except ToolNotFoundError as exc:
        raise FfmpegError(str(exc)) from exc


def probe_video(video_path: Path) -> VideoMetadata:
    _, ffprobe = require_video_tools()
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **get_subprocess_kwargs(),
    )
    if result.returncode != 0:
        raise FfmpegError(result.stderr.strip() or "Unable to read video metadata.")

    return parse_probe_output(result.stdout)


def parse_probe_output(raw_json: str) -> VideoMetadata:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise FfmpegError("ffprobe returned invalid metadata.") from exc

    streams = payload.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if not video_stream:
        raise FfmpegError("No video stream found in the selected file.")

    format_info = payload.get("format", {})
    duration_text = video_stream.get("duration") or format_info.get("duration") or "0"
    try:
        duration = float(duration_text)
    except (TypeError, ValueError):
        duration = 0.0

    avg_frame_rate = str(video_stream.get("avg_frame_rate") or "")
    r_frame_rate = str(video_stream.get("r_frame_rate") or "")
    return VideoMetadata(
        duration=max(0.0, duration),
        width=int(video_stream.get("width") or 0),
        height=int(video_stream.get("height") or 0),
        fps=choose_fps(avg_frame_rate, r_frame_rate),
        codec=str(video_stream.get("codec_name") or "unknown"),
        avg_frame_rate=avg_frame_rate,
        r_frame_rate=r_frame_rate,
    )


def extract_frame(video_path: Path, timestamp: float, output_path: Path) -> Path:
    ffmpeg, _ = require_video_tools()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        format_timestamp(timestamp),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(output_path),
    ]
    _run_ffmpeg(command, "Frame extraction failed.")
    return output_path


def export_frame(
    video_path: Path,
    timestamp: float,
    output_path: Path,
    crop: CropRect | None,
    overwrite: bool = False,
) -> Path:
    ffmpeg, _ = require_video_tools()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
        "-ss",
        format_timestamp(timestamp),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
    ]
    if crop:
        command.extend(["-vf", crop.as_ffmpeg_filter()])
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        command.extend(["-q:v", "2"])
    command.append(str(output_path))

    _run_ffmpeg(command, "Frame export failed.")
    return output_path


def _run_ffmpeg(command: list[str], fallback_message: str) -> None:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **get_subprocess_kwargs(),
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "File '" in stderr and "already exists" in stderr:
            raise FfmpegError("Output file already exists.")
        raise FfmpegError(stderr or fallback_message)

