"""FFmpeg / FFprobe wrapper: probing, audio extraction, thumbnails and rendering.

Commands are always passed as argument lists (never through a shell), so file
names cannot inject options or commands. Progress comes from FFmpeg's own
``-progress`` output, so the reported percentage reflects real work.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from openclip_processing.binaries import CREATE_NO_WINDOW, find_executable
from openclip_processing.errors import (
    FFmpegError,
    FFmpegNotFoundError,
    JobCancelled,
    MediaValidationError,
)
from openclip_processing.types import CancelCheck, ProgressCallback, never_cancel, no_progress

logger = logging.getLogger("openclip.ffmpeg")


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    format_name: str
    size_bytes: int | None
    has_video: bool
    has_audio: bool
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    rotation: int


def _parse_rate(value: str | None) -> float | None:
    if not value or value in {"0/0", "0"}:
        return None
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            return round(float(num) / float(den), 3) if float(den) else None
        return float(value)
    except ValueError:
        return None


def _rotation(stream: dict) -> int:
    for side_data in stream.get("side_data_list") or []:
        if "rotation" in side_data:
            try:
                return int(float(side_data["rotation"])) % 360
            except (TypeError, ValueError):
                return 0
    rotate = (stream.get("tags") or {}).get("rotate")
    try:
        return int(rotate) % 360 if rotate is not None else 0
    except ValueError:
        return 0


def parse_probe_output(data: dict, size_bytes: int | None = None) -> MediaInfo:
    """Turn ``ffprobe -show_format -show_streams`` JSON into :class:`MediaInfo`."""
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")
        ),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = 0.0
    for candidate in (
        fmt.get("duration"),
        (video or {}).get("duration"),
        (audio or {}).get("duration"),
    ):
        try:
            if candidate is not None and float(candidate) > 0:
                duration = float(candidate)
                break
        except (TypeError, ValueError):
            continue

    width = height = None
    rotation = 0
    if video:
        width, height = video.get("width"), video.get("height")
        rotation = _rotation(video)
        if rotation in (90, 270) and width and height:
            width, height = height, width  # report the displayed orientation

    return MediaInfo(
        duration=round(duration, 3),
        format_name=str(fmt.get("format_name", "")),
        size_bytes=size_bytes,
        has_video=video is not None,
        has_audio=audio is not None,
        width=width,
        height=height,
        fps=_parse_rate((video or {}).get("avg_frame_rate") or (video or {}).get("r_frame_rate")),
        video_codec=(video or {}).get("codec_name"),
        audio_codec=(audio or {}).get("codec_name"),
        rotation=rotation,
    )


class FFmpegTools:
    """Runs FFmpeg/FFprobe with progress reporting and cancellation."""

    _nvenc_cache: dict[str, bool] = {}  # noqa: RUF012 - shared per FFmpeg binary

    def __init__(self, ffmpeg: Path, ffprobe: Path) -> None:
        self.ffmpeg = Path(ffmpeg)
        self.ffprobe = Path(ffprobe)

    def nvenc_available(self) -> bool:
        """True if NVIDIA hardware H.264 encoding actually works (tested once per binary)."""
        key = str(self.ffmpeg)
        if key not in self._nvenc_cache:
            try:
                completed = subprocess.run(
                    [
                        str(self.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
                        "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
                        "-c:v", "h264_nvenc", "-f", "null", "-",
                    ],
                    capture_output=True,
                    timeout=30,
                    creationflags=CREATE_NO_WINDOW,
                    check=False,
                )  # fmt: skip
                self._nvenc_cache[key] = completed.returncode == 0
            except (OSError, subprocess.SubprocessError):
                self._nvenc_cache[key] = False
        return self._nvenc_cache[key]

    def pick_encoder(self, preference: str = "auto") -> str:
        if preference == "libx264":
            return "libx264"
        if preference == "h264_nvenc" or (preference == "auto" and self.nvenc_available()):
            return "h264_nvenc" if self.nvenc_available() else "libx264"
        return "libx264"

    @classmethod
    def locate(
        cls,
        *,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
        search_dirs: Iterable[Path] = (),
    ) -> FFmpegTools:
        dirs = list(search_dirs)
        ffmpeg = find_executable("ffmpeg", explicit=ffmpeg_path, search_dirs=dirs)
        ffprobe = find_executable("ffprobe", explicit=ffprobe_path, search_dirs=dirs)
        if ffmpeg is None or ffprobe is None:
            raise FFmpegNotFoundError(
                "FFmpeg is not installed or could not be found. Install it and try again."
            )
        return cls(ffmpeg[0], ffprobe[0])

    # ------------------------------------------------------------------ probe
    def probe(self, path: Path, timeout: float = 120.0) -> MediaInfo:
        cmd = [
            str(self.ffprobe),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaValidationError(
                "Reading the video file took too long.", detail=str(exc)
            ) from exc
        if completed.returncode != 0:
            raise MediaValidationError(
                "This file could not be read as a video. It may be damaged or in an unsupported format.",
                detail=completed.stderr[-2000:],
            )
        try:
            data = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise MediaValidationError("This file could not be read as a video.") from exc
        size = path.stat().st_size if path.exists() else None
        return parse_probe_output(data, size)

    # -------------------------------------------------------------- run ffmpeg
    def run(
        self,
        args: Sequence[str],
        *,
        duration: float | None = None,
        progress: ProgressCallback = no_progress,
        should_cancel: CancelCheck = never_cancel,
        stage: str | None = None,
        cwd: Path | None = None,
    ) -> None:
        """Run ``ffmpeg <args>`` reporting progress from ``-progress pipe:1``."""
        cmd = [
            str(self.ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-progress",
            "pipe:1",
            "-nostats",
            *args,
        ]
        logger.debug("Running FFmpeg", extra={"args": " ".join(args[-6:])})
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            cwd=str(cwd) if cwd else None,
        )
        stderr_tail: deque[str] = deque(maxlen=40)
        stdout, stderr = process.stdout, process.stderr
        if stdout is None or stderr is None:  # cannot happen with PIPE; keeps type checkers happy
            process.kill()
            raise FFmpegError("Could not start FFmpeg.")

        def drain_stderr() -> None:
            for line in stderr:
                stderr_tail.append(line.rstrip())

        drainer = threading.Thread(target=drain_stderr, daemon=True)
        drainer.start()
        cancelled = False
        try:
            for line in stdout:
                if should_cancel():
                    cancelled = True
                    process.terminate()
                    break
                key, _, value = line.strip().partition("=")
                if key in {"out_time_us", "out_time_ms"} and duration and value.isdigit():
                    seconds = int(value) / 1_000_000
                    progress(max(0.0, min(seconds / duration, 1.0)), stage)
                elif key == "progress" and value == "end":
                    progress(1.0, stage)
            process.wait()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            drainer.join(timeout=5)
        if cancelled:
            raise JobCancelled()
        if process.returncode != 0:
            raise FFmpegError(
                "FFmpeg could not process this video.",
                detail="\n".join(stderr_tail),
            )

    # ----------------------------------------------------------- operations
    def extract_audio(
        self,
        source: Path,
        destination: Path,
        *,
        duration: float | None,
        progress: ProgressCallback = no_progress,
        should_cancel: CancelCheck = never_cancel,
    ) -> Path:
        """Extract the first audio track as 16 kHz mono PCM WAV (what Whisper expects)."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            [
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                str(destination),
            ],
            duration=duration,
            progress=progress,
            should_cancel=should_cancel,
            stage="Extracting audio",
        )
        return destination

    def thumbnail(
        self, source: Path, destination: Path, *, at_seconds: float, width: int = 640
    ) -> Path:
        """Save one JPEG frame scaled to ``width`` pixels wide."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            [
                "-ss",
                f"{max(at_seconds, 0):.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:-2",
                "-q:v",
                "3",
                str(destination),
            ]
        )
        if not destination.exists():
            raise FFmpegError("Could not create a thumbnail for this video.")
        return destination

    def capture(
        self, args: Sequence[str], timeout: float = 300.0, limit: int = 64_000_000
    ) -> bytes:
        """Run ``ffmpeg <args>`` (which must write to ``pipe:1``) and return its output bytes."""
        cmd = [str(self.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", *args]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FFmpegError("Analysing the video took too long.", detail=str(exc)) from exc
        if completed.returncode != 0:
            raise FFmpegError(
                "FFmpeg could not analyse this video.",
                detail=completed.stderr.decode("utf-8", "replace")[-2000:],
            )
        return completed.stdout[:limit]


def file_size(path: Path) -> int:
    return os.path.getsize(path)
