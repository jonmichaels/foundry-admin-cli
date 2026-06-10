"""Foundry-native package backup and snapshot operations."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import FoundryInstance
from .process import ProcessError, get_status

SUPPORTED_BACKUP_TYPES = {"world", "system", "module", "snapshot"}
PACKAGE_BACKUP_TYPES = {"world", "system", "module"}


class BackupOperationError(RuntimeError):
    """Raised when a backup operation is unsafe or invalid."""


def _validate_package_backup_type(backup_type: str) -> None:
    if backup_type not in PACKAGE_BACKUP_TYPES:
        raise BackupOperationError("backup type must be one of: world, system, module")


def _normalize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    backup_type = manifest.get("type")
    normalized: dict[str, Any] = {
        "id": manifest.get("id"),
        "type": backup_type,
    }
    if backup_type == "snapshot":
        normalized.update(
            {
                "created_at": manifest.get("createdAt"),
                "size": manifest.get("size"),
                "original_size": manifest.get("originalSize"),
                "note": manifest.get("note"),
                "backups": list(manifest.get("backups", [])),
                "generation": manifest.get("generation"),
                "build": manifest.get("build"),
            }
        )
    else:
        normalized.update(
            {
                "package_id": manifest.get("packageId"),
                "title": manifest.get("title"),
                "created_at": manifest.get("createdAt"),
                "size": manifest.get("size"),
                "original_size": manifest.get("originalSize"),
                "note": manifest.get("note"),
                "snapshot_id": manifest.get("snapshotId"),
                "version": manifest.get("version"),
                "system": manifest.get("system"),
            }
        )
    return {key: value for key, value in normalized.items() if value is not None}


def _iter_manifests(raw: dict[str, Any]) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    snapshots = raw.get("snapshots", {})
    if isinstance(snapshots, dict):
        for snapshot in snapshots.values():
            if isinstance(snapshot, dict):
                manifests.append(snapshot)
    for backup_type in ("world", "module", "system"):
        packages = raw.get(backup_type, {})
        if not isinstance(packages, dict):
            continue
        for entries in packages.values():
            if not isinstance(entries, list):
                continue
            manifests.extend(entry for entry in entries if isinstance(entry, dict))
    return manifests


def _find_manifest(client: Any, backup_id: str) -> dict[str, Any]:
    raw = client.setup_action("listBackups")
    for manifest in _iter_manifests(raw):
        if manifest.get("id") == backup_id:
            return manifest
    raise BackupOperationError(f"Backup not found: {backup_id}")


def list_backups(
    *,
    client: Any,
    backup_type: str | None = None,
    package_id: str | None = None,
) -> dict[str, Any]:
    """List Foundry package backups and snapshots using the setup protocol."""

    if backup_type is not None and backup_type not in SUPPORTED_BACKUP_TYPES:
        raise BackupOperationError("backup type must be one of: world, system, module, snapshot")
    raw = client.setup_action("listBackups")
    rows = []
    for manifest in _iter_manifests(raw):
        normalized = _normalize_manifest(manifest)
        if backup_type is not None and normalized.get("type") != backup_type:
            continue
        if package_id is not None and normalized.get("package_id") != package_id:
            continue
        rows.append(normalized)
    rows.sort(key=lambda row: row.get("created_at") or 0, reverse=True)
    return {"count": len(rows), "backups": rows}


def create_backup(*, client: Any, backup_type: str, package_id: str, note: str = "") -> dict[str, Any]:
    """Create a Foundry package backup, then verify it appears in listBackups."""

    _validate_package_backup_type(backup_type)
    before_ids = {
        row["id"]
        for row in list_backups(client=client, backup_type=backup_type, package_id=package_id)["backups"]
        if "id" in row
    }
    payload = {"backups": [{"type": backup_type, "packageId": package_id, "note": note}]}
    client.setup_action("createBackup", payload)
    matches = list_backups(client=client, backup_type=backup_type, package_id=package_id)["backups"]
    new_matches = [row for row in matches if row.get("id") not in before_ids]
    if not new_matches:
        raise BackupOperationError("Backup creation did not produce a new visible backup manifest")
    return {"created": True, "backup": new_matches[0]}


def create_snapshot(*, client: Any, note: str = "") -> dict[str, Any]:
    """Create a Foundry snapshot, then verify it appears in listBackups."""

    before_ids = {row["id"] for row in list_backups(client=client, backup_type="snapshot")["backups"] if "id" in row}
    payload: dict[str, Any] = {}
    if note:
        payload["note"] = note
    client.setup_action("createSnapshot", payload)
    matches = list_backups(client=client, backup_type="snapshot")["backups"]
    new_matches = [row for row in matches if row.get("id") not in before_ids]
    if not new_matches:
        raise BackupOperationError("Snapshot creation did not produce a new visible snapshot manifest")
    return {"created": True, "snapshot": new_matches[0]}


def restore_backup(*, client: Any, backup_id: str, force: bool = False) -> dict[str, Any]:
    """Restore a Foundry package backup through the setup protocol."""

    if not force:
        raise BackupOperationError("--force is required to restore a backup")
    manifest = _find_manifest(client, backup_id)
    if manifest.get("type") == "snapshot":
        raise BackupOperationError("Use restore-snapshot for snapshot ids")
    client.setup_action("restoreBackup", {"backups": [manifest]})
    return {"restored": True, "backup": _normalize_manifest(manifest)}


def restore_snapshot(*, client: Any, snapshot_id: str, force: bool = False) -> dict[str, Any]:
    """Restore a Foundry snapshot through the setup protocol."""

    if not force:
        raise BackupOperationError("--force is required to restore a snapshot")
    manifest = _find_manifest(client, snapshot_id)
    if manifest.get("type") != "snapshot":
        raise BackupOperationError("restore-snapshot requires a snapshot id")
    client.setup_action("restoreSnapshot", {"snapshotData": manifest})
    return {"restored": True, "snapshot": _normalize_manifest(manifest)}


def delete_backup(*, client: Any, backup_id: str, force: bool = False) -> dict[str, Any]:
    """Delete a Foundry package backup through the setup protocol."""

    if not force:
        raise BackupOperationError("--force is required to delete a backup")
    manifest = _find_manifest(client, backup_id)
    if manifest.get("type") == "snapshot":
        raise BackupOperationError("Use delete-snapshot for snapshot ids")
    client.setup_action("deleteBackup", {"backups": [manifest]})
    return {"deleted": True, "backup": _normalize_manifest(manifest)}


def delete_snapshot(*, client: Any, snapshot_id: str, force: bool = False) -> dict[str, Any]:
    """Delete a Foundry snapshot through the setup protocol."""

    if not force:
        raise BackupOperationError("--force is required to delete a snapshot")
    manifest = _find_manifest(client, snapshot_id)
    if manifest.get("type") != "snapshot":
        raise BackupOperationError("delete-snapshot requires a snapshot id")
    client.setup_action("deleteSnapshot", {"snapshots": [manifest]})
    return {"deleted": True, "snapshot": _normalize_manifest(manifest)}


def _current_foundry_status(instance: FoundryInstance) -> str:
    try:
        return get_status(instance).status
    except ProcessError as exc:
        raise BackupOperationError(str(exc)) from exc


def _ensure_stopped(instance: FoundryInstance, *, require_stopped: bool) -> str:
    if not require_stopped:
        return "not-checked"
    status = _current_foundry_status(instance)
    if status not in {"stopped", "not-in-pm2"}:
        raise BackupOperationError(f"Foundry must be stopped for full User Data archive operations; current status is {status}")
    return status


def _default_archive_path(instance: FoundryInstance, *, suffix: str = "user-data") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return instance.resolved_backup_dir() / instance.version / "user-data" / f"foundry-{instance.version}-{suffix}-{stamp}.tar.gz"


def _add_directory_if_present(archive: tarfile.TarFile, source: Path, arcname: str) -> bool:
    if not source.exists():
        return False
    archive.add(source, arcname=arcname, recursive=True)
    return True


def create_user_data_archive(
    instance: FoundryInstance,
    *,
    output: Path | None = None,
    include_config: bool = False,
    require_stopped: bool = True,
) -> dict[str, Any]:
    """Create a full User Data archive containing Data and optionally Config."""

    instance.require_local("full User Data archive")
    status = _ensure_stopped(instance, require_stopped=require_stopped)
    data_root = instance.data_dir / "Data"
    if not data_root.is_dir():
        raise BackupOperationError(f"Data directory does not exist: {data_root}")
    archive_path = Path(output) if output is not None else _default_archive_path(instance)
    try:
        archive_parent = archive_path.resolve().parent
        data_dir_resolved = instance.data_dir.resolve()
        if archive_parent == data_dir_resolved or data_dir_resolved in archive_parent.parents:
            raise BackupOperationError("Archive output must be outside the Foundry User Data directory")
    except OSError as exc:
        raise BackupOperationError(f"Could not resolve archive output path: {archive_path}") from exc
    archive_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(archive_path.parent, 0o700)
    included: list[str] = []
    with tarfile.open(archive_path, "w:gz") as archive:
        if _add_directory_if_present(archive, instance.data_dir / "Data", "Data"):
            included.append("Data")
        if include_config and _add_directory_if_present(archive, instance.data_dir / "Config", "Config"):
            included.append("Config")
    os.chmod(archive_path, 0o600)
    return {
        "version": instance.version,
        "created": True,
        "archive": str(archive_path),
        "included": included,
        "include_config": include_config,
        "foundry_status": status,
        "sensitive": include_config,
    }


def _validate_archive_member(member: tarfile.TarInfo) -> None:
    name = member.name
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise BackupOperationError(f"unsafe archive member: {name}")
    if not path.parts or path.parts[0] not in {"Data", "Config"}:
        raise BackupOperationError(f"unsafe archive member: {name}")
    if member.issym() or member.islnk():
        raise BackupOperationError(f"unsafe archive member link: {name}")
    if not (member.isdir() or member.isfile()):
        raise BackupOperationError(f"unsupported archive member type: {name}")
    if len(path.parts) == 1 and not member.isdir():
        raise BackupOperationError(f"top-level {path.parts[0]} must be a directory")


def _validate_archive_members(members: list[tarfile.TarInfo]) -> set[str]:
    roots: set[str] = set()
    for member in members:
        _validate_archive_member(member)
        roots.add(Path(member.name).parts[0])
    if "Data" not in roots:
        raise BackupOperationError("User Data archive must contain a top-level Data directory")
    return roots


def _replace_from_extract(instance: FoundryInstance, extracted_root: Path, roots: set[str]) -> None:
    for root in ("Data", "Config"):
        if root not in roots:
            continue
        target = instance.data_dir / root
        replacement = extracted_root / root
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(replacement), str(target))


def restore_user_data_archive(
    instance: FoundryInstance,
    *,
    archive: Path,
    force: bool = False,
    require_stopped: bool = True,
) -> dict[str, Any]:
    """Restore a full User Data archive containing Data and optional Config."""

    instance.require_local("full User Data restore")
    if not force:
        raise BackupOperationError("--force is required to restore a full User Data archive")
    status = _ensure_stopped(instance, require_stopped=require_stopped)
    archive_path = Path(archive)
    if not archive_path.exists():
        raise BackupOperationError(f"Archive does not exist: {archive_path}")
    instance.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fvtt-restore-") as temp_dir:
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir()
        with tarfile.open(archive_path, "r:gz") as tar:
            members = tar.getmembers()
            roots = _validate_archive_members(members)
            pre_restore = create_user_data_archive(
                instance,
                output=_default_archive_path(instance, suffix="pre-restore"),
                include_config="Config" in roots,
                require_stopped=False,
            )
            tar.extractall(extract_root, members=members)
        _replace_from_extract(instance, extract_root, roots)
    return {
        "version": instance.version,
        "restored": True,
        "archive": str(archive_path),
        "restored_roots": sorted(roots),
        "pre_restore_archive": pre_restore["archive"],
        "foundry_status": status,
    }
