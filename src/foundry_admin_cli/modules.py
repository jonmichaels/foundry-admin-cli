"""Module package discovery and lifecycle helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import urllib.request
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .config import FoundryInstance
from .packages import PackageOperationError, validate_manifest_url

MODULE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ModulePackageError(RuntimeError):
    """Raised when a module package operation is unsafe or invalid."""


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _validate_module_id(module_id: str) -> None:
    if not MODULE_ID_RE.fullmatch(module_id):
        raise ModulePackageError(f"Invalid module id: {module_id}")


def _literal_module_dir(instance: FoundryInstance, module_id: str) -> Path:
    _validate_module_id(module_id)
    module_dir = instance.modules_dir / module_id
    modules_root = instance.modules_dir.resolve()
    if module_dir.parent.resolve() != modules_root:
        raise ModulePackageError(f"Invalid module id: {module_id}")
    return module_dir


def _module_manifest_path(instance: FoundryInstance, module_id: str) -> Path:
    module_dir = _literal_module_dir(instance, module_id)
    manifest = (module_dir / "module.json").resolve()
    modules_root = instance.modules_dir.resolve()
    if not manifest.is_relative_to(modules_root) and not module_dir.is_symlink():
        raise ModulePackageError(f"Invalid module id: {module_id}")
    return manifest


def _read_module_manifest(instance: FoundryInstance, module_id: str) -> tuple[Path, dict[str, Any]]:
    manifest_path = _module_manifest_path(instance, module_id)
    if not manifest_path.exists():
        raise ModulePackageError(f"Module not found: {module_id}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, UnicodeDecodeError) as exc:
        raise ModulePackageError(f"Cannot read module manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise ModulePackageError("module.json root must be an object")
    return manifest_path, data


def _unique_backup_path(backup_dir: Path) -> Path:
    for attempt in range(100):
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        suffix = f"-{attempt}" if attempt else ""
        candidate = backup_dir / f"{timestamp}{suffix}.json"
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise ModulePackageError("Unable to create unique backup path")


def _backup_file(path: Path, instance: FoundryInstance) -> Path:
    backup_dir = _hermes_home() / "backups" / "foundry-admin-cli" / instance.version / path.name
    backup_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    backup_path = _unique_backup_path(backup_dir)
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(backup_path, 0o600)
    return backup_path


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


def list_modules(instance: FoundryInstance) -> list[dict[str, Any]]:
    """Enumerate installed modules from Data/modules/*/module.json."""

    if not instance.modules_dir.exists():
        return []
    modules: list[dict[str, Any]] = []
    for module_dir in sorted(p for p in instance.modules_dir.iterdir() if p.is_dir() or p.is_symlink()):
        module_id = module_dir.name
        manifest_path = module_dir / "module.json"
        base = {
            "id": module_id,
            "directory_id": module_id,
            "manifest_id": None,
            "title": None,
            "version": None,
            "compatibility": {},
            "path": str(module_dir),
            "manifest": None,
            "valid": False,
            "symlink": module_dir.is_symlink(),
            "enabled_worlds": [],
        }
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (JSONDecodeError, UnicodeDecodeError):
            modules.append({**base, "error": "Invalid JSON in module.json"})
            continue
        except OSError as exc:
            modules.append({**base, "error": str(exc)})
            continue
        if not isinstance(data, dict):
            modules.append({**base, "error": "module.json root must be an object"})
            continue
        raw_manifest_id = data.get("id")
        if raw_manifest_id is not None and not isinstance(raw_manifest_id, str):
            modules.append({**base, "error": "module.json id must be a string"})
            continue
        manifest_id = raw_manifest_id or module_id
        modules.append(
            {
                **base,
                "id": manifest_id,
                "manifest_id": raw_manifest_id,
                "id_matches_directory": manifest_id == module_id,
                "title": data.get("title"),
                "version": data.get("version"),
                "compatibility": data.get("compatibility") or {},
                "manifest": data.get("manifest"),
                "valid": True,
            }
        )
    return modules


def create_module(
    instance: FoundryInstance,
    module_id: str,
    *,
    title: str,
    projects_dir: Path = Path("/home/jon/projects"),
    symlink: bool = False,
) -> dict[str, Any]:
    """Scaffold a minimal Foundry v13 module project."""

    _validate_module_id(module_id)
    if not title.strip():
        raise ModulePackageError("title cannot be empty")
    module_dir = projects_dir / module_id
    if module_dir.exists() or module_dir.is_symlink():
        raise ModulePackageError(f"Module project already exists: {module_id}")
    module_dir.mkdir(parents=True)
    for child in ["scripts", "templates", "styles", "languages"]:
        (module_dir / child).mkdir()
    manifest = {
        "id": module_id,
        "title": title,
        "version": "0.1.0",
        "compatibility": {"minimum": "13", "verified": "13"},
        "authors": [],
        "scripts": [],
        "styles": [],
        "languages": [{"lang": "en", "name": "English", "path": "languages/en.json"}],
    }
    _atomic_write_json(module_dir / "module.json", manifest)
    _atomic_write_json(module_dir / "languages" / "en.json", {})
    (module_dir / "CLAUDE.md").write_text(
        f"# {title} — Foundry VTT Module Notes\n\n"
        "## Purpose\n\nMinimal Foundry v13 module scaffold created by foundry-admin-cli.\n\n"
        "## Build / Test Commands\n\nNo build step configured yet.\n\n"
        "## Runtime Target\n\nFoundry VTT v13.\n",
        encoding="utf-8",
    )
    symlink_path = None
    if symlink:
        instance.modules_dir.mkdir(parents=True, exist_ok=True)
        symlink_path = instance.modules_dir / module_id
        if symlink_path.exists() or symlink_path.is_symlink():
            raise ModulePackageError(f"Foundry module path already exists: {module_id}")
        symlink_path.symlink_to(module_dir, target_is_directory=True)
    return {
        "version": instance.version,
        "module": module_id,
        "changed": True,
        "path": str(module_dir),
        "symlink_path": str(symlink_path) if symlink_path else None,
    }


def edit_module(
    instance: FoundryInstance,
    module_id: str,
    *,
    title: str | None = None,
    manifest_url: str | None = None,
) -> dict[str, Any]:
    """Update supported module.json fields with backup and atomic write."""

    manifest_path, data = _read_module_manifest(instance, module_id)
    updates: dict[str, Any] = {}
    if title is not None:
        if not title.strip():
            raise ModulePackageError("title cannot be empty")
        updates["title"] = title
    if manifest_url is not None:
        if not manifest_url.strip():
            raise ModulePackageError("manifest cannot be empty")
        try:
            validate_manifest_url(manifest_url)
        except PackageOperationError as exc:
            raise ModulePackageError(str(exc)) from exc
        updates["manifest"] = manifest_url
    if not updates:
        return {"version": instance.version, "module": module_id, "changed": False, "path": str(manifest_path)}
    changed = any(data.get(key) != value for key, value in updates.items())
    if not changed:
        return {"version": instance.version, "module": module_id, "changed": False, "path": str(manifest_path)}
    data.update(updates)
    _backup_file(manifest_path, instance)
    _atomic_write_json(manifest_path, data)
    return {"version": instance.version, "module": module_id, "changed": True, "path": str(manifest_path)}


def _fetch_manifest(url: str) -> dict[str, Any]:
    try:
        validate_manifest_url(url)
    except PackageOperationError as exc:
        raise ModulePackageError(str(exc)) from exc
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except OSError as exc:
        raise ModulePackageError(f"Could not fetch module manifest: {exc}") from exc
    try:
        data = json.loads(raw)
    except JSONDecodeError as exc:
        raise ModulePackageError("Remote module manifest was not JSON") from exc
    if not isinstance(data, dict):
        raise ModulePackageError("Remote module manifest root must be an object")
    return data


def _manifest_matches(local: dict[str, Any], remote: dict[str, Any]) -> bool:
    return local.get("version") == remote.get("version") and (local.get("compatibility") or {}) == (
        remote.get("compatibility") or {}
    )


def update_module(
    instance: FoundryInstance,
    module_id: str,
    *,
    client: Any,
    fetch_manifest: Any = _fetch_manifest,
) -> dict[str, Any]:
    """Update an installed module by comparing and re-running Foundry installPackage."""

    _, data = _read_module_manifest(instance, module_id)
    manifest = data.get("manifest")
    if not isinstance(manifest, str) or not manifest:
        raise ModulePackageError(f"No manifest URL recorded for module: {module_id}")
    remote = fetch_manifest(manifest)
    current_version = data.get("version")
    available_version = remote.get("version")
    if _manifest_matches(data, remote):
        return {
            "version": instance.version,
            "module": module_id,
            "manifest": manifest,
            "changed": False,
            "current_version": current_version,
            "available_version": available_version,
        }
    setup_result = client.setup_action(
        "installPackage",
        {"type": "module", "id": module_id, "manifest": manifest, "force": True},
    )
    return {
        "version": instance.version,
        "module": module_id,
        "manifest": manifest,
        "changed": True,
        "current_version": current_version,
        "available_version": available_version,
        "setup_result": setup_result,
    }


def _unique_archive_dir(base_dir: Path, module_id: str) -> Path:
    for attempt in range(100):
        suffix = f"-{attempt}" if attempt else ""
        candidate = base_dir / f"{module_id}{suffix}"
        if not candidate.exists():
            return candidate
    raise ModulePackageError("Unable to create unique archive path")


def remove_module(
    instance: FoundryInstance,
    module_id: str,
    *,
    permanent: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Archive module directories by default; unlink symlinks without deleting source."""

    module_dir = _literal_module_dir(instance, module_id)
    if module_dir.is_symlink():
        module_dir.unlink()
        return {
            "version": instance.version,
            "module": module_id,
            "changed": True,
            "removed": False,
            "unlinked": True,
            "archive_path": None,
        }
    if not (module_dir / "module.json").exists():
        raise ModulePackageError(f"Module not found: {module_id}")
    if permanent and not force:
        raise ModulePackageError("Permanent remove requires --force")
    if permanent:
        shutil.rmtree(module_dir)
        return {
            "version": instance.version,
            "module": module_id,
            "changed": True,
            "removed": True,
            "unlinked": False,
            "archive_path": None,
        }
    archive_root = _hermes_home() / "backups" / "foundry-admin-cli" / instance.version / "modules"
    archive_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(archive_root, 0o700)
    archive_path = _unique_archive_dir(archive_root, module_id)
    shutil.move(str(module_dir), str(archive_path))
    return {
        "version": instance.version,
        "module": module_id,
        "changed": True,
        "removed": False,
        "unlinked": False,
        "archive_path": str(archive_path),
    }
