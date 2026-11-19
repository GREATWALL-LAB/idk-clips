from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "openclip-ai-backend"
    assert body["environment"] == "test"
    assert body["version"]
    assert body["uptime_seconds"] >= 0


def test_every_response_has_request_id_and_security_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert len(response.headers["x-request-id"]) >= 16
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_valid_incoming_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-abc_123"})
    assert response.headers["x-request-id"] == "trace-abc_123"


def test_unsafe_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert response.headers["x-request-id"] != "bad id\nwith newline"
    assert " " not in response.headers["x-request-id"]


def test_root_describes_api(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["health"] == "/api/v1/health"
    assert body["docs"] == "/api/docs"


def test_openapi_lists_versioned_routes(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/system/status" in paths
