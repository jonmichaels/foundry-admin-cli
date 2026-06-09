"""Command-line interface for Foundry admin control."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .admin_client import AdminClient, AdminClientError, read_password_from_env
from .config import get_instance
from .process import fetch_active_world, get_status
from .worlds import WorldConfigError, configure_world, create_world, delete_world, edit_world, list_worlds, stop_world


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fvtt", description="Foundry VTT admin CLI")
    parser.add_argument("--version", dest="foundry_version", default="v13", help="Foundry version: v13 or v14")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--cli-version", action="version", version=f"fvtt {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="Show Foundry server status")
    status.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

    admin = subparsers.add_parser("admin", help="Admin session and setup probes")
    admin_subparsers = admin.add_subparsers(dest="admin_command", required=True)
    admin_login = admin_subparsers.add_parser("login", help="Authenticate as Foundry administrator")
    admin_login.add_argument(
        "--password-env",
        required=True,
        help="Environment variable containing the Foundry admin password",
    )
    admin_login.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    admin_logout = admin_subparsers.add_parser("logout", help="Revoke current admin session")
    admin_logout.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    admin_probe = admin_subparsers.add_parser(
        "probe", help="Run a non-mutating authenticated setup POST probe"
    )
    admin_probe.add_argument("--type", default="module", choices=["module", "system", "world"])
    admin_probe.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

    worlds = subparsers.add_parser("worlds", help="World lifecycle commands")
    worlds_subparsers = worlds.add_subparsers(dest="worlds_command", required=True)
    worlds_list = worlds_subparsers.add_parser("list", help="List installed worlds")
    worlds_list.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    worlds_create = worlds_subparsers.add_parser("create", help="Create a world directory and manifest")
    worlds_create.add_argument("world_id", help="World id/directory to create")
    worlds_create.add_argument("--title", required=True, help="World title")
    worlds_create.add_argument("--system", required=True, help="World system id")
    worlds_create.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    worlds_edit = worlds_subparsers.add_parser("edit", help="Edit supported world manifest fields")
    worlds_edit.add_argument("world_id", help="World id/directory to edit")
    worlds_edit.add_argument("--title", help="New world title")
    worlds_edit.add_argument("--system", help="New world system id")
    worlds_edit.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    worlds_delete = worlds_subparsers.add_parser("delete", help="Archive or permanently delete a world")
    worlds_delete.add_argument("world_id", help="World id/directory to delete")
    worlds_delete.add_argument("--permanent", action="store_true", help="Permanently delete instead of archiving")
    worlds_delete.add_argument("--force", action="store_true", help="Required for permanent delete or configured world")
    worlds_delete.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    worlds_run = worlds_subparsers.add_parser("run", help="Configure a world to launch on next restart")
    worlds_run.add_argument("world_id", help="World id/directory to configure")
    worlds_run.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    worlds_stop = worlds_subparsers.add_parser("stop", help="Clear configured world so Foundry starts in setup mode")
    worlds_stop.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    return parser


def emit(data: object, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return

    if isinstance(data, dict) and "version" in data and "status" in data:
        print(
            f"{data['version']}: {data['status']} | "
            f"PID {data['pid']} | port {data['port']} | "
            f"active: {data['active_world']} | configured: {data['configured_world']}"
        )
        if data.get("memory_mb") is not None:
            print(f"memory: {data['memory_mb']}MB")
        return

    if isinstance(data, dict) and "restart_required" in data:
        target = data.get("world") if data.get("world") is not None else "setup"
        state = "changed" if data.get("changed") else "unchanged"
        restart = "restart required" if data.get("restart_required") else "no restart required"
        print(f"configured world: {target} | {state} | {restart}")
        if data.get("previous_world") is not None:
            print(f"previous: {data['previous_world']}")
        return

    if isinstance(data, list) and all(isinstance(item, dict) and "system" in item for item in data):
        for world in data:
            marker = "*" if world.get("active") else " "
            states = []
            if world.get("active"):
                states.append("active")
            if world.get("configured"):
                states.append("configured")
            if not world.get("valid", True):
                states.append("invalid")
            state = ", ".join(states) if states else "installed"
            print(f"{marker} {world['id']} | {world.get('title')} | system {world.get('system')} | {state}")
        return

    print(data)


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        instance = get_instance(args.foundry_version)
    except ValueError as exc:
        parser.error(str(exc))

    if args.command == "status":
        emit(get_status(instance).to_dict(), as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "admin":
        client = AdminClient(instance)
        try:
            if args.admin_command == "login":
                data = client.login(read_password_from_env(args.password_env))
            elif args.admin_command == "logout":
                data = client.logout()
            elif args.admin_command == "probe":
                data = client.setup_probe(package_type=args.type)
            else:
                parser.error(f"Unknown admin command: {args.admin_command}")
        except AdminClientError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "worlds":
        try:
            if args.worlds_command == "list":
                data = list_worlds(instance, active_world=fetch_active_world(instance))
            elif args.worlds_command == "create":
                data = create_world(instance, args.world_id, title=args.title, system=args.system)
            elif args.worlds_command == "edit":
                data = edit_world(instance, args.world_id, title=args.title, system=args.system)
            elif args.worlds_command == "delete":
                data = delete_world(instance, args.world_id, permanent=args.permanent, force=args.force)
            elif args.worlds_command == "run":
                data = configure_world(instance, args.world_id)
            elif args.worlds_command == "stop":
                data = stop_world(instance)
            else:
                parser.error(f"Unknown worlds command: {args.worlds_command}")
        except WorldConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
