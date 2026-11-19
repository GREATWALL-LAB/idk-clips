"""Run IDK Clips: ``python -m app [serve] [--reload]`` or ``python -m app doctor``.

``serve`` (the default) starts the API with the host and port from the settings. In
local mode it also serves the web interface, so one process is the whole app.
``doctor`` checks that this computer has everything IDK Clips needs.
There is no administrator role or command: every account is an ordinary user.

The worker for hybrid mode is a separate command: ``python -m app.agent``.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from app.core.config import get_settings
from app.core.local_guard import is_loopback_address
from app.core.logging import configure_logging


def serve(reload: bool) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if (
        settings.mode == "local"
        and not settings.local_allow_remote
        and settings.host not in {"localhost"}
        and not is_loopback_address(settings.host)
    ):
        print(
            f"Local mode has no accounts, so it only listens on this computer, not on "
            f"'{settings.host}'.\nSet OPENCLIP_HOST=127.0.0.1, or choose OPENCLIP_MODE=server "
            "(accounts) to share IDK Clips on a network."
        )
        return 2
    shown_host = "localhost" if settings.host in {"127.0.0.1", "0.0.0.0", "::1"} else settings.host  # noqa: S104
    print(f"IDK Clips ({settings.mode} mode) -> http://{shown_host}:{settings.port}")
    if settings.web_dist is None:
        print(
            "  No web build found: this process serves the API only.\n"
            "  Build it with 'npm run build' in frontend/, or run 'npm run dev' there."
        )
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=reload,
        reload_dirs=["app", "../processing/openclip_processing"] if reload else None,
        access_log=False,
        log_config=None,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips or "127.0.0.1",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="Run IDK Clips.")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "doctor"],
        help="serve (default) starts the app; doctor checks the requirements.",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Restart automatically when code changes."
    )
    args = parser.parse_args(argv)
    if args.command == "doctor":
        from app.doctor import run_doctor

        return run_doctor(get_settings())
    return serve(args.reload)


if __name__ == "__main__":
    sys.exit(main())
