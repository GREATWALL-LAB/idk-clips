from __future__ import annotations

from pathlib import Path

import pytest

from app.services.files import display_filename, safe_download_name, video_extension
from app.services.storage import LocalStorage, StorageError


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../outside.txt",
        "users/../../outside.txt",
        "users/./x",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "users\\..\\x",
        "users//x",
        "%2e%2e/x",
    ],
)
def test_storage_rejects_path_traversal(tmp_path: Path, key: str) -> None:
    storage = LocalStorage(tmp_path / "storage")
    with pytest.raises(StorageError):
        storage.path(key)


def test_storage_resolves_keys_inside_root(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    key = f"{LocalStorage.project_prefix('u1', 'p1')}/source.mp4"
    path = storage.ensure_parent(key)
    path.write_bytes(b"data")
    assert path.is_relative_to(storage.root)
    assert storage.exists(key)
    assert storage.usage_bytes("users/u1") == 4
    storage.delete_tree("users/u1/projects/p1")
    assert not storage.exists(key)


def test_display_filename_strips_paths_and_control_characters() -> None:
    assert display_filename("C:\\Users\\me\\Videos\\talk.mp4") == "talk.mp4"
    assert display_filename("../../etc/passwd") == "passwd"
    assert display_filename("bad\x00name\n.mp4") == "badname.mp4"
    assert display_filename("") == "video"


def test_video_extension_allow_list() -> None:
    assert video_extension("Talk.MP4") == ".mp4"
    assert video_extension("a.webm") == ".webm"
    assert video_extension("a.mp4.exe") is None
    assert video_extension("noext") is None


def test_safe_download_name_is_ascii_only() -> None:
    assert safe_download_name('He said "hi"/\\<script>', ".mp4") == "He-said-hiscript.mp4"
    assert safe_download_name("Ünïcödé title", ".srt") == "Unicode-title.srt"
    assert safe_download_name("???", ".mp4") == "clip.mp4"
