"""Process/status helpers for local Foundry instances."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
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
    world: str | None
    memory_mb: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "pm2_name": self.pm2_name,
            "status": self.status,
            "pid": self.pid,
            "port": self.port,
            "world": self.world,
            "memory_mb": self.memory_mb,
        }


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


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
    result = run_pm2("jlist")
    if result.returncode != 0:
        return ProcessStatus(
            version=instance.version,
            pm2_name=instance.pm2_name,
            status="pm2-unreachable",
            pid=None,
            port=None,
            world=None,
            memory_mb=None,
        )

    try:
        processes = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        processes = []

    proc = next((item for item in processes if item.get("name") == instance.pm2_name), None)
    options = read_json(instance.options_path)
    port = options.get("port")
    world = options.get("world")

    if proc is None:
        return ProcessStatus(
            version=instance.version,
            pm2_name=instance.pm2_name,
            status="not-in-pm2",
            pid=None,
            port=port,
            world=world,
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
        world=world,
        memory_mb=memory_mb,
    )
