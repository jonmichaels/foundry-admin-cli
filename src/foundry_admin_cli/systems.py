"""System package discovery and lifecycle helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.request
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .config import FoundryInstance
from .packages import PackageOperationError, validate_manifest_url

SYSTEM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SystemPackageError(RuntimeError):
    """Raised when a system package operation is unsafe or invalid."""


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _validate_system_id(system_id: str) -> None:
    if not SYSTEM_ID_RE.fullmatch(system_id):
        raise SystemPackageError(f"Invalid system id: {system_id}")


def _literal_system_dir(instance: FoundryInstance, system_id: str) -> Path:
    _validate_system_id(system_id)
    system_dir = instance.systems_dir / system_id
    systems_root = instance.systems_dir.resolve()
    if system_dir.parent.resolve() != systems_root:
        raise SystemPackageError(f"Invalid system id: {system_id}")
    if system_dir.is_symlink():
        raise SystemPackageError(f"Refusing to remove symlinked system directory: {system_id}")
    return system_dir


def _system_manifest_path(instance: FoundryInstance, system_id: str) -> Path:
    system_dir = _literal_system_dir(instance, system_id)
    manifest = (system_dir / "system.json").resolve()
    if not manifest.is_relative_to(instance.systems_dir.resolve()):
        raise SystemPackageError(f"Invalid system id: {system_id}")
    return manifest


def _read_system_manifest(instance: FoundryInstance, system_id: str) -> tuple[Path, dict[str, Any]]:
    manifest_path = _system_manifest_path(instance, system_id)
    if not manifest_path.exists():
        raise SystemPackageError(f"System not found: {system_id}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemPackageError(f"Cannot read system manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemPackageError("system.json root must be an object")
    return manifest_path, data


def _world_dependencies(instance: FoundryInstance) -> dict[str, list[str]]:
    dependencies: dict[str, list[str]] = {}
    if not instance.worlds_dir.exists():
        return dependencies
    for manifest_path in sorted(instance.worlds_dir.glob("*/world.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        system_id = data.get("system")
        if isinstance(system_id, str) and system_id:
            raw_world_id = data.get("id")
            world_id = raw_world_id if isinstance(raw_world_id, str) else manifest_path.parent.name
            dependencies.setdefault(system_id, []).append(world_id)
    return dependencies


def list_systems(instance: FoundryInstance) -> list[dict[str, Any]]:
    """Enumerate installed systems from Data/systems/*/system.json."""

    if not instance.systems_dir.exists():
        return []
    worlds_by_system = _world_dependencies(instance)
    systems: list[dict[str, Any]] = []
    for system_dir in sorted(p for p in instance.systems_dir.iterdir() if p.is_dir() or p.is_symlink()):
        system_id = system_dir.name
        manifest_path = system_dir / "system.json"
        base = {
            "id": system_id,
            "directory_id": system_id,
            "manifest_id": None,
            "title": None,
            "version": None,
            "compatibility": {},
            "path": str(system_dir),
            "manifest": None,
            "valid": False,
            "worlds": worlds_by_system.get(system_id, []),
        }
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (JSONDecodeError, UnicodeDecodeError):
            systems.append({**base, "error": "Invalid JSON in system.json"})
            continue
        except OSError as exc:
            systems.append({**base, "error": str(exc)})
            continue
        if not isinstance(data, dict):
            systems.append({**base, "error": "system.json root must be an object"})
            continue
        raw_manifest_id = data.get("id")
        if raw_manifest_id is not None and not isinstance(raw_manifest_id, str):
            systems.append({**base, "error": "system.json id must be a string"})
            continue
        manifest_id = raw_manifest_id or system_id
        systems.append(
            {
                **base,
                "id": manifest_id,
                "manifest_id": raw_manifest_id,
                "id_matches_directory": manifest_id == system_id,
                "title": data.get("title"),
                "version": data.get("version"),
                "compatibility": data.get("compatibility") or {},
                "manifest": data.get("manifest"),
                "valid": True,
                "worlds": sorted(set(worlds_by_system.get(system_id, []) + worlds_by_system.get(manifest_id, []))),
            }
        )
    return systems


def _fetch_manifest(url: str) -> dict[str, Any]:
    try:
        validate_manifest_url(url)
    except PackageOperationError as exc:
        raise SystemPackageError(str(exc)) from exc
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except OSError as exc:
        raise SystemPackageError(f"Could not fetch system manifest: {exc}") from exc
    try:
        data = json.loads(raw)
    except JSONDecodeError as exc:
        raise SystemPackageError("Remote system manifest was not JSON") from exc
    if not isinstance(data, dict):
        raise SystemPackageError("Remote system manifest root must be an object")
    return data


def _manifest_matches(local: dict[str, Any], remote: dict[str, Any]) -> bool:
    return local.get("version") == remote.get("version") and (local.get("compatibility") or {}) == (
        remote.get("compatibility") or {}
    )


def update_system(
    instance: FoundryInstance,
    system_id: str,
    *,
    client: Any,
    fetch_manifest: Any = _fetch_manifest,
) -> dict[str, Any]:
    """Update an installed system by comparing and re-running Foundry installPackage."""

    _, data = _read_system_manifest(instance, system_id)
    manifest = data.get("manifest")
    if not isinstance(manifest, str) or not manifest:
        raise SystemPackageError(f"No manifest URL recorded for system: {system_id}")
    remote = fetch_manifest(manifest)
    current_version = data.get("version")
    available_version = remote.get("version")
    if _manifest_matches(data, remote):
        return {
            "version": instance.version,
            "system": system_id,
            "manifest": manifest,
            "changed": False,
            "current_version": current_version,
            "available_version": available_version,
        }
    try:
        setup_result = client.setup_action(
            "installPackage",
            {"type": "system", "id": system_id, "manifest": manifest, "force": True},
        )
    except PackageOperationError as exc:
        raise SystemPackageError(str(exc)) from exc
    return {
        "version": instance.version,
        "system": system_id,
        "manifest": manifest,
        "changed": True,
        "current_version": current_version,
        "available_version": available_version,
        "setup_result": setup_result,
    }


def _unique_archive_dir(base_dir: Path, system_id: str) -> Path:
    for attempt in range(100):
        suffix = f"-{attempt}" if attempt else ""
        candidate = base_dir / f"{system_id}{suffix}"
        if not candidate.exists():
            return candidate
    raise SystemPackageError("Unable to create unique archive path")


def remove_system(
    instance: FoundryInstance,
    system_id: str,
    *,
    permanent: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Archive a system by default, or permanently remove with explicit force."""

    system_dir = _literal_system_dir(instance, system_id)
    if not (system_dir / "system.json").exists():
        raise SystemPackageError(f"System not found: {system_id}")
    _, manifest_data = _read_system_manifest(instance, system_id)
    raw_manifest_id = manifest_data.get("id")
    manifest_id = raw_manifest_id if isinstance(raw_manifest_id, str) else system_id
    world_dependencies = _world_dependencies(instance)
    dependencies = sorted(set(world_dependencies.get(system_id, []) + world_dependencies.get(manifest_id, [])))
    if dependencies and not force:
        raise SystemPackageError(f"System {system_id} is used by worlds: {', '.join(dependencies)}")
    if permanent and not force:
        raise SystemPackageError("Permanent remove requires --force")
    if permanent:
        shutil.rmtree(system_dir)
        return {
            "version": instance.version,
            "system": system_id,
            "changed": True,
            "removed": True,
            "archive_path": None,
        }

    archive_root = _hermes_home() / "backups" / "foundry-admin-cli" / instance.version / "systems"
    archive_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(archive_root, 0o700)
    archive_path = _unique_archive_dir(archive_root, system_id)
    shutil.move(str(system_dir), str(archive_path))
    return {
        "version": instance.version,
        "system": system_id,
        "changed": True,
        "removed": False,
        "archive_path": str(archive_path),
    }
