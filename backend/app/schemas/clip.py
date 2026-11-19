from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.job import JobOut

#: crop = fill the frame (subject kept in view); fit = whole picture over a blurred background.
ClipLayout = Literal["crop", "fit"]
CaptionPosition = Literal["bottom", "middle", "top"]
#: Output shapes (pixel sizes are in processing/openclip_processing/render.py).
AspectRatio = Literal["9:16", "4:5", "1:1", "16:9"]

_HEX = r"^#[0-9a-fA-F]{6}$"


class CaptionStyle(BaseModel):
    """Caption appearance. Every field is validated before it reaches FFmpeg/libass."""

    font: Literal["Montserrat", "Anton", "Poppins"] = "Montserrat"
    font_size: int = Field(
        default=72, ge=24, le=160, description="Pixels on a 1920-pixel-tall frame."
    )
    text_color: str = Field(default="#FFFFFF", pattern=_HEX)
    highlight_color: str = Field(default="#FACC15", pattern=_HEX)
    outline_color: str = Field(default="#000000", pattern=_HEX)
    outline_width: int = Field(default=6, ge=0, le=20)
    background: bool = False
    background_color: str = Field(default="#000000", pattern=_HEX)
    position: CaptionPosition = "bottom"
    uppercase: bool = False
    highlight_words: bool = True
    words_per_line: int = Field(default=4, ge=1, le=10)


class CaptionLine(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=300)

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return " ".join(value.split())


class ClipOut(BaseModel):
    id: str
    project_id: str
    project_name: str | None = None
    rank: int
    title: str
    description: str
    reason: str
    score: int | None
    source: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    suggested_start: float | None
    suggested_end: float | None
    status: str
    layout: str
    crop_position: float
    auto_frame: bool
    #: The ratio this clip is exported in (its own choice, or the project default).
    aspect_ratio: str
    #: True when the clip has its own ratio instead of following the project.
    aspect_ratio_overridden: bool = False
    worker_id: str | None = None
    media_host: Literal["server", "worker"] = "server"
    captions_enabled: bool
    caption_style: CaptionStyle
    has_caption_edits: bool
    output_size_bytes: int | None
    rendered_at: datetime | None
    error_message: str | None
    preview_url: str | None
    download_url: str | None
    thumbnail_url: str | None
    active_job: JobOut | None = None
    created_at: datetime
    updated_at: datetime


class ClipCreate(BaseModel):
    title: str = Field(default="Custom clip", min_length=1, max_length=200)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)


class ClipUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    layout: ClipLayout | None = None
    crop_position: float | None = Field(
        default=None, ge=0, le=1, description="Setting it switches automatic framing off."
    )
    auto_frame: bool | None = None
    aspect_ratio: AspectRatio | None = Field(
        default=None, description="Export shape for this clip only."
    )
    captions_enabled: bool | None = None
    caption_style: CaptionStyle | None = None
    caption_lines: list[CaptionLine] | None = Field(
        default=None, max_length=500, description="Edited caption text; send [] to reset."
    )


class ClipCaptions(BaseModel):
    """The caption lines that will be burned into the clip (edited or generated)."""

    clip_id: str
    edited: bool
    lines: list[CaptionLine]


class ClipList(BaseModel):
    items: list[ClipOut]
    total: int
