"""Process/status helpers for local Foundry instances."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any

from .config import FoundryInstance

PM2 = "/home/linuxbrew/.linuxbrew/bin/pm2"
REAL_HOME = "/home/jon"


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
