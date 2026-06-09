"""Versioned Foundry instance configuration."""

from __future__ import annotations

import os
import shlex
import shutil
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


_VERSION_KEYS = ("install_dir", "data_dir", "url", "pm2_name", "mode")
_SHARED_KEYS = ("pm2_bin", "run_home", "projects_dir", "cache_dir", "backup_dir", "node_bin")
_ENV_VERSION_KEYS = {
    "install_dir": "INSTALL_DIR",
    "data_dir": "DATA_DIR",
    "url": "URL",
    "pm2_name": "PM2_NAME",
    "mode": "MODE",
}
_ENV_SHARED_KEYS = {
    "pm2_bin": "FOUNDRY_ADMIN_PM2_BIN",
    "run_home": "FOUNDRY_ADMIN_RUN_HOME",
    "projects_dir": "FOUNDRY_ADMIN_PROJECTS_DIR",
    "cache_dir": "FOUNDRY_ADMIN_CACHE_DIR",
    "backup_dir": "FOUNDRY_ADMIN_BACKUP_DIR",
    "node_bin": "FOUNDRY_ADMIN_NODE_BIN",
}


@dataclass(frozen=True)
class FoundryInstance:
    """Foundry instance paths, process metadata, and local capability settings."""

    version: str
    install_dir: Path
    data_dir: Path
    url: str
    pm2_name: str
    mode: str = "local"
    pm2_bin: str | None = None
    run_home: Path | None = None
    projects_dir: Path | None = None
    cache_dir: Path | None = None
    backup_dir: Path | None = None
    node_bin: str = "node"

    @property
    def options_path(self) -> Path:
        return self.data_dir / "Config" / "options.json"

    @property
    def worlds_dir(self) -> Path:
        return self.data_dir / "Data" / "worlds"

    @property
    def systems_dir(self) -> Path:
        return self.data_dir / "Data" / "systems"

    @property
    def modules_dir(self) -> Path:
        return self.data_dir / "Data" / "modules"

    def with_overrides(self, **kwargs: Any) -> "FoundryInstance":
        return replace(self, **{key: _coerce_instance_value(key, value) for key, value in kwargs.items()})

    def require_local(self, operation: str) -> None:
        if self.mode != "local":
            raise ConfigurationError(f"{operation} requires local Foundry filesystem/process access; instance mode is {self.mode!r}")

    def resolved_pm2_bin(self) -> str:
        if self.pm2_bin:
            return self.pm2_bin
        found = shutil.which("pm2")
        if found:
            return found
        raise ConfigurationError("PM2 binary not configured and 'pm2' was not found on PATH; set FOUNDRY_ADMIN_PM2_BIN")

    def resolved_run_home(self) -> str | None:
        return str(self.run_home) if self.run_home else os.environ.get("HOME")

    def resolved_projects_dir(self) -> Path:
        if self.projects_dir:
            return self.projects_dir
        return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "foundry-admin-cli" / "projects"

    def resolved_cache_dir(self) -> Path:
        if self.cache_dir:
            return self.cache_dir
        if os.environ.get("HERMES_HOME"):
            return Path(os.environ["HERMES_HOME"]) / "cache" / "foundry-admin-cli"
        return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "foundry-admin-cli"

    def resolved_backup_dir(self) -> Path:
        if self.backup_dir:
            return self.backup_dir
        if os.environ.get("HERMES_HOME"):
            return Path(os.environ["HERMES_HOME"]) / "backups" / "foundry-admin-cli"
        return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "foundry-admin-cli" / "backups"


def _coerce_path(value: Any) -> Path | None:
    if value is None or value == "":
        return None
    return Path(str(value)).expanduser()


def _coerce_instance_value(key: str, value: Any) -> Any:
    if key in {"install_dir", "data_dir", "run_home", "projects_dir", "cache_dir", "backup_dir"}:
        return _coerce_path(value)
    if key in {"pm2_bin", "node_bin", "url", "pm2_name", "mode", "version"} and value is not None:
        return str(value)
    return value


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            parts = shlex.split(value, comments=False, posix=True)
            value = parts[0] if len(parts) == 1 else value.strip('"\'')
        except ValueError:
            value = value.strip('"\'')
        values[key] = value
    return values


