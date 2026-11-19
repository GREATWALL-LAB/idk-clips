"""The real worker agent and its bridge, run in-process against a hybrid-mode server.

The agent's HTTP client is wired straight into the server app, and the bridge is
driven with a loopback test client, so these tests cover the true code paths:
pairing, direct upload to the worker, job claiming, FFmpeg rendering in every
aspect ratio, reading results back through the bridge, and clean-up.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent import state
from app.agent.bridge import create_bridge
from app.agent.client import ConnectionProblem, ServerClient, ServerError
from app.agent.runner import Agent, RemoteJobIO
from app.core.config import Settings
from app.db.models import Project, Transcript
from openclip_processing.errors import JobCancelled, ProcessingError
from openclip_processing.ffmpeg import FFmpegTools
from tests.conftest import CSRF_HEADERS, REAL_TOOLS, make_settings, requires_ffmpeg
from tests.hybrid import PROJECTS, SEGMENTS, WORKERS, new_code

BRIDGE_URL = "http://127.0.0.1:8787"
WEB_ORIGIN = "http://localhost:3000"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path, mode="hybrid")


class Rig:
    """A paired agent + bridge for one user."""

    def __init__(self, app, user: TestClient, tmp_path: Path, name: str = "rig") -> None:  # type: ignore[no-untyped-def]
        self.user = user
        self.settings = make_settings(tmp_path / f"{name}-data", mode="hybrid")
        for folder in (self.settings.tmp_dir, self.settings.storage_dir):
            folder.mkdir(parents=True, exist_ok=True)
        # In-process HTTP: each client is wired straight into the server app (no sockets).
        pairing = ServerClient("http://testserver", http_client=TestClient(app))
        answer = pairing.pair({"code": new_code(user), "name": name, "bridge_port": 8787})
        self.credentials = state.Credentials(
            server_url="http://testserver",
            worker_id=answer["worker_id"],
            worker_name=answer["worker_name"],
            token=answer["token"],
            owner_id=answer["owner_id"],
            owner_name=answer["owner_name"],
            paired_at="2026-11-13T00:00:00+00:00",
            allowed_origins=",".join(answer["allowed_origins"]),
        )
        self.client = ServerClient(
            "http://testserver", answer["token"], http_client=TestClient(app)
        )
        self.agent = Agent(self.settings, self.credentials, self.client)
        self.bridge_app = create_bridge(
            self.settings,
            self.credentials,
            self.client,
            self.agent.storage,
            allowed_origins=self.credentials.origins(),
        )
        self.bridge = TestClient(self.bridge_app, base_url=BRIDGE_URL, client=("127.0.0.1", 50123))

    @property
    def worker_id(self) -> str:
        return self.credentials.worker_id

    def token(self, scope: str, project_id: str | None = None) -> str:
        body: dict[str, Any] = {"scope": scope}
        if project_id:
            body["project_id"] = project_id
        response = self.user.post(f"{WORKERS}/{self.worker_id}/transfer-tokens", json=body)
        assert response.status_code == 201, response.text
        return response.json()["token"]

    def upload(self, project_id: str, video: Path, filename: str = "talk.mp4"):  # type: ignore[no-untyped-def]
        return self.bridge.put(
            f"/bridge/v1/projects/{project_id}/media",
            params={"filename": filename},
            content=video.read_bytes(),
            headers={"Authorization": f"Bearer {self.token('upload', project_id)}"},
        )


@pytest.fixture
def rig(app, user_client: TestClient, tmp_path: Path) -> Rig:  # type: ignore[no-untyped-def]
    return Rig(app, user_client, tmp_path)


def add_transcript(app, project_id: str) -> None:  # type: ignore[no-untyped-def]
    with app.state.database.session_scope() as db:
        db.add(
            Transcript(
                project_id=project_id, language="en", language_probability=1.0, model="test",
                device="cpu", duration=12.0, word_count=11, segments=SEGMENTS, warnings=[],
            )
        )  # fmt: skip
        db.get(Project, project_id).status = "transcribed"


def probe(path: Path):  # type: ignore[no-untyped-def]
    return FFmpegTools.locate(search_dirs=[REAL_TOOLS / "ffmpeg" / "bin"]).probe(path)


# ------------------------------------------------------------- credentials
def test_credentials_round_trip_and_never_print_the_token(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    assert state.load(settings) is None
    credentials = state.Credentials(
        server_url="https://clips.example.com", worker_id="w1", worker_name="PC",
        token="ocw_secret-value", owner_id="u1", owner_name="Alice", paired_at="now",
        allowed_origins="https://clips.example.com",
    )  # fmt: skip
    path = state.save(settings, credentials)
    assert path.parent == settings.agent_dir
    loaded = state.load(settings)
    assert loaded == credentials and loaded.origins() == ["https://clips.example.com"]
    assert "ocw_secret-value" not in repr(loaded)
    assert state.clear(settings) is True and state.load(settings) is None
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(state.AgentConfigError):
        state.load(settings)


@pytest.mark.parametrize(
    ("url", "allow_http", "ok"),
    [
        ("https://clips.example.com/", False, True),
        ("http://localhost:8000", False, True),
        ("http://127.0.0.1:8000", False, True),
        ("http://clips.example.com", False, False),  # would send the token in clear text
        ("http://192.168.1.20:8000", False, False),
        ("http://192.168.1.20:8000", True, True),
        ("https://user:pw@clips.example.com", False, False),
        ("ftp://clips.example.com", False, False),
        ("clips.example.com", False, False),
    ],
)
def test_server_address_must_be_encrypted_unless_local(
    url: str, allow_http: bool, ok: bool
) -> None:
    if ok:
        assert state.validate_server_url(url, allow_http=allow_http).startswith("http")
    else:
        with pytest.raises(state.AgentConfigError):
            state.validate_server_url(url, allow_http=allow_http)


# ------------------------------------------------------------------- bridge
def test_bridge_only_answers_this_computer(rig: Rig) -> None:
    assert rig.bridge.get("/bridge/v1/hello").json()["worker_id"] == rig.worker_id
    # Another machine on the network:
    remote = TestClient(rig.bridge_app, base_url=BRIDGE_URL, client=("192.168.1.50", 40000))
    assert remote.get("/bridge/v1/hello").status_code == 403
    # A website that made the browser resolve its own name to 127.0.0.1 (DNS rebinding):
    rebound = TestClient(
        rig.bridge_app, base_url="http://evil.example.com", client=("127.0.0.1", 40001)
    )
    assert rebound.get("/bridge/v1/hello").status_code == 403
    assert rebound.get("/bridge/v1/hello").json()["error"]["code"] == "local_only"


def test_bridge_cors_allows_only_the_paired_website(rig: Rig) -> None:
    preflight = {
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "authorization,content-type",
        "Access-Control-Request-Private-Network": "true",
    }
    allowed = rig.bridge.options(
        "/bridge/v1/projects/x/media", headers={"Origin": WEB_ORIGIN, **preflight}
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == WEB_ORIGIN
    assert allowed.headers.get("access-control-allow-private-network") == "true"
    denied = rig.bridge.options(
        "/bridge/v1/projects/x/media", headers={"Origin": "https://evil.example.com", **preflight}
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_bridge_requires_a_valid_transfer_token(
    app, rig: Rig, second_client: TestClient, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    project = rig.user.post(PROJECTS, json={"name": "Talk", "auto_process": False}).json()
    pid = project["id"]
    url = f"/bridge/v1/projects/{pid}/media"
    assert rig.bridge.get(url).status_code == 403
    assert rig.bridge.get(url, params={"token": "oct_made-up"}).status_code == 403
    assert rig.bridge.put(url, params={"filename": "a.mp4"}, content=b"12345").status_code == 403
    # A read token cannot upload, and an upload token is tied to its project.
    read = rig.token("read")
    wrong_scope = rig.bridge.put(
        url,
        params={"filename": "a.mp4"},
        content=b"12345",
        headers={"Authorization": f"Bearer {read}"},
    )
    assert wrong_scope.status_code == 403 and wrong_scope.json()["error"]["code"] == "wrong_scope"
    other = rig.user.post(PROJECTS, json={"name": "Other", "auto_process": False}).json()["id"]
    other_token = rig.token("upload", other)
    wrong_project = rig.bridge.put(
        url,
        params={"filename": "a.mp4"},
        content=b"12345",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert wrong_project.json()["error"]["code"] == "wrong_project"
    # Another user's token (for their own worker) is refused by this worker.
    bob = Rig(app, second_client, tmp_path, name="bob")
    assert rig.bridge.get(url, params={"token": bob.token("read")}).status_code == 403
    # With a valid token but no file yet: a clean 404, never a path.
    missing = rig.bridge.get(url, params={"token": read})
    assert missing.status_code == 404 and "users/" not in missing.text


@requires_ffmpeg
def test_bridge_rejects_bad_uploads(rig: Rig, silent_video: Path, tmp_path: Path) -> None:
    pid = rig.user.post(PROJECTS, json={"name": "Talk", "auto_process": False}).json()["id"]
    headers = {"Authorization": f"Bearer {rig.token('upload', pid)}"}
    url = f"/bridge/v1/projects/{pid}/media"
    exe = rig.bridge.put(
        url, params={"filename": "setup.exe"}, content=b"MZ" * 100, headers=headers
    )
    assert exe.status_code == 415
    empty = rig.bridge.put(url, params={"filename": "a.mp4"}, content=b"", headers=headers)
    assert empty.status_code == 400
    fake = tmp_path / "not-a-video.mp4"
    fake.write_bytes(b"this is not a video at all" * 50)
    garbage = rig.upload(pid, fake)
    assert garbage.status_code == 422 and garbage.json()["error"]["code"] == "invalid_media"
    no_audio = rig.upload(pid, silent_video)
    assert no_audio.status_code == 422 and "no audio" in no_audio.json()["error"]["message"]
    # Rejected files are removed from the worker and never registered.
    folder = rig.agent.storage.root / "users" / rig.credentials.owner_id / "projects" / pid
    assert not folder.exists() or not any(folder.iterdir())
    assert rig.user.get(f"{PROJECTS}/{pid}").json()["has_media"] is False
    # Path tricks in the file name are harmless: the name is never used as a path.
    assert rig.bridge.put(
        url, params={"filename": "../../evil.mp4"}, content=b"x" * 64, headers=headers
    ).status_code in (409, 422)
    assert not (rig.agent.storage.root.parent / "evil.mp4").exists()


# ----------------------------------------------- upload -> render -> download
@requires_ffmpeg
def test_agent_processes_a_real_video_end_to_end(app, rig: Rig, sample_video: Path) -> None:  # type: ignore[no-untyped-def]
    user = rig.user
    pid = user.post(PROJECTS, json={"name": "Talk", "auto_process": False}).json()["id"]

    uploaded = rig.upload(pid, sample_video)
    assert uploaded.status_code == 200, uploaded.text
    project = user.get(f"{PROJECTS}/{pid}").json()
    assert project["has_media"] is True and project["worker_id"] == rig.worker_id
    assert (project["width"], project["height"]) == (640, 360)
    assert 11.5 < project["duration_seconds"] < 12.5
    assert project["original_filename"] == "talk.mp4" and project["status"] == "uploaded"
    # The video is on the worker and nowhere on the server.
    assert list(rig.agent.storage.root.rglob("source.mp4"))
    assert not list(app.state.storage.root.rglob("*.mp4"))
    # One video per project: the server issues no second upload permission.
    second = user.post(
        f"{WORKERS}/{rig.worker_id}/transfer-tokens", json={"scope": "upload", "project_id": pid}
    )
    assert second.status_code == 409 and second.json()["error"]["code"] == "media_exists"

    read = rig.token("read")
    media = rig.bridge.get(f"/bridge/v1/projects/{pid}/media", params={"token": read})
    assert media.status_code == 200 and media.headers["content-type"] == "video/mp4"
    assert len(media.content) == sample_video.stat().st_size
    partial = rig.bridge.get(
        f"/bridge/v1/projects/{pid}/media", params={"token": read}, headers={"Range": "bytes=0-99"}
    )
    assert partial.status_code == 206 and len(partial.content) == 100  # seeking works
    thumb = rig.bridge.get(f"/bridge/v1/projects/{pid}/thumbnail", params={"token": read})
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"

    add_transcript(app, pid)
    clip = user.post(
        f"{PROJECTS}/{pid}/clips", json={"title": "My clip", "start_seconds": 1, "end_seconds": 7}
    ).json()
    job = user.post(f"/api/v1/clips/{clip['id']}/render").json()
    assert rig.agent.step(wait_seconds=0) == "succeeded"
    assert user.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "succeeded"
    ready = user.get(f"/api/v1/clips/{clip['id']}").json()
    assert ready["status"] == "ready" and ready["output_size_bytes"] > 10_000

    clip_url = f"/bridge/v1/projects/{pid}/clips/{clip['id']}"
    download = rig.bridge.get(
        f"{clip_url}/file", params={"token": read, "download": "true", "name": "My clip"}
    )
    assert download.status_code == 200 and download.headers["content-type"] == "video/mp4"
    assert 'filename="My-clip.mp4"' in download.headers["content-disposition"]
    assert len(download.content) == ready["output_size_bytes"]
    assert rig.bridge.get(f"{clip_url}/thumbnail", params={"token": read}).status_code == 200
    # Nothing is left in the worker's temporary folder.
    assert list(rig.settings.tmp_dir.iterdir()) == []
    assert rig.agent.step(wait_seconds=0) is None  # queue is empty

    # Deleting the project removes the files from the worker.
    assert user.delete(f"{PROJECTS}/{pid}").status_code == 204
    assert rig.agent.step(wait_seconds=0) == "succeeded"
    assert not list(rig.agent.storage.root.rglob("*.mp4"))


@requires_ffmpeg
@pytest.mark.parametrize(
    ("ratio", "size"),
    [("9:16", (1080, 1920)), ("4:5", (1080, 1350)), ("1:1", (1080, 1080)), ("16:9", (1920, 1080))],
)
@pytest.mark.parametrize("layout", ["crop", "fit"])
def test_every_aspect_ratio_is_exported_at_its_real_size(  # type: ignore[no-untyped-def]
    app,
    rig: Rig,
    sample_video: Path,
    tmp_path: Path,
    ratio: str,
    size: tuple[int, int],
    layout: str,
) -> None:
    user = rig.user
    pid = user.post(PROJECTS, json={"name": "Ratios", "auto_process": False}).json()["id"]
    assert rig.upload(pid, sample_video).status_code == 200
    add_transcript(app, pid)
    clip = user.post(
        f"{PROJECTS}/{pid}/clips", json={"title": "Ratio", "start_seconds": 2, "end_seconds": 6}
    ).json()
    changed = user.patch(
        f"/api/v1/clips/{clip['id']}", json={"aspect_ratio": ratio, "layout": layout}
    ).json()
    assert changed["aspect_ratio"] == ratio
    assert changed["aspect_ratio_overridden"] is (ratio != "9:16")
    user.post(f"/api/v1/clips/{clip['id']}/render")
    assert rig.agent.step(wait_seconds=0) == "succeeded"
    exported = rig.bridge.get(
        f"/bridge/v1/projects/{pid}/clips/{clip['id']}/file", params={"token": rig.token("read")}
    )
    out = tmp_path / "export.mp4"
    out.write_bytes(exported.content)
    info = probe(out)
    assert (info.width, info.height) == size  # the file itself has the chosen shape
    assert info.has_audio and info.video_codec == "h264"
    assert abs(info.duration - 4.0) < 0.3
    # Square pixels: the picture is cropped or padded, never stretched.
    ffprobe = REAL_TOOLS / "ffmpeg" / "bin" / "ffprobe.exe"
    if ffprobe.is_file():
        sar = subprocess.run(
            [str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=sample_aspect_ratio", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True, check=True, timeout=60,
        ).stdout.strip()  # fmt: skip
        assert sar in ("1:1", "N/A", "")


@requires_ffmpeg
def test_agent_reports_failures_instead_of_hiding_them(app, rig: Rig, sample_video: Path) -> None:  # type: ignore[no-untyped-def]
    user = rig.user
    pid = user.post(PROJECTS, json={"name": "Talk", "auto_process": False}).json()["id"]
    rig.upload(pid, sample_video)
    add_transcript(app, pid)
    clip = user.post(
        f"{PROJECTS}/{pid}/clips", json={"title": "Gone", "start_seconds": 1, "end_seconds": 7}
    ).json()
    job = user.post(f"/api/v1/clips/{clip['id']}/render").json()
    for source in rig.agent.storage.root.rglob("source.mp4"):
        source.unlink()  # the file disappeared from the worker
    assert rig.agent.step(wait_seconds=0) == "failed"
    failed = user.get(f"/api/v1/jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert failed["error_message"] == "The source video is missing. Upload it again."
    assert user.get(f"/api/v1/clips/{clip['id']}").json()["status"] == "failed"


def test_agent_refuses_jobs_for_another_account(rig: Rig) -> None:
    finished: list[tuple[str, str, str | None]] = []
    rig.client.finish = lambda job_id, outcome, message: finished.append((job_id, outcome, message))  # type: ignore[method-assign]
    rig.client.progress = lambda *args: {}  # type: ignore[method-assign]
    outcome = rig.agent.run_job(
        {
            "job_id": "j1",
            "type": "purge_files",
            "owner_id": "someone-else",
            "prefix": "users/someone-else",
        }
    )
    assert outcome == "failed" and "different account" in (finished[0][2] or "")
    unknown = rig.agent.run_job(
        {"job_id": "j2", "type": "run_shell", "owner_id": rig.credentials.owner_id}
    )
    assert unknown == "failed" and "does not know the job type" in (finished[1][2] or "")


def test_job_specs_cannot_reach_outside_the_owners_folder(rig: Rig, tmp_path: Path) -> None:
    from app.jobs import compute

    outside = rig.agent.storage.root.parent / "keep-me.txt"
    outside.write_text("important", encoding="utf-8")
    owner = rig.credentials.owner_id
    io = RemoteJobIO(rig.client, "job")
    for prefix in ("users/other-user", "users", "../", f"users/{owner}/../../.."):
        with pytest.raises(ProcessingError):
            compute._owned_key({"owner_id": owner}, prefix)
    # A purge that names foreign keys deletes nothing.
    compute.purge_files(
        {"owner_id": owner, "prefix": None, "keys": ["../keep-me.txt", "users/other/x.mp4"]},
        rig.agent.env,
        io,
    )
    assert outside.read_text(encoding="utf-8") == "important"


# ------------------------------------------------------- unreliable networks
class FlakyClient:
    """Fails with a connection error a few times, then works."""

    def __init__(self, failures: int, error: Exception | None = None) -> None:
        self.failures = failures
        self.error = error
        self.events: list[str] = []

    def event(self, job_id: str, name: str, payload: dict[str, Any]) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise self.error or ConnectionProblem("network down")
        self.events.append(name)

    def progress(self, job_id: str, fraction: float, stage: str | None) -> dict[str, Any]:
        return {"cancel_requested": False}


def test_results_are_delivered_after_a_short_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.agent.runner.time.sleep", lambda _seconds: None)
    client = FlakyClient(failures=3)
    RemoteJobIO(client, "job").emit("transcript", {})  # type: ignore[arg-type]
    assert client.events == ["transcript"]
    with pytest.raises(ProcessingError, match="lost its connection"):
        RemoteJobIO(FlakyClient(failures=99), "job").emit("transcript", {})  # type: ignore[arg-type]
    with pytest.raises(JobCancelled):
        gone = FlakyClient(failures=1, error=ServerError(409, "job_not_active", "no longer active"))
        RemoteJobIO(gone, "job").emit("transcript", {})  # type: ignore[arg-type]


def test_worker_loop_survives_disconnections(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    stop = threading.Event()
    calls = {"n": 0}

    def flaky_step(wait_seconds: int | None = None) -> None:
        calls["n"] += 1
        if calls["n"] <= 3:
            raise ConnectionProblem("server unreachable")
        stop.set()

    monkeypatch.setattr(rig.agent, "step", flaky_step)
    monkeypatch.setattr(stop, "wait", lambda _timeout=None: False)  # do not really sleep
    assert rig.agent.run_forever(stop) == 0
    assert calls["n"] == 4  # three failures, then it reconnected


def test_worker_loop_stops_when_its_credentials_are_revoked(rig: Rig) -> None:
    import threading

    rig.user.delete(f"{WORKERS}/{rig.worker_id}")
    assert rig.agent.run_forever(threading.Event()) == 2


def test_csrf_header_is_sent_by_the_agent_client(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    # Worker endpoints sit behind the same middleware as the rest of the API.
    bare = TestClient(app)
    assert bare.post("/api/v1/agent/pair", json={"code": "ABCD-EFGH"}).status_code == 403
    with_header = TestClient(app, headers=CSRF_HEADERS)
    assert with_header.post("/api/v1/agent/pair", json={"code": "ABCD-EFGH"}).status_code == 422
