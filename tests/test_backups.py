from __future__ import annotations

import pytest

from foundry_admin_cli.backups import (
    BackupOperationError,
    create_backup,
    create_snapshot,
    delete_backup,
    list_backups,
    restore_backup,
    restore_snapshot,
)


class FakeClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def setup_action(self, action, payload=None):
        self.calls.append((action, payload or {}))
        response = self.responses.get(action, {})
        if isinstance(response, list):
            return response.pop(0)
        return response


def test_list_backups_flattens_foundry_manifest_tree():
    client = FakeClient(
        {
            "listBackups": {
                "world": {
                    "my-world": [
                        {
                            "id": "world.my-world.2026-06-09.1781000000000",
                            "type": "world",
                            "packageId": "my-world",
                            "title": "My World",
                            "createdAt": 1781000000000,
                            "size": 100,
                            "originalSize": 200,
                            "note": "before edit",
                            "snapshotId": None,
                        }
                    ]
                },
                "module": {},
                "system": {},
                "snapshots": {
                    "snapshot.2026-06-09.1781000000001": {
                        "id": "snapshot.2026-06-09.1781000000001",
                        "type": "snapshot",
                        "createdAt": 1781000000001,
                        "size": 300,
                        "originalSize": 500,
                        "note": "major update",
                        "backups": ["world.my-world.2026-06-09.1781000000000"],
                    }
                },
            }
        }
    )

    result = list_backups(client=client)

    assert client.calls == [("listBackups", {})]
    assert result["count"] == 2
    assert result["backups"][0]["id"] == "snapshot.2026-06-09.1781000000001"
    assert result["backups"][1]["package_id"] == "my-world"


def test_list_backups_filters_type_and_package_id():
    client = FakeClient(
        {
            "listBackups": {
                "world": {
                    "a": [{"id": "world.a.2026-06-09.1", "type": "world", "packageId": "a"}],
                    "b": [{"id": "world.b.2026-06-09.2", "type": "world", "packageId": "b"}],
                },
                "module": {"m": [{"id": "module.m.2026-06-09.3", "type": "module", "packageId": "m"}]},
                "system": {},
                "snapshots": {},
            }
        }
    )

    result = list_backups(client=client, backup_type="world", package_id="b")

    assert result["count"] == 1
    assert result["backups"][0]["id"] == "world.b.2026-06-09.2"


def test_create_backup_posts_foundry_backup_payload_and_verifies_by_list():
    backup_id = "world.my-world.2026-06-09.1781000000000"
    client = FakeClient(
        {
            "listBackups": [
                {"world": {"my-world": []}, "module": {}, "system": {}, "snapshots": {}},
                {
                    "world": {"my-world": [{"id": backup_id, "type": "world", "packageId": "my-world", "note": "before"}]},
                    "module": {},
                    "system": {},
                    "snapshots": {},
                },
            ]
        }
    )

    result = create_backup(client=client, backup_type="world", package_id="my-world", note="before")

    assert client.calls[1] == (
        "createBackup",
        {"backups": [{"type": "world", "packageId": "my-world", "note": "before"}]},
    )
    assert result["created"] is True
    assert result["backup"]["id"] == backup_id


def test_create_backup_returns_new_manifest_not_existing_match():
    old_id = "world.my-world.2026-06-09.1"
    new_id = "world.my-world.2026-06-09.2"
    client = FakeClient(
        {
            "listBackups": [
                {"world": {"my-world": [{"id": old_id, "type": "world", "packageId": "my-world", "createdAt": 1}]}, "module": {}, "system": {}, "snapshots": {}},
                {"world": {"my-world": [{"id": new_id, "type": "world", "packageId": "my-world", "createdAt": 2}, {"id": old_id, "type": "world", "packageId": "my-world", "createdAt": 1}]}, "module": {}, "system": {}, "snapshots": {}},
            ]
        }
    )

    result = create_backup(client=client, backup_type="world", package_id="my-world", note="before")

    assert result["backup"]["id"] == new_id


def test_create_snapshot_posts_note_and_verifies_by_list():
    snapshot_id = "snapshot.2026-06-09.1781000000001"
    client = FakeClient(
        {
            "listBackups": [
                {"world": {}, "module": {}, "system": {}, "snapshots": {}},
                {
                    "world": {},
                    "module": {},
                    "system": {},
                    "snapshots": {snapshot_id: {"id": snapshot_id, "type": "snapshot", "note": "before update"}},
                },
            ]
        }
    )

    result = create_snapshot(client=client, note="before update")

    assert client.calls[1] == ("createSnapshot", {"note": "before update"})
    assert result["created"] is True
    assert result["snapshot"]["id"] == snapshot_id


def test_restore_backup_requires_force():
    with pytest.raises(BackupOperationError, match="--force is required"):
        restore_backup(client=FakeClient(), backup_id="world.my-world.2026-06-09.1", force=False)


def test_restore_backup_posts_manifest_from_list_when_forced():
    backup_id = "world.my-world.2026-06-09.1"
    manifest = {"id": backup_id, "type": "world", "packageId": "my-world"}
    client = FakeClient(
        {
            "listBackups": {"world": {"my-world": [manifest]}, "module": {}, "system": {}, "snapshots": {}},
        }
    )

    result = restore_backup(client=client, backup_id=backup_id, force=True)

    assert client.calls[-1] == ("restoreBackup", {"backups": [manifest]})
    assert result == {"restored": True, "backup": {"id": backup_id, "type": "world", "package_id": "my-world"}}


def test_restore_snapshot_posts_snapshot_manifest_when_forced():
    snapshot_id = "snapshot.2026-06-09.1"
    manifest = {"id": snapshot_id, "type": "snapshot", "backups": ["world.my-world.2026-06-09.1"]}
    client = FakeClient(
        {
            "listBackups": {"world": {}, "module": {}, "system": {}, "snapshots": {snapshot_id: manifest}},
        }
    )

    result = restore_snapshot(client=client, snapshot_id=snapshot_id, force=True)

    assert client.calls[-1] == ("restoreSnapshot", {"snapshotData": manifest})
    assert result["restored"] is True
    assert result["snapshot"]["id"] == snapshot_id


def test_delete_backup_requires_force():
    with pytest.raises(BackupOperationError, match="--force is required"):
        delete_backup(client=FakeClient(), backup_id="world.my-world.2026-06-09.1", force=False)