def _default_config_paths() -> list[Path]:
    paths = [Path("foundry-admin-cli.toml")]
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        paths.append(Path(xdg_config) / "foundry-admin-cli" / "config.toml")
    paths.append(Path.home() / ".config" / "foundry-admin-cli" / "config.toml")
    return paths


def _default_env_files() -> list[Path]:
    return [Path(".env")]


def _merge_toml(config: dict[str, Any], path: Path) -> None:
    if not path.exists():
        return
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    shared = data.get("shared", {})
    if isinstance(shared, dict):
        for key in _SHARED_KEYS:
            if key in shared:
                config["shared"][key] = shared[key]
    instances = data.get("instances", {})
    if isinstance(instances, dict):
        for version, values in instances.items():
            if not isinstance(values, dict):
                continue
            target = config["instances"].setdefault(str(version), {})
            for key in _VERSION_KEYS:
                if key in values:
                    target[key] = values[key]


def _merge_env(config: dict[str, Any], values: Mapping[str, str]) -> None:
    for key, env_key in _ENV_SHARED_KEYS.items():
        if env_key in values and values[env_key] != "":
            config["shared"][key] = values[env_key]
    for version in ("v13", "v14"):
        prefix = f"FOUNDRY_{version.upper()}_"
        target = config["instances"].setdefault(version, {})
        for key, suffix in _ENV_VERSION_KEYS.items():
            env_key = f"{prefix}{suffix}"
            if env_key in values and values[env_key] != "":
                target[key] = values[env_key]


def load_config(
    *,
    config_paths: list[Path] | None = None,
    env_files: list[Path] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Load non-secret runtime configuration with deterministic precedence."""

    config: dict[str, Any] = {"shared": {}, "instances": {}}
    for path in _default_config_paths() if config_paths is None else config_paths:
        _merge_toml(config, Path(path))
    env_file_values: dict[str, str] = {}
    for path in _default_env_files() if env_files is None else env_files:
        env_file_values.update(_parse_env_file(Path(path)))
    _merge_env(config, env_file_values)
    _merge_env(config, os.environ if environ is None else environ)
    return config


def apply_overrides(config: dict[str, Any], *, version: str = "v13", **kwargs: Any) -> dict[str, Any]:
    copied = {
        "shared": dict(config.get("shared", {})),
        "instances": {key: dict(value) for key, value in config.get("instances", {}).items()},
    }
    instance = copied["instances"].setdefault(version, {})
    for key, value in kwargs.items():
        if value is None:
            continue
        if key in _SHARED_KEYS:
            copied["shared"][key] = value
        elif key in _VERSION_KEYS:
            instance[key] = value
        else:
            raise ConfigurationError(f"Unknown configuration override: {key}")
    return copied


def get_instance(
    version: str,
    *,
    config: dict[str, Any] | None = None,
    config_paths: list[Path] | None = None,
    env_files: list[Path] | None = None,
) -> FoundryInstance:
    """Return configured instance or raise a CLI-friendly error."""

    loaded = config if config is not None else load_config(config_paths=config_paths, env_files=env_files)
    instances = loaded.get("instances", {})
    if version not in instances:
        valid = ", ".join(sorted(instances)) or "none configured"
        raise ValueError(f"Unknown Foundry version '{version}'. Expected one of: {valid}")
    data = dict(instances[version])
    missing = [key for key in ("install_dir", "data_dir", "url", "pm2_name") if not data.get(key)]
    if missing:
        keys = ", ".join(f"FOUNDRY_{version.upper()}_{_ENV_VERSION_KEYS[key]}" for key in missing)
        raise ConfigurationError(f"Missing required configuration for {version}: {keys}")
    shared = dict(loaded.get("shared", {}))
    values: dict[str, Any] = {
        "version": version,
        "install_dir": data["install_dir"],
        "data_dir": data["data_dir"],
        "url": data["url"],
        "pm2_name": data["pm2_name"],
        "mode": data.get("mode", "local"),
        **{key: shared.get(key) for key in _SHARED_KEYS},
    }
    if values["node_bin"] is None:
        values["node_bin"] = "node"
    coerced = {key: _coerce_instance_value(key, value) for key, value in values.items()}
    return FoundryInstance(**coerced)
