"""Foundry-native package backup and snapshot operations."""

from __future__ import annotations

from typing import Any

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
