"""Automatic framing: keep the main subject visible when cropping to another aspect ratio.

The analysis is deliberately lightweight (no extra AI models): a few small grayscale
frames are sampled from the clip with FFmpeg, and every column (or row) is scored by

- visual detail (edge strength), which is high around people, faces and text, and
- motion between frames, which is high where someone is speaking or moving.

The crop window with the highest combined score wins. If no part of the frame clearly
stands out (for example a static, evenly busy picture), the window stays centred.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from openclip_processing.ffmpeg import FFmpegTools

logger = logging.getLogger("openclip.framing")

ANALYSIS_WIDTH = 192
SAMPLES = 12
MIN_ADVANTAGE = 1.08  # the best window must beat the centred one by at least 8 %


def crop_axis(source_width: int, source_height: int, ratio_w: int, ratio_h: int) -> str | None:
    """Which axis a 'crop' layout trims: "x" (sides), "y" (top/bottom) or None."""
    source = source_width / source_height
    target = ratio_w / ratio_h
    if abs(source - target) / target < 0.01:
        return None
    return "x" if source > target else "y"


def best_window_position(profile: np.ndarray, window: int) -> float:
    """Return the start of the best window as a fraction of the free space (0..1)."""
    length = int(profile.shape[0])
    if window >= length or length == 0:
        return 0.5
    # Only what stands out from the typical column/row counts (ignores uniform texture and noise).
    profile = np.maximum(profile - np.median(profile), 0.0)
    sums = np.convolve(profile, np.ones(window), mode="valid")
    best = int(np.argmax(sums))
    centre = (length - window) // 2
    if sums[best] <= 1e-6 or sums[best] < sums[centre] * MIN_ADVANTAGE:
        return 0.5  # nothing clearly stands out: keep it centred
    return round(best / (length - window), 3)


def subject_position(
    ffmpeg: FFmpegTools,
    source: Path,
    *,
    start: float,
    end: float,
    source_width: int,
    source_height: int,
    ratio_w: int,
    ratio_h: int,
) -> float:
    """Best crop position (0..1) for showing the subject of ``source`` between start and end."""
    axis = crop_axis(source_width, source_height, ratio_w, ratio_h)
    if axis is None:
        return 0.5
    width = ANALYSIS_WIDTH
    height = max(2, round(width * source_height / source_width / 2) * 2)
    duration = max(end - start, 0.5)
    raw = ffmpeg.capture(
        [
            "-ss", f"{max(start, 0):.3f}",
            "-t", f"{duration:.3f}",
            "-i", str(source),
            "-vf", f"fps={SAMPLES / duration:.5f},scale={width}:{height},format=gray",
            "-f", "rawvideo",
            "-pix_fmt", "gray",
            "pipe:1",
        ]
    )  # fmt: skip
    frame_size = width * height
    count = len(raw) // frame_size
    if count == 0:
        return 0.5
    frames = np.frombuffer(raw[: count * frame_size], dtype=np.uint8).reshape(count, height, width)
    frames = frames.astype(np.float32)

    # Edge strength (detail) averaged over the sampled frames.
    edges = np.zeros((height, width), dtype=np.float32)
    edges[:, 1:] += np.abs(np.diff(frames, axis=2)).mean(axis=0)
    edges[1:, :] += np.abs(np.diff(frames, axis=1)).mean(axis=0)
    energy = edges
    if count > 1:
        # Motion counts double: the speaker is usually what moves.
        energy = energy + 2.0 * np.abs(np.diff(frames, axis=0)).mean(axis=0)

    if axis == "x":
        profile = energy.sum(axis=0)
        window = round(height * ratio_w / ratio_h)
    else:
        profile = energy.sum(axis=1)
        window = round(width * ratio_h / ratio_w)
    position = best_window_position(profile, window)
    logger.debug("Auto framing", extra={"axis": axis, "position": position})
    return position
