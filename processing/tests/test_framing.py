from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from openclip_processing.binaries import find_executable
from openclip_processing.ffmpeg import FFmpegTools
from openclip_processing.framing import best_window_position, crop_axis, subject_position

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "ffmpeg" / "bin"
requires_ffmpeg = pytest.mark.skipif(
    find_executable("ffmpeg", search_dirs=[TOOLS]) is None, reason="FFmpeg not installed"
)


def test_crop_axis() -> None:
    assert crop_axis(1920, 1080, 9, 16) == "x"  # landscape to vertical: trim the sides
    assert crop_axis(1080, 1920, 16, 9) == "y"  # vertical to landscape: trim top/bottom
    assert crop_axis(1920, 1080, 16, 9) is None  # same ratio: nothing to crop


def test_best_window_prefers_the_busy_region_and_falls_back_to_centre() -> None:
    profile = np.zeros(100)
    profile[80:95] = 10.0
    assert best_window_position(profile, 20) > 0.8
    assert best_window_position(np.ones(100), 20) == 0.5  # nothing stands out
    assert best_window_position(np.ones(10), 20) == 0.5  # window wider than the frame


def _moving_box_video(ff: FFmpegTools, path: Path, size: str, box: str) -> Path:
    """A static grey frame with a bright moving square at ``box`` (an FFmpeg x:y expression)."""
    subprocess.run(
        [
            str(ff.ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=0x303030:s={size}:r=25",
            "-f", "lavfi", "-i", "color=c=white:s=120x120:r=25",
            "-filter_complex", f"[0:v][1:v]overlay={box}:shortest=1",
            "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


@requires_ffmpeg
def test_subject_on_the_right_moves_a_vertical_crop_right(tmp_path: Path) -> None:
    ff = FFmpegTools.locate(search_dirs=[TOOLS])
    video = _moving_box_video(
        ff, tmp_path / "right.mp4", "1280x720", "x='1000+60*sin(t*3)':y='300+80*cos(t*2)'"
    )
    position = subject_position(
        ff, video, start=0, end=4, source_width=1280, source_height=720, ratio_w=9, ratio_h=16
    )
    assert position > 0.75


@requires_ffmpeg
def test_subject_at_the_top_moves_a_landscape_crop_up(tmp_path: Path) -> None:
    ff = FFmpegTools.locate(search_dirs=[TOOLS])
    video = _moving_box_video(
        ff, tmp_path / "top.mp4", "720x1280", "x='300+80*sin(t*3)':y='120+40*cos(t*2)'"
    )
    position = subject_position(
        ff, video, start=0, end=4, source_width=720, source_height=1280, ratio_w=16, ratio_h=9
    )
    assert position < 0.25


@requires_ffmpeg
def test_static_uniform_video_stays_centred(tmp_path: Path) -> None:
    ff = FFmpegTools.locate(search_dirs=[TOOLS])
    video = tmp_path / "flat.mp4"
    subprocess.run(
        [
            str(ff.ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0x303030:s=1280x720:r=25", "-t", "3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
    )  # fmt: skip
    assert (
        subject_position(
            ff, video, start=0, end=3, source_width=1280, source_height=720, ratio_w=9, ratio_h=16
        )
        == 0.5
    )
