"""Plain-text, SRT and WebVTT export of transcript segments."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _timestamp(seconds: float, separator: str) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{ms:03d}"


def srt_timestamp(seconds: float) -> str:
    return _timestamp(seconds, ",")


def vtt_timestamp(seconds: float) -> str:
    return _timestamp(seconds, ".")


def _clean(text: str) -> str:
    # Subtitle cues end at a blank line, so collapse whitespace and strip "-->" markers.
    return " ".join(text.replace("-->", "->").split())


def to_srt(segments: Iterable[dict[str, Any]]) -> str:
    blocks = []
    for index, seg in enumerate(segments, start=1):
        blocks.append(
            f"{index}\n{srt_timestamp(seg['start'])} --> {srt_timestamp(seg['end'])}\n{_clean(seg['text'])}\n"
        )
    return "\n".join(blocks)


def to_vtt(segments: Iterable[dict[str, Any]]) -> str:
    cues = [
        f"{vtt_timestamp(seg['start'])} --> {vtt_timestamp(seg['end'])}\n{_clean(seg['text'])}\n"
        for seg in segments
    ]
    return "WEBVTT\n\n" + "\n".join(cues)


def to_text(segments: Iterable[dict[str, Any]], *, with_timestamps: bool = True) -> str:
    lines = []
    for seg in segments:
        text = _clean(seg["text"])
        if with_timestamps:
            minutes, seconds = divmod(int(seg["start"]), 60)
            hours, minutes = divmod(minutes, 60)
            stamp = (
                f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:d}:{seconds:02d}"
            )
            lines.append(f"[{stamp}] {text}")
        else:
            lines.append(text)
    return "\n".join(lines) + "\n"
