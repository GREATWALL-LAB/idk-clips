"""Small shared helpers for tests that wait on in-process jobs."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def wait_for_job(client: TestClient, job_id: str, timeout: float = 300) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.25)
    raise AssertionError("job did not finish")
