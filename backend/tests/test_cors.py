from __future__ import annotations

from fastapi.testclient import TestClient

ALLOWED = "http://localhost:3000"
BLOCKED = "https://evil.example.com"


def test_allowed_origin_receives_cors_header(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": ALLOWED})
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_unlisted_origin_gets_no_cors_header(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": BLOCKED})
    assert response.status_code == 200  # the server answers, but the browser will block it
    assert "access-control-allow-origin" not in response.headers


def test_preflight_for_allowed_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_preflight_for_unlisted_origin_is_refused(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={"Origin": BLOCKED, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_credentials_only_for_listed_origins(client: TestClient) -> None:
    # Cookies may be sent only because the origin list is explicit (never "*").
    allowed = client.get("/api/v1/health", headers={"Origin": ALLOWED})
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert allowed.headers["access-control-allow-origin"] == ALLOWED
    blocked = client.get("/api/v1/health", headers={"Origin": BLOCKED})
    assert "access-control-allow-origin" not in blocked.headers
