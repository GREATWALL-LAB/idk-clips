"""Cut, reframe, caption and encode one clip with FFmpeg.

Supported output aspect ratios (always encoded with square pixels, never stretched):

=========  ===========  =========================================
Ratio      Size         Typical use
=========  ===========  =========================================
9:16       1080 x 1920  TikTok, Instagram Reels, YouTube Shorts
4:5        1080 x 1350  Instagram / Facebook feed (portrait)
1:1        1080 x 1080  Square posts
16:9       1920 x 1080  YouTube, LinkedIn, X (landscape)
=========  ===========  =========================================

Framing modes:
- ``crop``: fill the frame. The largest window with the target ratio is cut from
  the source (no distortion) and moved by ``crop_position`` (0 = left/top,
  1 = right/bottom) along whichever axis is being cropped.
- ``fit``: show the whole source frame, scaled down without distortion, over a
  blurred and zoomed copy of itself that fills the remaining space.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openclip_processing.ffmpeg import FFmpegTools
from openclip_processing.types import CancelCheck, ProgressCallback, never_cancel, no_progress

ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
DEFAULT_ASPECT_RATIO = "9:16"
LAYOUTS = ("crop", "fit", "original")

# Kept for callers that only need the vertical size.
VERTICAL_SIZE = ASPECT_RATIOS["9:16"]


@dataclass
class RenderSpec:
    source: Path
    output: Path
    start: float
    end: float
    layout: str = "crop"  # crop | fit | original (original keeps the source frame)
    crop_position: float = 0.5  # subject position along the cropped axis (0..1)
    aspect_ratio: str = DEFAULT_ASPECT_RATIO
    source_width: int | None = None
    source_height: int | None = None
    subtitles: str | None = None  # file name inside ``workdir``
    fonts_dir: str | None = None  # folder name inside ``workdir``
    workdir: Path | None = None
    encoder: str = "libx264"

    @property
    def duration(self) -> float:
        return self.end - self.start

    def output_size(self) -> tuple[int, int]:
        if self.layout == "original":
            width = (self.source_width or 1280) // 2 * 2
            height = (self.source_height or 720) // 2 * 2
            return width, height
        if self.aspect_ratio not in ASPECT_RATIOS:
            raise ValueError(f"Unsupported aspect ratio {self.aspect_ratio!r}")
        return ASPECT_RATIOS[self.aspect_ratio]


def build_video_filter(spec: RenderSpec) -> str:
    """Filter graph from input [0:v] to output [v]."""
    if spec.layout not in LAYOUTS:
        raise ValueError(f"Unknown layout {spec.layout!r}")
    width, height = spec.output_size()
    position = min(max(float(spec.crop_position), 0.0), 1.0)
    if spec.layout == "crop":
        # Largest window with exactly the target ratio (even sizes), positioned along the
        # cropped axis. Only one of (iw-ow) and (ih-oh) is non-zero, so one position works.
        graph = (
            f"[0:v]crop=w='trunc(min(iw,ih*{width}/{height})/2)*2'"
            f":h='trunc(min(ih,iw*{height}/{width})/2)*2'"
            f":x='(iw-ow)*{position:.3f}':y='(ih-oh)*{position:.3f}',"
            f"scale={width}:{height}:flags=lanczos,setsar=1"
        )
    elif spec.layout == "fit":
        # Whole frame (never distorted) over a blurred, zoomed copy of itself.
        bg_w, bg_h = max(width // 4 // 2 * 2, 2), max(height // 4 // 2 * 2, 2)
        graph = (
            "[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={bg_w}:{bg_h}:force_original_aspect_ratio=increase,crop={bg_w}:{bg_h},"
            f"boxblur=10:2,scale={width}:{height},eq=brightness=-0.06[bg];"
            f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    else:
        graph = f"[0:v]scale={width}:{height}:flags=lanczos,setsar=1"
    if spec.subtitles:
        # Relative names only (the process runs inside ``workdir``), so no path escaping issues.
        fonts = f":fontsdir={spec.fonts_dir}" if spec.fonts_dir else ""
        graph += f",subtitles=filename={spec.subtitles}{fonts}"
    return graph + ",format=yuv420p[v]"


def encoder_args(encoder: str) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "23", "-b:v", "0"]  # fmt: skip
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high"]


def build_args(spec: RenderSpec) -> list[str]:
    return [
        "-ss", f"{spec.start:.3f}",
        "-i", str(spec.source),
        "-t", f"{spec.duration:.3f}",
        "-filter_complex", build_video_filter(spec),
        "-map", "[v]",
        "-map", "0:a:0?",
        *encoder_args(spec.encoder),
        "-r", "30",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(spec.output),
    ]  # fmt: skip


def render_clip(
    ffmpeg: FFmpegTools,
    spec: RenderSpec,
    *,
    progress: ProgressCallback = no_progress,
    should_cancel: CancelCheck = never_cancel,
) -> Path:
    spec.output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        build_args(spec),
        duration=spec.duration,
        progress=progress,
        should_cancel=should_cancel,
        stage="Rendering video",
        cwd=spec.workdir,
    )
    return spec.output
