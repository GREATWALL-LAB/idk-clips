"""Serve the exported web interface from the API process.

The frontend is a static export (plain HTML, CSS and JavaScript). In local mode the
API serves it itself, so running IDK Clips needs one process and no Node.js. For
the hosted site the same files go to any static host instead (see docs/DEPLOYMENT.md).
"""

from __future__ import annotations

from pathlib import Path

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

#: In hybrid mode the browser also talks to the user's worker bridge on 127.0.0.1.
BRIDGE_SOURCE = "http://127.0.0.1:*"


def content_security_policy(*, hybrid: bool = False) -> str:
    """The interface only talks to its own origin, so the policy can be strict.

    Next.js needs inline bootstrap scripts and styles; YouTube thumbnails come from ytimg.
    """
    bridge = f" {BRIDGE_SOURCE}" if hybrid else ""
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline'",
            f"img-src 'self' data: blob: https://i.ytimg.com{bridge}",
            f"media-src 'self' blob:{bridge}",
            f"connect-src 'self'{bridge}",
            "font-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


CONTENT_SECURITY_POLICY = content_security_policy()


class WebApp(StaticFiles):
    """Static files with sensible caching and a Content-Security-Policy on pages."""

    def __init__(self, directory: Path, *, hybrid: bool = False) -> None:
        super().__init__(directory=str(directory), html=True)
        self.policy = content_security_policy(hybrid=hybrid)

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        normalized = path.replace("\\", "/")
        if normalized.startswith("_next/static/"):
            # File names contain a content hash, so they can be cached forever.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Content-Security-Policy"] = self.policy
        return response
