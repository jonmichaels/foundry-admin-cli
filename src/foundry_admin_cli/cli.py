"""Command-line interface for Foundry admin control."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .admin_client import AdminClient, AdminClientError, read_password_from_env
from .config import get_instance
from .process import get_status


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
    return parser


def emit(data: object, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return

    if isinstance(data, dict) and "version" in data:
        print(
            f"{data['version']}: {data['status']} | "
            f"PID {data['pid']} | port {data['port']} | "
            f"active: {data['active_world']} | configured: {data['configured_world']}"
        )
        if data.get("memory_mb") is not None:
            print(f"memory: {data['memory_mb']}MB")
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

    parser.error(f"Unknown command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
