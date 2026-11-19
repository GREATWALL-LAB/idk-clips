"""Worker command line: ``python -m app.agent <command>``.

Commands:
  pair     Connect this computer to your IDK Clips account with a one-time code.
  run      Start working: wait for your jobs and process them on this computer.
  status   Show whether this computer is paired and whether the server answers.
  unpair   Disconnect this computer and delete its saved credentials.
  doctor   Check that FFmpeg, the speech model and Ollama are ready.
  purge    Delete every video and clip this worker stores for the paired account.
"""

from __future__ import annotations

import argparse
import logging
import platform
import signal
import sys
import threading
from datetime import UTC, datetime

from app import __version__
from app.agent import DISPLAY_NAME, state
from app.agent.bridge import BridgeServer, create_bridge
from app.agent.capabilities import collect_capabilities
from app.agent.client import ConnectionProblem, NotAuthorized, ServerClient, ServerError
from app.agent.runner import Agent
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, redactor
from app.doctor import run_doctor
from app.services.storage import LocalStorage

logger = logging.getLogger("app.agent")


def _platform_label() -> str:
    return f"{platform.system()} {platform.release()}"[:40]


def cmd_pair(settings: Settings, args: argparse.Namespace) -> int:
    existing = state.load(settings)
    if existing is not None and not args.force:
        print(
            f"This computer is already paired with {existing.server_url} as "
            f"'{existing.worker_name}'.\nRun 'unpair' first, or add --force to replace it."
        )
        return 1
    try:
        server_url = state.validate_server_url(args.server, allow_http=settings.agent_allow_http)
    except state.AgentConfigError as exc:
        print(f"Cannot pair: {exc}")
        return 1
    client = ServerClient(server_url)
    try:
        answer = client.pair(
            {
                "code": args.code,
                "name": args.name or platform.node() or "My computer",
                "platform": _platform_label(),
                "app_version": __version__,
                "bridge_port": settings.agent_bridge_port,
                "capabilities": collect_capabilities(settings),
            }
        )
    except ConnectionProblem as exc:
        print(f"Cannot reach {server_url}: {exc}\nCheck the address and your internet connection.")
        return 1
    except ServerError as exc:
        print(f"Pairing was refused: {exc.message}")
        return 1
    finally:
        client.close()
    token = str(answer["token"])
    redactor.register(token)
    path = state.save(
        settings,
        state.Credentials(
            server_url=server_url,
            worker_id=str(answer["worker_id"]),
            worker_name=str(answer["worker_name"]),
            token=token,
            owner_id=str(answer["owner_id"]),
            owner_name=str(answer["owner_name"]),
            paired_at=datetime.now(UTC).isoformat(),
            allowed_origins=",".join(str(o) for o in answer.get("allowed_origins") or []),
        ),
    )
    print(
        f"Paired. This computer is now '{answer['worker_name']}' for {answer['owner_name']}.\n"
        f"Credentials were saved to {path}\n"
        "Start processing with:  scripts\\windows\\worker.cmd run\n"
        "                  (Linux/macOS: bash scripts/linux/worker.sh run)"
    )
    return 0


def _load_or_explain(settings: Settings) -> state.Credentials | None:
    try:
        credentials = state.load(settings)
    except state.AgentConfigError as exc:
        print(str(exc))
        return None
    if credentials is None:
        print(
            "This computer is not paired yet.\nOpen the IDK Clips dashboard, choose "
            "'Connect a worker', and run the 'pair' command it shows."
        )
        return None
    redactor.register(credentials.token)
    return credentials


