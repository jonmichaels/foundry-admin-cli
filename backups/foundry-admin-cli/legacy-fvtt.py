#!/usr/bin/env python3
"""
Foundry VTT Admin CLI — agent-facing Foundry management without browser interaction.

Usage:
  fvtt status                    Show Foundry server status
  fvtt restart [v13|v14]         Restart Foundry instance
  fvtt logs [v13|v14] [filter]   Tail error/debug logs
  fvtt modules list [v13|v14]    List installed modules
  fvtt modules enable <id> [v13|v14]  Symlink module to Data/modules/
  fvtt modules disable <id> [v13|v14] Remove module symlink
  fvtt world active [v13|v14]    Show/set auto-load world
  fvtt config [get|set] <key> [value]  Read/write options.json
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Config ──────────────────────────────────────────────
PM2 = "/home/linuxbrew/.linuxbrew/bin/pm2"
HOME = os.environ.get("REAL_HOME", "/home/jon")
FOUNDRY = {
    "v13": {
        "pm2_name": "foundry-v13",
        "data_dir": f"{HOME}/foundryuserdata",
        "install_dir": f"{HOME}/foundry",
    },
    "v14": {
        "pm2_name": "foundry-v14",
        "data_dir": f"{HOME}/foundryuserdata14",
        "install_dir": f"{HOME}/foundry14",
    },
}

DEFAULT_VERSION = "v13"


def pm2(*args, _input=None):
    """Run pm2 command with correct HOME."""
    env = {**os.environ, "HOME": HOME}
    result = subprocess.run(
        [PM2, *args],
        capture_output=True, text=True, env=env,
        input=_input, timeout=30
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def get_options(version):
    """Read options.json for a Foundry instance."""
    path = Path(FOUNDRY[version]["data_dir"]) / "Config" / "options.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def set_options(version, updates):
    """Update options.json for a Foundry instance."""
    path = Path(FOUNDRY[version]["data_dir"]) / "Config" / "options.json"
    current = {}
    if path.exists():
        with open(path) as f:
            current = json.load(f)
    current.update(updates)
    with open(path, "w") as f:
        json.dump(current, f, indent=2)
    return current


def get_modules_dir(version):
    """Get the Data/modules/ directory path."""
    return Path(FOUNDRY[version]["data_dir"]) / "Data" / "modules"


# ── Commands ────────────────────────────────────────────

def cmd_status(version=None):
    """Show status of Foundry instances."""
    version = version or DEFAULT_VERSION
    if version == "all":
        for v in FOUNDRY:
            _show_status(v)
    else:
        _show_status(version)


def _show_status(version):
    cfg = FOUNDRY[version]
    stdout, stderr, rc = pm2("jlist")
    try:
        processes = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"[{version}] pm2 unreachable")
        return

    proc = next((p for p in processes if p.get("name") == cfg["pm2_name"]), None)
    if not proc:
        print(f"[{version}] NOT IN PM2")
        return

    pid = proc.get("pid")
    status = proc.get("pm2_env", {}).get("status", "unknown")
    uptime = proc.get("pm2_env", {}).get("pm_uptime", 0)
    restarts = proc.get("pm2_env", {}).get("unstable_restarts", 0)
    memory = proc.get("monit", {}).get("memory", 0) / (1024 * 1024)

    options = get_options(version)
    world = options.get("world", "none")
    port = options.get("port", "30000")

    print(f"  {version}: {status} | PID {pid} | port {port} | world: {world}")
    print(f"  uptime: {uptime}s | restarts: {restarts} | mem: {memory:.0f}MB")


def cmd_restart(version=None):
    """Restart a Foundry instance via pm2."""
    version = version or DEFAULT_VERSION
    name = FOUNDRY[version]["pm2_name"]
    stdout, stderr, rc = pm2("restart", name)
    print(stdout or stderr)


def cmd_logs(version=None, filter_text=None, lines=50):
    """Show Foundry logs."""
    version = version or DEFAULT_VERSION
    data_dir = FOUNDRY[version]["data_dir"]

    logs = sorted(
        Path(data_dir).glob("Logs/debug.*.log"),
        key=lambda p: p.stat().st_mtime, reverse=True
    )

    if not logs:
        print(f"No debug logs found for {version}")
        return

    latest = logs[0]
    with open(latest) as f:
        log_lines = f.readlines()

    if filter_text:
        log_lines = [l for l in log_lines if filter_text.lower() in l.lower()]

    for line in log_lines[-lines:]:
        try:
            entry = json.loads(line)
            ts = entry.get("timestamp", "")[11:19] if "timestamp" in entry else ""
            msg = entry.get("message", line.strip())
            print(f"[{ts}] {msg}")
        except json.JSONDecodeError:
            print(line.rstrip())


def cmd_modules_list(version=None):
    """List installed modules."""
    version = version or DEFAULT_VERSION
    modules_dir = get_modules_dir(version)

    if not modules_dir.exists():
        print(f"Modules directory not found: {modules_dir}")
        return

    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        manifest = mod_dir / "module.json"
        if manifest.exists():
            try:
                with open(manifest) as f:
                    data = json.load(f)
                is_symlink = mod_dir.is_symlink()
                marker = "→" if is_symlink else " "
                print(f"  {marker} {data.get('id', mod_dir.name):40} v{data.get('version', '?')}")
            except (json.JSONDecodeError, KeyError):
                print(f"    {mod_dir.name} (error reading manifest)")
        else:
            print(f"    {mod_dir.name} (no module.json)")


def cmd_modules_enable(module_id, version=None):
    """Enable a module by symlinking from projects/ to Data/modules/."""
    version = version or DEFAULT_VERSION
    modules_dir = get_modules_dir(version)

    # Find module source in ~/projects/
    projects = Path(f"{HOME}/projects")
    source = None
    for candidate in projects.rglob(f"*{module_id}*/module.json"):
        with open(candidate) as f:
            try:
                data = json.load(f)
                if data.get("id") == module_id:
                    source = candidate.parent
                    break
            except json.JSONDecodeError:
                continue

    if not source:
        print(f"Module '{module_id}' not found in ~/projects/")
        return

    target = modules_dir / module_id
    if target.exists():
        print(f"Module '{module_id}' already exists at {target}")
        return

    target.symlink_to(source)
    print(f"Enabled: {source} → {target}")


def cmd_modules_disable(module_id, version=None):
    """Disable a module by removing symlink."""
    version = version or DEFAULT_VERSION
    modules_dir = get_modules_dir(version)
    target = modules_dir / module_id

    if not target.exists():
        print(f"Module '{module_id}' not found")
        return

    if target.is_symlink():
        target.unlink()
        print(f"Disabled (symlink removed): {target}")
    else:
        print(f"Module '{module_id}' is not a symlink — refusing to delete. Remove manually.")


def cmd_world(version=None, world_name=None):
    """Show or set the auto-load world."""
    version = version or DEFAULT_VERSION
    options = get_options(version)

    if world_name:
        set_options(version, {"world": world_name})
        print(f"Set auto-load world to: {world_name}")
    else:
        current = options.get("world", "none")
        print(f"Auto-load world: {current}")


def cmd_config(version=None, action="get", key=None, value=None):
    """Read or write options.json."""
    version = version or DEFAULT_VERSION
    options = get_options(version)

    if action == "get":
        if key:
            print(f"{key}: {options.get(key, 'NOT SET')}")
        else:
            for k, v in sorted(options.items()):
                if isinstance(v, str) and len(str(v)) > 60:
                    v = str(v)[:57] + "..."
                print(f"  {k}: {v}")
    elif action == "set":
        if not key or value is None:
            print("Usage: fvtt config set <key> <value>")
            return
        # Try to parse value as JSON, fall back to string
        try:
            val = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            val = value
        set_options(version, {key: val})
        print(f"Set {key} = {val}")


def cmd_mcp_status():
    """Check MCP bridge connection status."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", 31415))
        s.close()
        print("MCP Server: LISTENING on :31415")
    except (socket.error, OSError):
        print("MCP Server: NOT LISTENING on :31415")

    # Check if Foundry module is connected
    data_dir = FOUNDRY[DEFAULT_VERSION]["data_dir"]
    log_files = sorted(
        Path(data_dir).glob("Logs/debug.*.log"),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    if log_files:
        with open(log_files[0]) as f:
            content = f.read()
        if "Starting MCP bridge" in content or "Bridge started" in content:
            print("Foundry Module: CONNECTED")
        else:
            print("Foundry Module: NOT CONNECTED (no bridge start in logs)")


# ── Main ─────────────────────────────────────────────────

HELP = """
fvtt — Foundry VTT Admin CLI

Commands:
  status [v13|v14|all]          Show server status
  restart [v13|v14]             Restart Foundry via pm2
  logs [v13|v14] [filter]       Tail debug logs
  modules list [v13|v14]        List installed modules
  modules enable <id> [v13|v14] Enable module (symlink from projects/)
  modules disable <id> [v13|v14] Disable module (remove symlink)
  world [v13|v14] [name]        Show/set auto-load world
  config [v13|v14] [key]        Show config
  config set <key> <val> [v13|v14]  Set config value
  mcp                           Show MCP bridge connection status
  port [v13|v14]                Show listening port
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "-h", "--help"):
        print(HELP)
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "status":
        version = args[0] if args else None
        cmd_status(version)
    elif cmd == "restart":
        version = args[0] if args else None
        cmd_restart(version)
    elif cmd == "logs":
        version = None
        filter_text = None
        if args and args[0] in FOUNDRY:
            version = args[0]
            args = args[1:]
        if args:
            filter_text = args[0]
        cmd_logs(version, filter_text)
    elif cmd == "modules":
        if not args:
            print("Usage: fvtt modules <list|enable|disable> ...")
            return
        sub = args[0]
        if sub == "list":
            version = args[1] if len(args) > 1 else None
            cmd_modules_list(version)
        elif sub == "enable":
            if len(args) < 2:
                print("Usage: fvtt modules enable <module_id> [version]")
                return
            version = args[2] if len(args) > 2 else None
            cmd_modules_enable(args[1], version)
        elif sub == "disable":
            if len(args) < 2:
                print("Usage: fvtt modules disable <module_id> [version]")
                return
            version = args[2] if len(args) > 2 else None
            cmd_modules_disable(args[1], version)
    elif cmd == "world":
        version = None
        world = None
        non_flag = [a for a in args if not a.startswith("-")]
        if non_flag and non_flag[0] in FOUNDRY:
            version = non_flag[0]
            non_flag = non_flag[1:]
        if non_flag:
            world = non_flag[0]
        cmd_world(version, world)
    elif cmd == "config":
        if not args:
            cmd_config()
            return
        if args[0] == "set":
            if len(args) < 3:
                print("Usage: fvtt config set <key> <value> [version]")
                return
            version = args[3] if len(args) > 3 else None
            cmd_config(version, "set", args[1], args[2])
        else:
            version = args[1] if len(args) > 1 and args[1] in FOUNDRY else None
            key = args[0] if args[0] not in FOUNDRY else (args[1] if len(args) > 1 else None)
            cmd_config(version, "get", key)
    elif cmd == "mcp":
        cmd_mcp_status()
    elif cmd == "port":
        version = args[0] if args else None
        version = version or DEFAULT_VERSION
        options = get_options(version)
        print(f"{version}: port {options.get('port', '30000')}")
    else:
        print(f"Unknown command: {cmd}")
        print("Use 'fvtt help' for available commands.")


if __name__ == "__main__":
    main()
