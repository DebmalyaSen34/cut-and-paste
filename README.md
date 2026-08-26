# Media Studio (Frame Extractor & Audio Cutter/Merger)

A unified, high-performance cross-platform desktop application built with **Python**, **PySide6 (Qt 6)**, and **FFmpeg** for:
1. **Video Frame Extraction & Cropping**: Extract full-resolution video frames at arbitrary timestamps and apply non-destructive crop metadata before export.
2. **Audio Cutting & Merging**: Interactive waveform editing, trimming, reordering multiple segments, seamless merging with crossfades, and batch exporting.

Works seamlessly on both **macOS** and **Windows** (as well as Linux).

---

## 🚀 For Non-Technical Users (Zero-Install / Click & Run)

No terminal, no Python, and no Homebrew or winget required:

- **macOS**: Download `MediaStudio-macOS.zip` (or `.dmg`) from GitHub Releases -> Unzip -> Open `MediaStudio.app`.
- **Windows**: Download `MediaStudio-Windows.zip` from GitHub Releases -> Unzip -> Double-click `MediaStudio.exe`.

> All media tools (including static FFmpeg & FFprobe) are fully embedded inside the package!

---

## 🛠 For Developers / Running from Source

If you are developing or running directly from source:

- **Python**: 3.11+
- **uv** (recommended) or standard Python `pip`

```bash
uv sync
uv run main.py
```
*(If FFmpeg is not found on your system when running from source, Media Studio will display a 1-click dialog to download and set it up automatically).*

### Building Standalone Packages Locally

To build standalone distribution packages with embedded FFmpeg:

```bash
# Downloads static FFmpeg into ./bin/ and packages with PyInstaller:
python scripts/build_app.py
```
Output archives will be generated in `dist/`.

---

## 🎬 Video Frame Extractor Features

- **High-Precision Frame Capturing**: Capture full-resolution frames at any arbitrary timestamp using FFmpeg directly.
- **Non-Destructive Crop Editor**: Interactive visual crop box and manual coordinate inputs (X, Y, Width, Height) applied on export via FFmpeg's `crop` filter.
- **Optimized for Large Files**: Smooth interactive preview for standard videos with automatic still-preview fallback for large video files.
- **Export Options**: Export selected or all captured frames as PNG or JPEG without re-encoding original source video.

### Video Keyboard Shortcuts
| Shortcut | Action |
| --- | --- |
| `Space` | Play / Pause |
| `Left` / `Right` | Previous frame / Next frame |
| `Shift + Left` / `Shift + Right` | Jump backward / forward 5s |
| `C` | Capture current frame |
| `Delete` | Delete selected frame from list |

---

## 🎵 Audio Cutter & Merger Features

- **Wide Format Support**: MP3, WAV, AAC/M4A, FLAC, OGG, Opus, AIFF, plus direct audio extraction from video files (`.mp4`, `.mkv`, `.mov`).
- **Interactive Waveform Display**: High-speed peak rendering, draggable playhead, draggable In/Out handles, zoom in/out, and live scrubbing.
- **Segment Management**:
  - Add selections as segments (`A` or `Enter`).
  - Split at playhead (`S`).
  - Reorder segments with **Move Up** / **Move Down** to customize the merge sequence.
  - Live audition / preview individual segments.
  - Rename segments and edit timestamps directly in the table.
  - Enable/disable segments to include or exclude from the output.
- **Export & Merging Options**:
  - **Merge All**: Concat active segments in sequence into a single file with sample accuracy.
  - **Optional Crossfade**: Smooth transition crossfades (50ms, 100ms, 250ms, 500ms, 1.0s).
  - **Batch Export**: Export each segment as a separate audio file.
  - **Target Formats**: MP3, WAV, M4A, FLAC, OGG with configurable bitrates (320 kbps, 256 kbps, 192 kbps, 128 kbps).
  - **Loudness Normalization**: Optional EBU R128 loudness normalization.

### Audio Keyboard Shortcuts
| Shortcut | Action |
| --- | --- |
| `Space` | Play / Pause |
| `Left` / `Right` | Seek backward / forward 1s |
| `Shift + Left` / `Shift + Right` | Seek backward / forward 5s |
| `I` | Set In point (Selection Start) to current playhead |
| `O` | Set Out point (Selection End) to current playhead |
| `A` / `Enter` | Add current selection as a Segment |
| `S` | Split segment at playhead |
| `Delete` | Remove selected segment |
| `Ctrl + E` / `Cmd + E` | Open Export & Merge Dialog |
| `Ctrl + O` / `Cmd + O` | Open Audio File |

---

## 💻 Cross-Platform Highlights

- **Native Folder Revealing**: Opening completed export directories uses Qt's `QDesktopServices` to open **Finder** on macOS and **File Explorer** on Windows.
- **No Console Flashing on Windows**: Subprocess calls use `subprocess.CREATE_NO_WINDOW` on Windows to suppress terminal popups.
- **Standardized OS Cache**: Temporary frames and audio waveforms use standard OS cache paths (`QStandardPaths`), automatically cleaned up on exit.

---

## 🧪 Testing

Run automated tests:

```bash
uv run pytest
```
