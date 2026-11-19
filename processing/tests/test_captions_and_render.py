from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from openclip_processing.binaries import find_executable
from openclip_processing.captions import (
    CaptionCue,
    ass_color,
    ass_override_color,
    ass_time,
    build_ass,
    clean_caption_text,
    copy_fonts,
    font_cell_ratio,
)
from openclip_processing.ffmpeg import FFmpegTools
from openclip_processing.render import ASPECT_RATIOS, RenderSpec, build_video_filter, render_clip

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "ffmpeg" / "bin"
requires_ffmpeg = pytest.mark.skipif(
    find_executable("ffmpeg", search_dirs=[TOOLS]) is None, reason="FFmpeg not installed"
)
STYLE = {
    "font": "Montserrat",
    "font_size": 72,
    "text_color": "#FFFFFF",
    "highlight_color": "#FACC15",
    "outline_color": "#000000",
    "outline_width": 6,
    "background": False,
    "background_color": "#000000",
    "position": "bottom",
    "uppercase": True,
    "highlight_words": True,
    "words_per_line": 3,
}


def test_color_and_time_conversion() -> None:
    assert ass_color("#FACC15") == "&H0015CCFA"
    assert ass_override_color("#FACC15") == "&H15CCFA&"
    assert ass_time(83.456) == "0:01:23.46"
    with pytest.raises(ValueError):
        ass_color("red")


def test_caption_text_cannot_inject_ass_overrides() -> None:
    cleaned = clean_caption_text(r"hi {\pos(1,1)\c&HFF&} there\N", uppercase=True)
    assert "{" not in cleaned and "}" not in cleaned and "\\" not in cleaned
    assert cleaned == "HI POS(1,1)C&HFF& THEREN"


def test_build_ass_highlights_each_spoken_word() -> None:
    words = [
        {"start": 0.0, "end": 0.4, "text": "Three"},
        {"start": 0.45, "end": 0.9, "text": "simple"},
        {"start": 0.95, "end": 1.4, "text": "habits"},
    ]
    ass = build_ass(
        [CaptionCue(0.0, 1.5, "Three simple habits", words)], STYLE, width=1080, height=1920
    )
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    dialogue = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogue) == 3
    assert r"{\c&H15CCFA&}THREE{\r} SIMPLE HABITS" in dialogue[0]
    assert r"THREE {\c&H15CCFA&}SIMPLE{\r} HABITS" in dialogue[1]


def test_edited_lines_without_word_timing_are_static() -> None:
    style = {**STYLE, "uppercase": False}
    ass = build_ass([CaptionCue(1.0, 2.0, "Edited text")], style, width=1080, height=1920)
    assert "Dialogue: 0,0:00:01.00,0:00:02.00,Caption,,0,0,0,,Edited text" in ass


def test_font_size_matches_css_em_and_scales_with_the_short_side() -> None:
    ratio = font_cell_ratio("Montserrat")
    assert 1.3 < ratio < 2.0
    for width, height in ASPECT_RATIOS.values():
        ass = build_ass([], STYLE, width=width, height=height)
        style_line = next(line for line in ass.splitlines() if line.startswith("Style:"))
        assert style_line.split(",")[2] == str(round(72 * min(width, height) / 1080 * ratio))


def test_unsupported_font_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_ass([], {**STYLE, "font": "../../evil"}, width=1080, height=1920)


def test_filters_for_each_layout_and_ratio() -> None:
    base = {"source": Path("in.mp4"), "output": Path("out.mp4"), "start": 0, "end": 10}
    crop = build_video_filter(RenderSpec(**base, layout="crop", crop_position=0.25))
    assert "crop=w='trunc(min(iw,ih*1080/1920)/2)*2'" in crop
    assert "x='(iw-ow)*0.250'" in crop and "y='(ih-oh)*0.250'" in crop
    assert "scale=1080:1920" in crop and "setsar=1" in crop
    square = build_video_filter(RenderSpec(**base, layout="crop", aspect_ratio="1:1"))
    assert "ih*1080/1080" in square and "scale=1080:1080" in square
    landscape_fit = build_video_filter(RenderSpec(**base, layout="fit", aspect_ratio="16:9"))
    assert "boxblur" in landscape_fit and "overlay" in landscape_fit
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in landscape_fit
    original = build_video_filter(
        RenderSpec(**base, layout="original", source_width=1281, source_height=721)
    )
    assert "scale=1280:720" in original
    subs = build_video_filter(RenderSpec(**base, subtitles="captions.ass", fonts_dir="fonts"))
    assert subs.endswith("subtitles=filename=captions.ass:fontsdir=fonts,format=yuv420p[v]")
    with pytest.raises(ValueError):
        build_video_filter(RenderSpec(**base, layout="diagonal"))
    with pytest.raises(ValueError):
        build_video_filter(RenderSpec(**base, aspect_ratio="3:2"))


