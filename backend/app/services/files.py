"""Helpers for user-supplied file names (display only; never used as paths)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath, PureWindowsPath

from app.core.config import ALLOWED_VIDEO_EXTENSIONS

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_DOWNLOAD_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def display_filename(raw: str) -> str:
    """Strip directories and control characters from a client-supplied name."""
    name = PureWindowsPath(PurePosixPath(raw or "").name).name
    name = _CONTROL_RE.sub("", unicodedata.normalize("NFC", name)).strip()
    return name[:255] or "video"


def video_extension(filename: str) -> str | None:
    """Return the lowercase extension if it is an allowed video type."""
    suffix = PurePosixPath(display_filename(filename).lower()).suffix
    return suffix if suffix in ALLOWED_VIDEO_EXTENSIONS else None


def safe_download_name(title: str, extension: str) -> str:
    """ASCII-only name for Content-Disposition headers."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    cleaned = _UNSAFE_DOWNLOAD_RE.sub("", ascii_title).strip().replace(" ", "-")[:80]
    return f"{cleaned or 'clip'}{extension}"
