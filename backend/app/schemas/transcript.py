from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WordOut(BaseModel):
    start: float
    end: float
    text: str
    probability: float | None = None


class SegmentOut(BaseModel):
    id: int
    start: float
    end: float
    text: str
    words: list[WordOut]


class TranscriptOut(BaseModel):
    project_id: str
    language: str
    language_probability: float | None
    model: str
    device: str
    duration: float
    word_count: int
    warnings: list[str]
    segments: list[SegmentOut]
    created_at: datetime