def cmd_run(settings: Settings, args: argparse.Namespace) -> int:
    credentials = _load_or_explain(settings)
    if credentials is None:
        return 1
    for folder in (settings.data_dir, settings.tmp_dir, settings.models_dir, settings.storage_dir):
        folder.mkdir(parents=True, exist_ok=True)
    agent = Agent(settings, credentials)
    try:
        info = agent.heartbeat()
    except NotAuthorized as exc:
        print(f"The server no longer accepts this worker: {exc.message}\nPair it again.")
        return 2
    except (ConnectionProblem, ServerError) as exc:
        # Not fatal: the loop below keeps retrying. The bridge uses the origins saved at pairing.
        logger.warning(
            "Server not reachable yet; will keep trying", extra={"reason": str(exc)[:200]}
        )
        info = {}
    origins = sorted({*credentials.origins(), *(info.get("allowed_origins") or [])})

    bridge = BridgeServer(
        create_bridge(
            settings,
            credentials,
            agent.client,
            agent.storage,
            allowed_origins=origins,
        ),
        settings.agent_bridge_port,
    )
    if not bridge.start():
        print(
            f"Could not open the local bridge on 127.0.0.1:{settings.agent_bridge_port}. "
            "Another program may be using that port; set OPENCLIP_AGENT_BRIDGE_PORT to a free one."
        )
        return 1

    stop = threading.Event()

    def request_stop(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    print(
        f"{DISPLAY_NAME} {__version__}: '{credentials.worker_name}' for {credentials.owner_name}\n"
        f"  server : {credentials.server_url}\n"
        f"  bridge : http://127.0.0.1:{settings.agent_bridge_port} (this computer only)\n"
        f"  files  : {settings.storage_dir}\n"
        "Waiting for jobs. Press Ctrl+C to stop."
    )
    try:
        code = agent.run_forever(stop)
    finally:
        bridge.stop()
        agent.client.close()
    print("Worker stopped.")
    return code


def cmd_status(settings: Settings, args: argparse.Namespace) -> int:
    credentials = _load_or_explain(settings)
    if credentials is None:
        return 1
    print(
        f"Paired as '{credentials.worker_name}' for {credentials.owner_name}\n"
        f"  server    : {credentials.server_url}\n"
        f"  worker id : {credentials.worker_id}\n"
        f"  paired at : {credentials.paired_at}"
    )
    agent = Agent(settings, credentials)
    try:
        agent.heartbeat()
        print("  server    : reachable, credentials accepted")
        return 0
    except NotAuthorized as exc:
        print(f"  server    : credentials rejected ({exc.message})")
        return 2
    except (ConnectionProblem, ServerError) as exc:
        print(f"  server    : not reachable right now ({str(exc)[:120]})")
        return 1
    finally:
        agent.client.close()


def cmd_unpair(settings: Settings, args: argparse.Namespace) -> int:
    credentials = _load_or_explain(settings)
    if credentials is None:
        return 1
    client = ServerClient(credentials.server_url, credentials.token)
    try:
        client.unpair()
        print("The server removed this worker from your account.")
    except (ConnectionProblem, ServerError) as exc:
        print(
            f"Could not tell the server ({str(exc)[:120]}). The local credentials are removed "
            "anyway; also remove this worker in the dashboard."
        )
    finally:
        client.close()
    state.clear(settings)
    print("Saved credentials deleted. Videos and clips on this computer were not touched.")
    return 0


def cmd_purge(settings: Settings, args: argparse.Namespace) -> int:
    credentials = _load_or_explain(settings)
    if credentials is None:
        return 1
    storage = LocalStorage(settings.storage_dir)
    prefix = LocalStorage.user_prefix(credentials.owner_id)
    size = storage.usage_bytes(prefix)
    if not args.yes:
        print(
            f"This deletes every video and clip stored for {credentials.owner_name} on this "
            f"computer ({size / 1024**2:.0f} MB). Run again with --yes to confirm."
        )
        return 1
    storage.delete_tree(prefix)
    print(f"Deleted {size / 1024**2:.0f} MB.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.agent",
        description="IDK Clips worker: processes your videos on this computer.",
    )
    parser.add_argument("--version", action="version", version=f"{DISPLAY_NAME} {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    pair = commands.add_parser("pair", help="Connect this computer to your account.")
    pair.add_argument("--server", required=True, help="Address of the IDK Clips server.")
    pair.add_argument("--code", required=True, help="One-time code from the dashboard.")
    pair.add_argument(
        "--name", default="", help="Name shown in the dashboard (default: computer name)."
    )
    pair.add_argument("--force", action="store_true", help="Replace an existing pairing.")
    pair.set_defaults(handler=cmd_pair)

    commands.add_parser("run", help="Wait for jobs and process them.").set_defaults(handler=cmd_run)
    commands.add_parser("status", help="Show the pairing and connection.").set_defaults(
        handler=cmd_status
    )
    commands.add_parser("unpair", help="Disconnect this computer.").set_defaults(handler=cmd_unpair)
    commands.add_parser("doctor", help="Check FFmpeg, speech model and Ollama.").set_defaults(
        handler=lambda settings, args: run_doctor(settings, worker=True)
    )
    purge = commands.add_parser("purge", help="Delete all files stored for the paired account.")
    purge.add_argument("--yes", action="store_true", help="Confirm the deletion.")
    purge.set_defaults(handler=cmd_purge)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    for secret in settings.secret_values():
        redactor.register(secret)
    return int(args.handler(settings, args))


if __name__ == "__main__":
    sys.exit(main())
