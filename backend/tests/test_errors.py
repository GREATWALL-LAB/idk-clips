from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import NotFoundError
from app.main import create_app
from tests.conftest import make_settings


class Payload(BaseModel):
    name: str
    count: int


def _app_with_test_routes(tmp_path: Path) -> FastAPI:
    app = create_app(make_settings(tmp_path))

    @app.get("/test/not-found")
    async def not_found() -> None:
        raise NotFoundError("Project not found.")

    @app.get("/test/crash")
    async def crash() -> None:
        raise RuntimeError(r"secret internal detail at C:\server\private\path.py")

    @app.post("/test/validate")
    async def validate(payload: Payload) -> dict:
        return payload.model_dump()

    return app


def test_app_error_uses_standard_envelope(tmp_path: Path) -> None:
    with TestClient(_app_with_test_routes(tmp_path)) as client:
        response = client.get("/test/not-found")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["message"] == "Project not found."
    assert error["request_id"] == response.headers["x-request-id"]


def test_unknown_route_returns_friendly_404(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wrong_method_returns_405(client: TestClient) -> None:
    response = client.delete("/api/v1/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_validation_errors_list_fields_without_echoing_input(tmp_path: Path) -> None:
    with TestClient(_app_with_test_routes(tmp_path)) as client:
        response = client.post("/test/validate", json={"name": "x", "count": "SENSITIVE-VALUE"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "body.count"
    assert "SENSITIVE-VALUE" not in response.text


def test_unhandled_errors_hide_internal_details(tmp_path: Path) -> None:
    with TestClient(_app_with_test_routes(tmp_path), raise_server_exceptions=False) as client:
        response = client.get("/test/crash", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert "secret" not in response.text
    assert "private" not in response.text
    assert "Traceback" not in response.text
    # Error responses still carry CORS and request-ID headers so the UI can show them.
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert error["request_id"] == response.headers["x-request-id"]
