"""Process/status helpers for local Foundry instances."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from datetime import date
from html import unescape
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.error import URLError

from .config import FoundryInstance

PM2 = "/home/linuxbrew/.linuxbrew/bin/pm2"
REAL_HOME = "/home/jon"


class ProcessError(RuntimeError):
    """Raised for process/lifecycle failures safe to show in CLI output."""


@dataclass(frozen=True)
class ProcessStatus:
    version: str
    pm2_name: str
    status: str
    pid: int | None
    port: int | None
    configured_world: str | None
    active_world: str | None
    memory_mb: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "pm2_name": self.pm2_name,
            "status": self.status,
            "pid": self.pid,
            "port": self.port,
            "configured_world": self.configured_world,
            "active_world": self.active_world,
            "memory_mb": self.memory_mb,
        }


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def infer_active_world_from_html_title(html: str, worlds_dir: Path) -> str | None:
    """Infer the active world id by matching the rendered page title to world.json titles."""

    match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = unescape(match.group(1).strip())
    if not title or title == "Foundry Virtual Tabletop":
        return None

    for manifest in worlds_dir.glob("*/world.json"):
        try:
            data = json.loads(manifest.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("title") == title:
            return data.get("id") or manifest.parent.name
    return None


def fetch_active_world(instance: FoundryInstance) -> str | None:
    """Return the world currently being served, without requiring authentication."""

    try:
        with urllib.request.urlopen(instance.url, timeout=5) as response:
            html = response.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    return infer_active_world_from_html_title(html, instance.worlds_dir)


def run_pm2(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": REAL_HOME}
    return subprocess.run(
        [PM2, *args],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=30,
    )


def get_status(instance: FoundryInstance) -> ProcessStatus:
    options = read_json(instance.options_path)
    port = options.get("port")
    configured_world = options.get("world")
    active_world = fetch_active_world(instance)
    result = run_pm2("jlist")
    if result.returncode != 0:
        return ProcessStatus(
            version=instance.version,
            pm2_name=instance.pm2_name,
            status="pm2-unreachable",
            pid=None,
            port=port,
            configured_world=configured_world,
            active_world=active_world,
            memory_mb=None,
        )

    try:
        processes = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        processes = []

    proc = next((item for item in processes if item.get("name") == instance.pm2_name), None)

    if proc is None:
        return ProcessStatus(
            version=instance.version,
            pm2_name=instance.pm2_name,
            status="not-in-pm2",
            pid=None,
            port=port,
            configured_world=configured_world,
            active_world=active_world,
            memory_mb=None,
        )

    memory = proc.get("monit", {}).get("memory")
    memory_mb = int(memory / (1024 * 1024)) if isinstance(memory, int | float) else None
    return ProcessStatus(
        version=instance.version,
        pm2_name=instance.pm2_name,
        status=proc.get("pm2_env", {}).get("status", "unknown"),
        pid=proc.get("pid"),
        port=port,
        configured_world=configured_world,
        active_world=active_world,
        memory_mb=memory_mb,
    )


def wait_until_ready(
    instance: FoundryInstance,
    *,
    timeout_seconds: float = 60.0,
    interval_seconds: float = 1.0,
) -> dict[str, Any]:
    """Wait until Foundry responds to unauthenticated GET /."""

    if timeout_seconds <= 0:
        raise ProcessError("timeout must be positive")
    if interval_seconds <= 0:
        raise ProcessError("interval must be positive")
    deadline = monotonic() + timeout_seconds
    attempts = 0
    last_error = ""
    while True:
        attempts += 1
        try:
            with urllib.request.urlopen(instance.url, timeout=5) as response:
                response.read()
            return {
                "version": instance.version,
                "url": instance.url,
                "ready": True,
                "attempts": attempts,
            }
        except (OSError, URLError) as exc:
            last_error = str(exc)
        if monotonic() >= deadline:
            raise ProcessError(f"Timed out waiting for Foundry at {instance.url}: {last_error}")
        sleep(interval_seconds)


def restart_instance(instance: FoundryInstance, *, timeout_seconds: float = 60.0) -> dict[str, Any]:
    """Restart the configured PM2 process and wait for Foundry readiness."""

    result = run_pm2("restart", instance.pm2_name)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        suffix = f": {stderr}" if stderr else ""
        raise ProcessError(f"PM2 restart failed for {instance.pm2_name}{suffix}")
    ready = wait_until_ready(instance, timeout_seconds=timeout_seconds)
    return {
        "version": instance.version,
        "pm2_name": instance.pm2_name,
        "restarted": True,
        **ready,
    }


def _tail_lines(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:] if lines > 0 else []


def collect_logs(
    instance: FoundryInstance,
    *,
    lines: int = 50,
    contains: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Tail today's debug and error logs, optionally filtering matching lines."""

    if lines < 1:
        raise ProcessError("--lines must be at least 1")
    current_date = today or date.today()
    log_dir = instance.data_dir / "Logs"
    paths = {
        "debug": log_dir / f"debug.{current_date.isoformat()}.log",
        "error": log_dir / f"error.{current_date.isoformat()}.log",
    }
    output: dict[str, Any] = {
        "version": instance.version,
        "debug_path": str(paths["debug"]),
        "error_path": str(paths["error"]),
    }
    for name, path in paths.items():
        log_lines = _tail_lines(path, lines)
        if contains:
            log_lines = [line for line in log_lines if contains in line]
        output[name] = log_lines
    return output
