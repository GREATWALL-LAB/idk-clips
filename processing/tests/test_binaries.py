from __future__ import annotations

import os
from pathlib import Path

from openclip_processing.binaries import find_executable

EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def test_explicit_path_must_exist(tmp_path: Path) -> None:
    assert find_executable("ffmpeg", explicit=tmp_path / "nope" / EXE) is None


def test_explicit_directory_is_accepted(tmp_path: Path) -> None:
    (tmp_path / EXE).write_bytes(b"")
    assert find_executable("ffmpeg", explicit=tmp_path) == (tmp_path / EXE, "configured")


def test_bundled_tools_folder_is_searched_before_path(tmp_path: Path) -> None:
    bundled = tmp_path / "tools" / "ffmpeg" / "bin"
    bundled.mkdir(parents=True)
    (bundled / EXE).write_bytes(b"")
    assert find_executable("ffmpeg", search_dirs=[bundled]) == (bundled / EXE, "bundled")


def test_missing_binary_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_executable("definitely-not-a-real-tool-xyz") is None
