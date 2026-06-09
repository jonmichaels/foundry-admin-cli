"""Command-line interface for Foundry admin control."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .admin_client import AdminClient, AdminClientError, read_password_from_env
from .config import get_instance
from .modules import ModulePackageError, create_module, edit_module, list_modules, remove_module, update_module
from .packages import PackageOperationError, install_package
from .process import ProcessError, collect_logs, fetch_active_world, get_status, restart_instance, wait_until_ready
from .systems import SystemPackageError, list_systems, remove_system, update_system
from .world_client import WorldClient, WorldClientError, read_secret_from_env as read_world_secret_from_env
from .worlds import WorldConfigError, configure_world, create_world, delete_world, edit_world, list_worlds, stop_world


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fvtt", description="Foundry VTT admin CLI")
    parser.add_argument("--version", dest="foundry_version", default="v13", help="Foundry version: v13 or v14")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--cli-version", action="version", version=f"fvtt {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="Show Foundry server status")
    status.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    restart = subparsers.add_parser("restart", help="Restart Foundry PM2 process and wait for readiness")
    restart.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait for readiness")
    restart.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    logs = subparsers.add_parser("logs", help="Tail today's Foundry debug/error logs")
    logs.add_argument("--lines", type=int, default=50, help="Number of lines to read from each log")
    logs.add_argument("--filter", dest="contains", help="Only show lines containing this text")
    logs.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    wait = subparsers.add_parser("wait", help="Wait until Foundry answers unauthenticated HTTP GET /")
    wait.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait")
    wait.add_argument("--interval", type=float, default=1.0, help="Seconds between checks")
    wait.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

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
    admin_status = admin_subparsers.add_parser("status", help="Check persisted admin setup session")
    admin_status.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    admin_whoami = admin_subparsers.add_parser("whoami", help="Alias for admin status")
    admin_whoami.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    admin_probe = admin_subparsers.add_parser(
        "probe", help="Run a non-mutating authenticated setup POST probe"
    )
    admin_probe.add_argument("--type", default="module", choices=["module", "system", "world"])
    admin_probe.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

    systems = subparsers.add_parser("systems", help="System package lifecycle commands")
    systems_subparsers = systems.add_subparsers(dest="systems_command", required=True)
    systems_list = systems_subparsers.add_parser("list", help="List installed systems")
    systems_list.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    systems_install = systems_subparsers.add_parser("install", help="Install a system from a manifest URL")
    systems_install.add_argument("manifest", help="System manifest URL")
    systems_install.add_argument("--id", dest="package_id", help="Optional system id hint")
    systems_install.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    systems_update = systems_subparsers.add_parser("update", help="Update an installed system from its manifest URL")
    systems_update.add_argument("system_id", help="Installed system id")
    systems_update.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    systems_remove = systems_subparsers.add_parser("remove", help="Archive or permanently remove a system")
    systems_remove.add_argument("system_id", help="Installed system id")
    systems_remove.add_argument("--permanent", action="store_true", help="Permanently delete instead of archiving")
    systems_remove.add_argument("--force", action="store_true", help="Required for permanent remove or world dependencies")
    systems_remove.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

    modules = subparsers.add_parser("modules", help="Module package lifecycle commands")
    modules_subparsers = modules.add_subparsers(dest="modules_command", required=True)
    modules_list = modules_subparsers.add_parser("list", help="List installed modules")
    modules_list.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    modules_install = modules_subparsers.add_parser("install", help="Install a module from a manifest URL")
    modules_install.add_argument("manifest", help="Module manifest URL")
    modules_install.add_argument("--id", dest="package_id", help="Optional module id hint")
    modules_install.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    modules_update = modules_subparsers.add_parser("update", help="Update an installed module from its manifest URL")
    modules_update.add_argument("module_id", help="Installed module id")
    modules_update.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    modules_create = modules_subparsers.add_parser("create", help="Scaffold a minimal Foundry module project")
    modules_create.add_argument("module_id", help="Module id/project directory")
    modules_create.add_argument("--title", required=True, help="Module title")
    modules_create.add_argument("--symlink", action="store_true", help="Symlink scaffold into Data/modules")
    modules_create.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    modules_edit = modules_subparsers.add_parser("edit", help="Edit supported module manifest fields")
    modules_edit.add_argument("module_id", help="Installed module id")
    modules_edit.add_argument("--title", help="New module title")
    modules_edit.add_argument("--manifest", dest="manifest_url", help="New module manifest URL")
    modules_edit.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    modules_remove = modules_subparsers.add_parser("remove", help="Archive, unlink, or permanently remove a module")
    modules_remove.add_argument("module_id", help="Installed module id")
    modules_remove.add_argument("--permanent", action="store_true", help="Permanently delete instead of archiving")
    modules_remove.add_argument("--force", action="store_true", help="Required for permanent remove")
    modules_remove.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

    world = subparsers.add_parser("world", help="Active world session commands")
    world_subparsers = world.add_subparsers(dest="world_command", required=True)
    world_login = world_subparsers.add_parser("login", help="Authenticate a GM user into the running world")
    world_login.add_argument("world_id", help="Expected running world id")
    world_login.add_argument("--user", required=True, help="Foundry GM user id/name")
    world_login.add_argument("--password-env", required=True, help="Environment variable containing the GM password")
    world_login.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    world_ping = world_subparsers.add_parser("ping", help="Verify persisted authenticated world session")
    world_ping.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

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

    if args.command in {"restart", "logs", "wait"}:
        try:
            if args.command == "restart":
                data = restart_instance(instance, timeout_seconds=args.timeout)
            elif args.command == "logs":
                data = collect_logs(instance, lines=args.lines, contains=args.contains)
            else:
                data = wait_until_ready(
                    instance,
                    timeout_seconds=args.timeout,
                    interval_seconds=args.interval,
                )
        except ProcessError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "admin":
        client = AdminClient(instance)
        try:
            if args.admin_command == "login":
                data = client.login(read_password_from_env(args.password_env, env_file=instance.data_dir / ".env"))
            elif args.admin_command == "logout":
                data = client.logout()
            elif args.admin_command in {"status", "whoami"}:
                data = client.status()
            elif args.admin_command == "probe":
                data = client.setup_probe(package_type=args.type)
            else:
                parser.error(f"Unknown admin command: {args.admin_command}")
        except AdminClientError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "systems":
        try:
            if args.systems_command == "list":
                data = list_systems(instance)
            elif args.systems_command == "install":
                data = install_package(
                    instance,
                    package_type="system",
                    manifest=args.manifest,
                    package_id=args.package_id,
                    client=AdminClient(instance),
                )
            elif args.systems_command == "update":
                data = update_system(instance, args.system_id, client=AdminClient(instance))
            elif args.systems_command == "remove":
                data = remove_system(instance, args.system_id, permanent=args.permanent, force=args.force)
            else:
                parser.error(f"Unknown systems command: {args.systems_command}")
        except (SystemPackageError, PackageOperationError, AdminClientError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "modules":
        try:
            if args.modules_command == "list":
                data = list_modules(instance)
            elif args.modules_command == "install":
                data = install_package(
                    instance,
                    package_type="module",
                    manifest=args.manifest,
                    package_id=args.package_id,
                    client=AdminClient(instance),
                )
            elif args.modules_command == "update":
                data = update_module(instance, args.module_id, client=AdminClient(instance))
            elif args.modules_command == "create":
                data = create_module(instance, args.module_id, title=args.title, symlink=args.symlink)
            elif args.modules_command == "edit":
                data = edit_module(instance, args.module_id, title=args.title, manifest_url=args.manifest_url)
            elif args.modules_command == "remove":
                data = remove_module(instance, args.module_id, permanent=args.permanent, force=args.force)
            else:
                parser.error(f"Unknown modules command: {args.modules_command}")
        except (ModulePackageError, PackageOperationError, AdminClientError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "world":
        client = WorldClient(instance)
        try:
            if args.world_command == "login":
                data = client.login(
                    args.world_id,
                    user=args.user,
                    password=read_world_secret_from_env(args.password_env, env_file=instance.data_dir / ".env"),
                )
            elif args.world_command == "ping":
                data = client.ping()
            else:
                parser.error(f"Unknown world command: {args.world_command}")
        except WorldClientError as exc:
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
