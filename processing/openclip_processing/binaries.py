"""Locate external executables (FFmpeg, FFprobe) without assuming they are installed."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Prevents a console window from flashing up for every subprocess on Windows.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_VERSION_RE = re.compile(r"^(?:ffmpeg|ffprobe) version (?P<version>\S+)")


@dataclass(frozen=True)
class BinaryInfo:
    name: str
    path: Path
    version: str | None
    source: str  # "configured", "bundled" or "system"


def _executable_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def find_executable(
    name: str,
    *,
    explicit: str | os.PathLike[str] | None = None,
    search_dirs: Iterable[Path] = (),
) -> tuple[Path, str] | None:
    """Find ``name`` and say where it came from.

    Order: an explicitly configured path, then project-local tool folders
    (for example ``tools/ffmpeg/bin``), then the system ``PATH``.
    An explicit path that does not exist returns ``None`` instead of silently
    falling back, so misconfiguration is visible.
    """
    exe = _executable_name(name)
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_dir():
            candidate = candidate / exe
        return (candidate, "configured") if candidate.is_file() else None
    for directory in search_dirs:
        candidate = Path(directory) / exe
        if candidate.is_file():
            return candidate, "bundled"
    found = shutil.which(name)
    return (Path(found), "system") if found else None


def read_version(path: Path, timeout: float = 10.0) -> str | None:
    """Return the version string printed by ``<tool> -version``, or ``None``."""
    try:
        completed = subprocess.run(
            [str(path), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    match = _VERSION_RE.match(first_line)
    return match.group("version") if match else None


def inspect_binary(
    name: str,
    *,
    explicit: str | os.PathLike[str] | None = None,
    search_dirs: Iterable[Path] = (),
) -> BinaryInfo | None:
    located = find_executable(name, explicit=explicit, search_dirs=search_dirs)
    if located is None:
        return None
    path, source = located
    return BinaryInfo(name=name, path=path, version=read_version(path), source=source)
