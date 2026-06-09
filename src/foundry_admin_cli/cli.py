"""Command-line interface for Foundry admin control."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .admin_client import AdminClient, AdminClientError, read_password_from_env
from .config import ConfigurationError, apply_overrides, get_instance, load_config
from .modules import ModulePackageError, create_module, edit_module, list_modules, remove_module, update_module
from .packages import PackageOperationError, install_package
from .process import ProcessError, collect_logs, fetch_active_world, get_status, restart_instance, wait_until_ready
from .systems import SystemPackageError, list_systems, remove_system, update_system
from .world_client import (
    WorldClient,
    WorldClientError,
    read_secret_from_env as read_world_secret_from_env,
    resolve_world_user_id,
)
from .world_modules import (
    ModuleSettingError,
    disable_world_module,
    enable_world_module,
    list_world_modules,
    set_world_modules,
)
from .worlds import WorldConfigError, configure_world, create_world, delete_world, edit_world, list_worlds, stop_world


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fvtt", description="Foundry VTT admin CLI")
    parser.add_argument("--version", dest="foundry_version", default="v13", help="Foundry version: v13 or v14")
    parser.add_argument("--config", type=Path, help="Path to foundry-admin-cli.toml")
    parser.add_argument("--install-dir", type=Path, help="Override Foundry install directory")
    parser.add_argument("--data-dir", type=Path, help="Override Foundry user data directory")
    parser.add_argument("--url", help="Override Foundry base URL")
    parser.add_argument("--pm2-name", help="Override PM2 process name")
    parser.add_argument("--pm2-bin", help="Override PM2 executable path")
    parser.add_argument("--run-home", type=Path, help="Override HOME used for PM2/process commands")
    parser.add_argument("--cache-dir", type=Path, help="Override cache/cookie directory")
    parser.add_argument("--backup-dir", type=Path, help="Override backup/archive directory")
    parser.add_argument("--node-bin", help="Override Node.js executable for socket helpers")
    parser.add_argument("--mode", choices=["local", "remote", "http-only"], help="Override instance capability mode")
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

    system = subparsers.add_parser("system", help="System package lifecycle commands")
    system_subparsers = system.add_subparsers(dest="system_command", required=True)
    system_list = system_subparsers.add_parser("list", help="List installed systems")
    system_list.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    system_install = system_subparsers.add_parser("install", help="Install a system from a manifest URL")
    system_install.add_argument("manifest", help="System manifest URL")
    system_install.add_argument("--id", dest="package_id", help="Optional system id hint")
    system_install.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    system_update = system_subparsers.add_parser("update", help="Update an installed system from its manifest URL")
    system_update.add_argument("system_id", help="Installed system id")
    system_update.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    system_remove = system_subparsers.add_parser("remove", help="Archive or permanently remove a system")
    system_remove.add_argument("system_id", help="Installed system id")
    system_remove.add_argument("--permanent", action="store_true", help="Permanently delete instead of archiving")
    system_remove.add_argument("--force", action="store_true", help="Required for permanent remove or world dependencies")
    system_remove.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

    module = subparsers.add_parser("module", help="Module package lifecycle commands")
    module_subparsers = module.add_subparsers(dest="module_command", required=True)
    module_list = module_subparsers.add_parser("list", help="List installed modules")
    module_list.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    module_install = module_subparsers.add_parser("install", help="Install a module from a manifest URL")
    module_install.add_argument("manifest", help="Module manifest URL")
    module_install.add_argument("--id", dest="package_id", help="Optional module id hint")
    module_install.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    module_update = module_subparsers.add_parser("update", help="Update an installed module from its manifest URL")
    module_update.add_argument("module_id", help="Installed module id")
    module_update.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    module_create = module_subparsers.add_parser("create", help="Scaffold a minimal Foundry module project")
    module_create.add_argument("module_id", help="Module id/project directory")
    module_create.add_argument("--title", required=True, help="Module title")
    module_create.add_argument("--projects-dir", help="Override configured module scaffold project root")
    module_create.add_argument("--symlink", action="store_true", help="Symlink scaffold into Data/modules")
    module_create.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    module_edit = module_subparsers.add_parser("edit", help="Edit supported module manifest fields")
    module_edit.add_argument("module_id", help="Installed module id")
    module_edit.add_argument("--title", help="New module title")
    module_edit.add_argument("--manifest", dest="manifest_url", help="New module manifest URL")
    module_edit.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    module_remove = module_subparsers.add_parser("remove", help="Archive, unlink, or permanently remove a module")
    module_remove.add_argument("module_id", help="Installed module id")
    module_remove.add_argument("--permanent", action="store_true", help="Permanently delete instead of archiving")
    module_remove.add_argument("--force", action="store_true", help="Required for permanent remove")
    module_remove.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

    game = subparsers.add_parser("game", help="Active game session commands")
    game_subparsers = game.add_subparsers(dest="game_command", required=True)
    game_login = game_subparsers.add_parser("login", help="Authenticate a GM user into the running game")
    game_login.add_argument("world_id", help="Expected running world id")
    game_login.add_argument("--user", required=True, help="Foundry GM user id/name")
    game_login.add_argument("--password-env", help="Environment variable containing the GM password")
    game_login.add_argument(
        "--allow-empty-password",
        action="store_true",
        help="Explicitly allow passwordless login for a fresh default Gamemaster user",
    )
    game_login.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    game_ping = game_subparsers.add_parser("ping", help="Verify persisted authenticated game session")
    game_ping.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    game_return = game_subparsers.add_parser("return-to-setup", help="Shut down the running game and return to setup")
    game_return.add_argument("--world", required=True, help="Expected running world id")
    game_return.add_argument("--admin-password-env", help="Environment variable containing the admin password if setup re-authentication is needed")
    game_return.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    game_module = game_subparsers.add_parser("module", help="Manage active modules in the running game")
    game_module_subparsers = game_module.add_subparsers(dest="game_module_command", required=True)
    game_module_list = game_module_subparsers.add_parser("list", help="List running-game module activation")
    game_module_list.add_argument("--world", required=True, help="Expected running world id")
    game_module_list.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    game_module_enable = game_module_subparsers.add_parser("enable", help="Enable a module in the running game")
    game_module_enable.add_argument("module_id", help="Module id to enable")
    game_module_enable.add_argument("--world", required=True, help="Expected running world id")
    game_module_enable.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    game_module_disable = game_module_subparsers.add_parser("disable", help="Disable a module in the running game")
    game_module_disable.add_argument("module_id", help="Module id to disable")
    game_module_disable.add_argument("--world", required=True, help="Expected running world id")
    game_module_disable.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    game_module_set = game_module_subparsers.add_parser("set", help="Replace running-game module activation list")
    game_module_set.add_argument("--world", required=True, help="Expected running world id")
    game_module_set.add_argument("--modules", required=True, help="Comma-separated module ids to enable")
    game_module_set.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

    world = subparsers.add_parser("world", help="World lifecycle commands")
    world_subparsers = world.add_subparsers(dest="world_command", required=True)
    world_list = world_subparsers.add_parser("list", help="List installed worlds")
    world_list.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    world_create = world_subparsers.add_parser("create", help="Create a world directory and manifest")
    world_create.add_argument("world_id", help="World id/directory to create")
    world_create.add_argument("--title", required=True, help="World title")
    world_create.add_argument("--system", required=True, help="World system id")
    world_create.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    world_edit = world_subparsers.add_parser("edit", help="Edit supported world manifest fields")
    world_edit.add_argument("world_id", help="World id/directory to edit")
    world_edit.add_argument("--title", help="New world title")
    world_edit.add_argument("--system", help="New world system id")
    world_edit.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    world_delete = world_subparsers.add_parser("delete", help="Archive or permanently delete a world")
    world_delete.add_argument("world_id", help="World id/directory to delete")
    world_delete.add_argument("--permanent", action="store_true", help="Permanently delete instead of archiving")
    world_delete.add_argument("--force", action="store_true", help="Required for permanent delete or configured world")
    world_delete.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    world_run = world_subparsers.add_parser("run", help="Configure a world to launch on next restart")
    world_run.add_argument("world_id", help="World id/directory to configure")
    world_run.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")
    world_stop = world_subparsers.add_parser("stop", help="Clear configured world so Foundry starts in setup mode")
    world_stop.add_argument("--json", action="store_true", dest="command_json", help="Emit JSON output")

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
        config = load_config(config_paths=[args.config] if args.config else None)
        config = apply_overrides(
            config,
            version=args.foundry_version,
            install_dir=args.install_dir,
            data_dir=args.data_dir,
            url=args.url,
            pm2_name=args.pm2_name,
            pm2_bin=args.pm2_bin,
            run_home=args.run_home,
            cache_dir=args.cache_dir,
            backup_dir=args.backup_dir,
            node_bin=args.node_bin,
            mode=args.mode,
        )
        instance = get_instance(args.foundry_version, config=config)
    except (ValueError, ConfigurationError) as exc:
        parser.error(str(exc))

    if args.command == "status":
        try:
            data = get_status(instance).to_dict()
        except (ConfigurationError, ProcessError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
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
        except (ConfigurationError, ProcessError) as exc:
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
        except (ConfigurationError, AdminClientError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "system":
        try:
            if args.system_command == "list":
                data = list_systems(instance)
            elif args.system_command == "install":
                data = install_package(
                    instance,
                    package_type="system",
                    manifest=args.manifest,
                    package_id=args.package_id,
                    client=AdminClient(instance),
                )
            elif args.system_command == "update":
                data = update_system(instance, args.system_id, client=AdminClient(instance))
            elif args.system_command == "remove":
                data = remove_system(instance, args.system_id, permanent=args.permanent, force=args.force)
            else:
                parser.error(f"Unknown system command: {args.system_command}")
        except (ConfigurationError, SystemPackageError, PackageOperationError, AdminClientError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "module":
        try:
            if args.module_command == "list":
                data = list_modules(instance)
            elif args.module_command == "install":
                data = install_package(
                    instance,
                    package_type="module",
                    manifest=args.manifest,
                    package_id=args.package_id,
                    client=AdminClient(instance),
                )
            elif args.module_command == "update":
                data = update_module(instance, args.module_id, client=AdminClient(instance))
            elif args.module_command == "create":
                data = create_module(
                    instance,
                    args.module_id,
                    title=args.title,
                    projects_dir=Path(args.projects_dir) if args.projects_dir else None,
                    symlink=args.symlink,
                )
            elif args.module_command == "edit":
                data = edit_module(instance, args.module_id, title=args.title, manifest_url=args.manifest_url)
            elif args.module_command == "remove":
                data = remove_module(instance, args.module_id, permanent=args.permanent, force=args.force)
            else:
                parser.error(f"Unknown module command: {args.module_command}")
        except (ConfigurationError, ModulePackageError, PackageOperationError, AdminClientError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "game":
        client = WorldClient(instance)
        try:
            if args.game_command == "login":
                if args.allow_empty_password and args.password_env:
                    raise WorldClientError(
                        "--password-env cannot be combined with --allow-empty-password"
                    )
                if args.allow_empty_password:
                    password = ""
                elif args.password_env:
                    password = read_world_secret_from_env(
                        args.password_env, env_file=instance.data_dir / ".env"
                    )
                else:
                    raise WorldClientError(
                        "--password-env is required unless --allow-empty-password is set"
                    )
                resolved_user = resolve_world_user_id(instance, args.world_id, args.user)
                data = client.login(
                    args.world_id,
                    user=resolved_user,
                    password=password,
                    allow_empty_password=args.allow_empty_password,
                )
            elif args.game_command == "ping":
                data = client.ping()
            elif args.game_command == "return-to-setup":
                admin_password = None
                if args.admin_password_env:
                    admin_password = read_password_from_env(args.admin_password_env, env_file=instance.data_dir / ".env")
                data = client.return_to_setup(args.world, admin_password=admin_password)
            elif args.game_command == "module":
                if args.game_module_command == "list":
                    data = list_world_modules(instance, args.world)
                elif args.game_module_command == "enable":
                    data = enable_world_module(instance, args.world, args.module_id)
                elif args.game_module_command == "disable":
                    data = disable_world_module(instance, args.world, args.module_id)
                elif args.game_module_command == "set":
                    module_ids = [mid.strip() for mid in args.modules.split(",") if mid.strip()]
                    data = set_world_modules(instance, args.world, module_ids)
                else:
                    parser.error(f"Unknown game module command: {args.game_module_command}")
            else:
                parser.error(f"Unknown game command: {args.game_command}")
        except (ConfigurationError, WorldClientError, ModuleSettingError, AdminClientError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        emit(data, as_json=args.json or getattr(args, "command_json", False))
        return 0

    if args.command == "world":
        try:
            if args.world_command == "list":
                data = list_worlds(instance, active_world=fetch_active_world(instance))
            elif args.world_command == "create":
                data = create_world(instance, args.world_id, title=args.title, system=args.system)
            elif args.world_command == "edit":
                data = edit_world(instance, args.world_id, title=args.title, system=args.system)
            elif args.world_command == "delete":
                data = delete_world(instance, args.world_id, permanent=args.permanent, force=args.force)
            elif args.world_command == "run":
                data = configure_world(instance, args.world_id)
            elif args.world_command == "stop":
                data = stop_world(instance)
            else:
                parser.error(f"Unknown world command: {args.world_command}")
        except (ConfigurationError, ProcessError, WorldConfigError) as exc:
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
