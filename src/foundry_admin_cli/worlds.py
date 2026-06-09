"""World discovery and lifecycle helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .config import FoundryInstance

WORLD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _configured_world(instance: FoundryInstance) -> str | None:
    if not instance.options_path.exists():
        return None
    try:
        options = json.loads(instance.options_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, UnicodeDecodeError):
        return None
    world = options.get("world")
    return world if isinstance(world, str) and world else None


def list_worlds(instance: FoundryInstance, *, active_world: str | None = None) -> list[dict[str, Any]]:
    """Enumerate installed worlds from Data/worlds/*/world.json."""

    if not instance.worlds_dir.exists():
        return []

    configured_world = _configured_world(instance)
    worlds: list[dict[str, Any]] = []
    for world_dir in sorted(p for p in instance.worlds_dir.iterdir() if p.is_dir()):
        world_id = world_dir.name
        world_json = world_dir / "world.json"
        base = {
            "id": world_id,
            "directory_id": world_id,
            "manifest_id": None,
            "title": None,
            "system": None,
            "compatibility": {},
            "path": str(world_dir),
            "active": world_id == active_world,
            "configured": world_id == configured_world,
        }
        try:
            data = json.loads(world_json.read_text())
        except (JSONDecodeError, UnicodeDecodeError):
            worlds.append({**base, "valid": False, "error": "Invalid JSON in world.json"})
            continue
        except OSError as exc:
            worlds.append({**base, "valid": False, "error": str(exc)})
            continue

        if not isinstance(data, dict):
            worlds.append({**base, "valid": False, "error": "world.json root must be an object"})
            continue
        raw_manifest_id = data.get("id")
        if raw_manifest_id is not None and not isinstance(raw_manifest_id, str):
            worlds.append({**base, "valid": False, "error": "world.json id must be a string"})
            continue
        manifest_id = raw_manifest_id or world_id
        id_values = {world_id, manifest_id}
        worlds.append(
            {
                **base,
                "id": manifest_id,
                "manifest_id": raw_manifest_id,
                "id_matches_directory": manifest_id == world_id,
                "active": active_world in id_values,
                "configured": configured_world in id_values,
                "title": data.get("title"),
                "system": data.get("system"),
                "compatibility": data.get("compatibility") or {},
                "valid": True,
            }
        )
    return worlds


class WorldConfigError(RuntimeError):
    """Raised when a world configuration mutation is unsafe or invalid."""


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _unique_backup_path(backup_dir: Path) -> Path:
    for attempt in range(100):
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        suffix = f"-{attempt}" if attempt else ""
        backup_path = backup_dir / f"{timestamp}{suffix}.json"
        try:
            fd = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        return backup_path
    raise WorldConfigError("Unable to create unique backup path")


def _backup_file(path: Path, instance: FoundryInstance) -> Path:
    backup_dir = _hermes_home() / "backups" / "foundry-admin-cli" / instance.version / path.name
    backup_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    backup_path = _unique_backup_path(backup_dir)
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(backup_path, 0o600)
    return backup_path


def _read_options(instance: FoundryInstance) -> dict[str, Any]:
    if not instance.options_path.exists():
        raise WorldConfigError(f"Missing options file: {instance.options_path}")
    try:
        data = json.loads(instance.options_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, UnicodeDecodeError) as exc:
        raise WorldConfigError(f"Cannot read options file: {exc}") from exc
    if not isinstance(data, dict):
        raise WorldConfigError("options.json root must be an object")
    return data


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _write_options(instance: FoundryInstance, options: dict[str, Any]) -> Path:
    _backup_file(instance.options_path, instance)
    _atomic_write_json(instance.options_path, options)
    return instance.options_path


def _validate_world_id(world_id: str) -> None:
    if not WORLD_ID_RE.fullmatch(world_id):
        raise WorldConfigError(f"Invalid world id: {world_id}")


def _world_manifest_path(instance: FoundryInstance, world_id: str) -> Path:
    _validate_world_id(world_id)
    worlds_root = instance.worlds_dir.resolve()
    manifest = (instance.worlds_dir / world_id / "world.json").resolve()
    if not manifest.is_relative_to(worlds_root):
        raise WorldConfigError(f"Invalid world id: {world_id}")
    return manifest


def _world_exists(instance: FoundryInstance, world_id: str) -> bool:
    return _world_manifest_path(instance, world_id).exists()


def _read_world_manifest(instance: FoundryInstance, world_id: str) -> tuple[Path, dict[str, Any]]:
    manifest_path = _world_manifest_path(instance, world_id)
    if not manifest_path.exists():
        raise WorldConfigError(f"World not found: {world_id}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, UnicodeDecodeError) as exc:
        raise WorldConfigError(f"Cannot read world manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise WorldConfigError("world.json root must be an object")
    return manifest_path, data


def _write_manifest(instance: FoundryInstance, manifest_path: Path, data: dict[str, Any]) -> Path:
    _backup_file(manifest_path, instance)
    _atomic_write_json(manifest_path, data)
    return manifest_path


def configure_world(instance: FoundryInstance, world_id: str) -> dict[str, Any]:
    """Set Config/options.json world to an installed world id."""

    if not _world_exists(instance, world_id):
        raise WorldConfigError(f"World not found: {world_id}")

    options = _read_options(instance)
    if options.get("world") == world_id:
        return {"version": instance.version, "world": world_id, "changed": False, "restart_required": False}

    previous = options.get("world")
    options["world"] = world_id
    _write_options(instance, options)
    return {
        "version": instance.version,
        "world": world_id,
        "previous_world": previous,
        "changed": True,
        "restart_required": True,
    }


def stop_world(instance: FoundryInstance) -> dict[str, Any]:
    """Clear Config/options.json world so Foundry starts in setup mode after restart."""

    options = _read_options(instance)
    if options.get("world") is None:
        return {"version": instance.version, "world": None, "changed": False, "restart_required": False}

    previous = options.get("world")
    options["world"] = None
    _write_options(instance, options)
    return {
        "version": instance.version,
        "world": None,
        "previous_world": previous,
        "changed": True,
        "restart_required": True,
    }


def _world_dir(instance: FoundryInstance, world_id: str) -> Path:
    return _world_manifest_path(instance, world_id).parent


def _unique_archive_dir(base_dir: Path, world_id: str) -> Path:
    for attempt in range(100):
        suffix = f"-{attempt}" if attempt else ""
        candidate = base_dir / f"{world_id}{suffix}"
        if not candidate.exists():
            return candidate
    raise WorldConfigError("Unable to create unique archive path")


def _literal_world_dir(instance: FoundryInstance, world_id: str) -> Path:
    _validate_world_id(world_id)
    world_dir = instance.worlds_dir / world_id
    worlds_root = instance.worlds_dir.resolve()
    parent = world_dir.parent.resolve()
    if parent != worlds_root:
        raise WorldConfigError(f"Invalid world id: {world_id}")
    if world_dir.is_symlink():
        raise WorldConfigError(f"Refusing to delete symlinked world directory: {world_id}")
    return world_dir


def delete_world(
    instance: FoundryInstance,
    world_id: str,
    *,
    permanent: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Archive a world by default, or permanently delete with explicit force."""

    world_dir = _literal_world_dir(instance, world_id)
    manifest_path = world_dir / "world.json"
    if not manifest_path.exists():
        raise WorldConfigError(f"World not found: {world_id}")
    _, manifest = _read_world_manifest(instance, world_id)
    manifest_id = manifest.get("id") if isinstance(manifest.get("id"), str) else world_id
    configured_ids = {world_id, manifest_id}
    if _configured_world(instance) in configured_ids and not force:
        raise WorldConfigError("Refusing to delete configured world without --force")
    if permanent and not force:
        raise WorldConfigError("Permanent delete requires --force")

    if permanent:
        shutil.rmtree(world_dir)
        return {
            "version": instance.version,
            "world": world_id,
            "changed": True,
            "deleted": True,
            "archive_path": None,
        }

    archive_root = _hermes_home() / "backups" / "foundry-admin-cli" / instance.version / "worlds"
    archive_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(archive_root, 0o700)
    archive_path = _unique_archive_dir(archive_root, world_id)
    shutil.move(str(world_dir), str(archive_path))
    return {
        "version": instance.version,
        "world": world_id,
        "changed": True,
        "deleted": False,
        "archive_path": str(archive_path),
    }


def edit_world(
    instance: FoundryInstance,
    world_id: str,
    *,
    title: str | None = None,
    system: str | None = None,
) -> dict[str, Any]:
    """Edit supported world.json fields with a backup."""

    updates = {key: value for key, value in {"title": title, "system": system}.items() if value is not None}
    for key, value in updates.items():
        if not value.strip():
            raise WorldConfigError(f"{key} cannot be empty")
    if not updates:
        raise WorldConfigError("No fields provided to update")

    manifest_path, manifest = _read_world_manifest(instance, world_id)
    changed_fields: dict[str, Any] = {}
    for key, value in updates.items():
        if manifest.get(key) != value:
            manifest[key] = value
            changed_fields[key] = value

    if not changed_fields:
        return {"version": instance.version, "world": world_id, "changed": False, "fields": []}

    _write_manifest(instance, manifest_path, manifest)
    return {
        "version": instance.version,
        "world": world_id,
        "changed": True,
        "fields": sorted(changed_fields),
        "path": str(manifest_path),
    }
