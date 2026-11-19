"""HTTP client for the server's worker endpoints (``/api/v1/agent``)."""

from __future__ import annotations

from typing import Any

import httpx

from app import __version__
from app.agent import AGENT_NAME
from app.core.csrf import CSRF_HEADER, CSRF_HEADER_VALUE


class ServerError(Exception):
    """The server answered with an error."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class NotAuthorized(ServerError):
    """The worker's credentials were rejected (removed from the account, or never valid)."""


class ConnectionProblem(Exception):
    """The server could not be reached. Always temporary from the worker's point of view."""


class ServerClient:
    def __init__(
        self,
        server_url: str,
        token: str | None = None,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        headers = {
            "User-Agent": f"{AGENT_NAME}/{__version__}",
            "Accept": "application/json",
            CSRF_HEADER: CSRF_HEADER_VALUE,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        base_url = f"{self.server_url}/api/v1/agent"
        if http_client is not None:
            # Tests hand in a client that is wired straight into the server app.
            http_client.base_url = base_url  # type: ignore[assignment]
            http_client.headers.update(headers)
            http_client.follow_redirects = False
            self._client = http_client
        else:
            self._client = httpx.Client(
                base_url=base_url,
                headers=headers,
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=60.0, pool=10.0),
                follow_redirects=False,  # a redirect must never carry the token elsewhere
            )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ core
    def _request(
        self, method: str, path: str, *, json: Any = None, read_timeout: float | None = None
    ) -> dict[str, Any]:
        try:
            if read_timeout is not None:
                # A plain number keeps this compatible with any httpx-style client.
                response = self._client.request(method, path, json=json, timeout=read_timeout)
            else:
                response = self._client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise ConnectionProblem(str(exc) or exc.__class__.__name__) from exc
        if response.status_code in (200, 201):
            try:
                data = response.json()
            except ValueError as exc:
                raise ServerError(
                    response.status_code, "bad_response", "Unreadable answer."
                ) from exc
            return data if isinstance(data, dict) else {}
        if response.status_code in (202, 204):
            return {}
        code, message = "http_error", f"The server answered with status {response.status_code}."
        try:
            error = (response.json() or {}).get("error") or {}
            code = str(error.get("code") or code)
            message = str(error.get("message") or message)
        except ValueError:
            pass
        if response.status_code == 401:
            raise NotAuthorized(401, code, message)
        if response.status_code in (502, 503, 504):
            raise ConnectionProblem(message)
        raise ServerError(response.status_code, code, message)

    # ------------------------------------------------------------- endpoints
    def pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/pair", json=payload)

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/heartbeat", json=payload)

    def unpair(self) -> None:
        self._request("DELETE", "/self")

    def claim(self, wait_seconds: int) -> dict[str, Any] | None:
        data = self._request(
            "POST",
            "/jobs/claim",
            json={"wait_seconds": wait_seconds},
            read_timeout=wait_seconds + 30.0,
        )
        job = data.get("job")
        return job if isinstance(job, dict) else None

    def progress(self, job_id: str, fraction: float, stage: str | None) -> dict[str, Any]:
        return self._request(
            "POST", f"/jobs/{job_id}/progress", json={"progress": fraction, "stage": stage}
        )

    def event(self, job_id: str, name: str, payload: dict[str, Any]) -> None:
        self._request(
            "POST",
            f"/jobs/{job_id}/events",
            json={"name": name, "payload": payload},
            read_timeout=120.0,
        )

    def finish(self, job_id: str, outcome: str, message: str | None) -> None:
        self._request(
            "POST", f"/jobs/{job_id}/finish", json={"outcome": outcome, "message": message}
        )

    def verify_transfer_token(self, token: str) -> dict[str, Any]:
        return self._request("POST", "/transfer-tokens/verify", json={"token": token})

    def register_media(self, project_id: str, payload: dict[str, Any]) -> None:
        self._request("POST", f"/projects/{project_id}/media", json=payload)
