"""The worker's saved credentials (one small JSON file on the user's computer).

The token in this file is the only secret the worker has. It is written with
owner-only permissions where the platform supports it, never logged, and removed
by ``unpair``. Deleting the file is always a safe way to disconnect a worker; the
server-side entry can then be removed from the dashboard.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import Settings
from app.core.local_guard import LOOPBACK_NAMES

FILE_NAME = "credentials.json"


class AgentConfigError(Exception):
    """A user-facing problem with the worker's configuration."""


@dataclass
class Credentials:
    server_url: str
    worker_id: str
    worker_name: str
    token: str
    owner_id: str
    owner_name: str
    paired_at: str
    #: Web origins allowed to call the local bridge (comma separated), as told by the server.
    allowed_origins: str = ""

    def origins(self) -> list[str]:
        return [origin for origin in self.allowed_origins.split(",") if origin]

    def __repr__(self) -> str:  # never show the token in logs or tracebacks
        return f"Credentials(server_url={self.server_url!r}, worker_id={self.worker_id!r})"


def credentials_path(settings: Settings) -> Path:
    return settings.agent_dir / FILE_NAME


def validate_server_url(url: str, *, allow_http: bool = False) -> str:
    """Require HTTPS, except for a server on this same computer (development, self-hosting)."""
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise AgentConfigError("The server address must look like https://example.com")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise AgentConfigError("The server address must not contain credentials or parameters.")
    is_local = parts.hostname.lower() in LOOPBACK_NAMES
    if parts.scheme == "http" and not is_local and not allow_http:
        raise AgentConfigError(
            "Refusing to use an unencrypted http:// server address. Use https://, or set "
            "OPENCLIP_AGENT_ALLOW_HTTP=true if this is a server on your own trusted network."
        )
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def load(settings: Settings) -> Credentials | None:
    path = credentials_path(settings)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        values = {field: str(data[field]) for field in Credentials.__annotations__ if field in data}
        return Credentials(**values)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AgentConfigError(
            f"The saved worker credentials are unreadable ({path.name}). "
            "Run 'unpair' and pair this worker again."
        ) from exc


def save(settings: Settings, credentials: Credentials) -> Path:
    path = credentials_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    # Create the file with owner-only permissions before any secret is written to it.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(temporary, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(asdict(credentials), handle, indent=2)
    temporary.replace(path)
    with contextlib.suppress(OSError):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def clear(settings: Settings) -> bool:
    path = credentials_path(settings)
    if path.is_file():
        path.unlink()
        return True
    return False
