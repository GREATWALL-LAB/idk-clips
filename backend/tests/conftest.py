"""Shared fixtures: every test gets an isolated app, database and data folder."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import PROJECT_ROOT, Settings
from app.main import create_app
from openclip_processing.binaries import find_executable

REAL_TOOLS = PROJECT_ROOT / "tools"
CSRF_HEADERS = {"X-Requested-With": "OpenClip"}
PASSWORD = "correct-horse-battery"


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        # Accounts + processing on the server: what most of the API tests exercise.
        # Local and hybrid mode have their own test modules.
        "mode": "server",
        # Never serve a locally built web interface from the tests.
        "web_dist_dir": tmp_path / "no-web-build",
        "data_dir": tmp_path / "data",
        # The real tools folder is used read-only so FFmpeg-based tests can run.
        "tools_dir": REAL_TOOLS,
        "rate_limit_enabled": False,
        # Port 9 (discard) is never an Ollama server; status checks report "unavailable".
        "ollama_base_url": "http://127.0.0.1:9",
        "whisper_device": "cpu",
        "job_backend": "local",
        # Most tests are not about email verification (tests/test_verification.py is).
        "email_verification": "off",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def app(settings: Settings):  # type: ignore[no-untyped-def]
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app, headers=CSRF_HEADERS) as test_client:
        yield test_client


def register(
    client: TestClient,
    email: str = "alice@example.com",
    password: str = PASSWORD,
    name: str = "Alice",
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": name, "age_confirmed": True},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


@pytest.fixture
def user_client(client: TestClient) -> TestClient:
    """Logged in as Alice (every account is an ordinary user)."""
    register(client)
    return client


@pytest.fixture
def second_client(app, user_client: TestClient) -> TestClient:  # type: ignore[no-untyped-def]
    """Signed in as Bob, a regular user. Shares the running app but has its own cookies."""
    other = TestClient(app, headers=CSRF_HEADERS)
    register(other, "bob@example.com", PASSWORD, "Bob")
    return other


# ----------------------------------------------------------------- media
def ffmpeg_exe() -> Path | None:
    found = find_executable("ffmpeg", search_dirs=[REAL_TOOLS / "ffmpeg" / "bin"])
    return found[0] if found else None


requires_ffmpeg = pytest.mark.skipif(ffmpeg_exe() is None, reason="FFmpeg is not installed")


def _ffmpeg(out: Path, *args: str) -> Path:
    exe = ffmpeg_exe()
    if exe is None:
        pytest.skip("FFmpeg is not installed")
    subprocess.run(
        [str(exe), "-hide_banner", "-loglevel", "error", "-y", *args, str(out)],
        check=True,
        timeout=180,
    )
    return out


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="session")
def sample_video(media_dir: Path) -> Path:
    """12-second 640x360 test pattern with a 440 Hz tone (no speech)."""
    return _ffmpeg(
        media_dir / "sample.mp4",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
    )  # fmt: skip


@pytest.fixture(scope="session")
def silent_video(media_dir: Path) -> Path:
    """Video without an audio track."""
    return _ffmpeg(
        media_dir / "silent.mp4",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25",
        "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
    )  # fmt: skip