def _make_source(ff: FFmpegTools, path: Path, size: str = "1280x720") -> Path:
    subprocess.run(
        [
            str(ff.ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
            "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


def _stream_info(ff: FFmpegTools, path: Path) -> dict:
    probe = subprocess.run(
        [
            str(ff.ffprobe), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,sample_aspect_ratio",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return json.loads(probe.stdout)["streams"][0]


@requires_ffmpeg
def test_real_render_for_every_aspect_ratio_with_captions(tmp_path: Path) -> None:
    ff = FFmpegTools.locate(search_dirs=[TOOLS])
    source = _make_source(ff, tmp_path / "landscape.mp4")
    workdir = tmp_path / "work"
    copy_fonts(workdir / "fonts")
    words = [
        {"start": 0.2, "end": 0.6, "text": "Hello"},
        {"start": 0.7, "end": 1.2, "text": "world"},
    ]
    progress: list[float] = []
    for ratio, (width, height) in ASPECT_RATIOS.items():
        for layout in ("crop", "fit"):
            (workdir / "captions.ass").write_text(
                build_ass(
                    [CaptionCue(0.2, 1.5, "Hello world", words)], STYLE, width=width, height=height
                ),
                encoding="utf-8",
            )
            output = tmp_path / f"{ratio.replace(':', 'x')}-{layout}.mp4"
            spec = RenderSpec(
                source=source, output=output, start=1.0, end=3.5, layout=layout, aspect_ratio=ratio,
                subtitles="captions.ass", fonts_dir="fonts", workdir=workdir,
                encoder=ff.pick_encoder("auto"),
            )  # fmt: skip
            render_clip(ff, spec, progress=lambda f, _s=None: progress.append(f))
            info = ff.probe(output)
            stream = _stream_info(ff, output)
            assert (info.width, info.height) == (width, height), (ratio, layout)
            assert (
                stream["sample_aspect_ratio"] in ("1:1", "0:1", None)
                or "sample_aspect_ratio" not in stream
            )
            assert stream["codec_name"] == "h264"
            assert info.has_audio
            assert 2.3 <= info.duration <= 2.8
    assert progress and progress[-1] == 1.0


@requires_ffmpeg
def test_captions_are_drawn_inside_the_frame_for_every_ratio(tmp_path: Path) -> None:
    """Render white captions on a black video and check where the text pixels land."""
    ff = FFmpegTools.locate(search_dirs=[TOOLS])
    source = tmp_path / "black.mp4"
    subprocess.run(
        [
            str(ff.ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source),
        ],
        check=True,
    )  # fmt: skip
    workdir = tmp_path / "work"
    copy_fonts(workdir / "fonts")
    style = {**STYLE, "highlight_words": False, "outline_width": 0}
    for ratio, (width, height) in ASPECT_RATIOS.items():
        (workdir / "captions.ass").write_text(
            build_ass([CaptionCue(0.0, 3.0, "Caption check")], style, width=width, height=height),
            encoding="utf-8",
        )
        output = tmp_path / f"cap-{ratio.replace(':', 'x')}.mp4"
        render_clip(
            ff,
            RenderSpec(
                source=source, output=output, start=0.0, end=2.0, aspect_ratio=ratio,
                subtitles="captions.ass", fonts_dir="fonts", workdir=workdir,
            ),
        )  # fmt: skip
        raw = ff.capture(
            [
                "-ss",
                "1",
                "-i",
                str(output),
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "gray",
                "pipe:1",
            ]
        )
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width)
        rows = np.where(frame.max(axis=1) > 200)[0]
        cols = np.where(frame.max(axis=0) > 200)[0]
        assert rows.size and cols.size, ratio
        # Text sits in the lower half, above the bottom margin, horizontally centred and inside the frame.
        assert height * 0.5 < rows.min() and rows.max() < height * 0.86, (
            ratio,
            rows.min(),
            rows.max(),
        )
        assert cols.min() > 0 and cols.max() < width - 1
        assert abs((cols.min() + cols.max()) / 2 - width / 2) < width * 0.05
        # Text height is consistent with the configured size (72 px on the short side 1080).
        assert 0.025 < (rows.max() - rows.min()) / min(width, height) < 0.09
