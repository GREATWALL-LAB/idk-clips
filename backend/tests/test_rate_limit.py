from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import TokenBucketLimiter
from app.main import create_app
from tests.conftest import make_settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_token_bucket_allows_burst_then_blocks_and_refills() -> None:
    clock = FakeClock()
    limiter = TokenBucketLimiter(capacity=3, window_seconds=60, clock=clock)
    assert [limiter.acquire("a")[0] for _ in range(3)] == [True, True, True]
    allowed, retry_after = limiter.acquire("a")
    assert allowed is False
    assert retry_after == pytest.approx(20.0)  # one token refills every 20 s
    assert limiter.acquire("b")[0] is True  # other clients are unaffected
    clock.now += 20
    assert limiter.acquire("a")[0] is True


def test_invalid_limiter_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        TokenBucketLimiter(capacity=0, window_seconds=60)


def test_middleware_returns_429_with_retry_after(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, rate_limit_enabled=True, rate_limit_requests_per_minute=2)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/auth/status").status_code == 200
        assert client.get("/api/v1/auth/status").status_code == 200
        response = client.get("/api/v1/auth/status", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) >= 1
        assert response.json()["error"]["code"] == "rate_limited"
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        # The health endpoint stays available for monitoring.
        assert client.get("/api/v1/health").status_code == 200


def test_rate_limit_can_be_disabled(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, rate_limit_enabled=False, rate_limit_requests_per_minute=1)
    with TestClient(create_app(settings)) as client:
        assert all(client.get("/").status_code == 200 for _ in range(5))
