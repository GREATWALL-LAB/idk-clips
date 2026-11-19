"""Plain data types shared by the processing modules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

#: Called with a fraction between 0 and 1 and an optional human-readable stage.
ProgressCallback = Callable[[float, str | None], None]
#: Returns True when the current job should stop as soon as possible.
CancelCheck = Callable[[], bool]


def no_progress(_: float, __: str | None = None) -> None:
    """Default progress callback that ignores updates."""


def never_cancel() -> bool:
    return False


@dataclass
class Word:
    start: float
    end: float
    text: str
    probability: float | None = None


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    language_probability: float | None
    duration: float
    model: str
    device: str
    segments: list[Segment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(segment.text for segment in self.segments).strip()

    @property
    def word_count(self) -> int:
        return sum(len(segment.text.split()) for segment in self.segments)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transcript:
        segments = [
            Segment(
                id=int(s["id"]),
                start=float(s["start"]),
                end=float(s["end"]),
                text=str(s["text"]),
                words=[Word(**w) for w in s.get("words", [])],
            )
            for s in data.get("segments", [])
        ]
        return cls(
            language=str(data.get("language", "")),
            language_probability=data.get("language_probability"),
            duration=float(data.get("duration", 0.0)),
            model=str(data.get("model", "")),
            device=str(data.get("device", "")),
            segments=segments,
            warnings=list(data.get("warnings", [])),
        )
