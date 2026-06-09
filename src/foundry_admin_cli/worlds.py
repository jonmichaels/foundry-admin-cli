"""World discovery and lifecycle helpers."""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from .config import FoundryInstance


def _configured_world(instance: FoundryInstance) -> str | None:
    if not instance.options_path.exists():
        return None
    try:
        options = json.loads(instance.options_path.read_text())
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
