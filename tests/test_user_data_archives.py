from __future__ import annotations

import tarfile

import pytest

from foundry_admin_cli.backups import (
    BackupOperationError,
    create_user_data_archive,
    restore_user_data_archive,
)
from foundry_admin_cli.config import FoundryInstance


class FakeStatus:
    def __init__(self, status="stopped"):
        self.status = status


def instance(tmp_path):
    data_dir = tmp_path / "userdata"
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=data_dir,
        url="http://foundry.test/",
        pm2_name="foundry-v13",
        backup_dir=tmp_path / "backups",
    )


def test_create_user_data_archive_requires_data_directory(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("stopped"))

    with pytest.raises(BackupOperationError, match="Data directory does not exist"):
        create_user_data_archive(inst, output=tmp_path / "archive.tar.gz")


def test_create_user_data_archive_rejects_output_inside_user_data(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    (inst.data_dir / "Data").mkdir(parents=True)
    output = inst.data_dir / "Data" / "archive.tar.gz"
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("stopped"))

    with pytest.raises(BackupOperationError, match="outside the Foundry User Data directory"):
        create_user_data_archive(inst, output=output)


def test_create_user_data_archive_includes_data_and_optional_config(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    (inst.data_dir / "Data" / "worlds" / "w").mkdir(parents=True)
    (inst.data_dir / "Data" / "worlds" / "w" / "world.json").write_text('{"id":"w"}', encoding="utf-8")
    (inst.data_dir / "Config").mkdir(parents=True)
    (inst.data_dir / "Config" / "options.json").write_text('{"world":"w"}', encoding="utf-8")
    output = tmp_path / "archive.tar.gz"
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("stopped"))

    result = create_user_data_archive(inst, output=output, include_config=True)

    assert result["created"] is True
    assert result["archive"] == str(output)
    with tarfile.open(output, "r:gz") as archive:
        names = set(archive.getnames())
    assert "Data/worlds/w/world.json" in names
    assert "Config/options.json" in names


def test_create_user_data_archive_requires_stopped_foundry_by_default(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    (inst.data_dir / "Data").mkdir(parents=True)
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("online"))

    with pytest.raises(BackupOperationError, match="Foundry must be stopped"):
        create_user_data_archive(inst, output=tmp_path / "archive.tar.gz")


def test_create_user_data_archive_can_explicitly_allow_running(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    (inst.data_dir / "Data").mkdir(parents=True)
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("online"))

    result = create_user_data_archive(inst, output=tmp_path / "archive.tar.gz", require_stopped=False)

    assert result["created"] is True
    assert result["foundry_status"] == "not-checked"


def test_restore_user_data_archive_requires_force_and_stopped(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    archive_path = tmp_path / "archive.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        pass
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("stopped"))

    with pytest.raises(BackupOperationError, match="--force is required"):
        restore_user_data_archive(inst, archive=archive_path, force=False)

    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("online"))
    with pytest.raises(BackupOperationError, match="Foundry must be stopped"):
        restore_user_data_archive(inst, archive=archive_path, force=True)


def test_restore_user_data_archive_replaces_data_and_config(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    (inst.data_dir / "Data" / "old").mkdir(parents=True)
    (inst.data_dir / "Data" / "old" / "file.txt").write_text("old", encoding="utf-8")
    (inst.data_dir / "Config").mkdir(parents=True)
    (inst.data_dir / "Config" / "options.json").write_text("old", encoding="utf-8")
    source = tmp_path / "source"
    (source / "Data" / "worlds" / "w").mkdir(parents=True)
    (source / "Data" / "worlds" / "w" / "world.json").write_text("new", encoding="utf-8")
    (source / "Config").mkdir(parents=True)
    (source / "Config" / "options.json").write_text("new", encoding="utf-8")
    archive_path = tmp_path / "archive.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(source / "Data", arcname="Data")
        archive.add(source / "Config", arcname="Config")
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("stopped"))

    result = restore_user_data_archive(inst, archive=archive_path, force=True)

    assert result["restored"] is True
    assert (inst.data_dir / "Data" / "worlds" / "w" / "world.json").read_text(encoding="utf-8") == "new"
    assert not (inst.data_dir / "Data" / "old").exists()
    assert (inst.data_dir / "Config" / "options.json").read_text(encoding="utf-8") == "new"
    assert result["pre_restore_archive"]


def test_restore_user_data_archive_rejects_path_traversal(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    archive_path = tmp_path / "evil.tar.gz"
    payload = tmp_path / "payload.txt"
    payload.write_text("evil", encoding="utf-8")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(payload, arcname="../evil.txt")
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("stopped"))

    with pytest.raises(BackupOperationError, match="unsafe archive member"):
        restore_user_data_archive(inst, archive=archive_path, force=True)


def test_restore_user_data_archive_rejects_top_level_data_file(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    archive_path = tmp_path / "evil.tar.gz"
    payload = tmp_path / "Data"
    payload.write_text("not a directory", encoding="utf-8")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(payload, arcname="Data")
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("stopped"))

    with pytest.raises(BackupOperationError, match="top-level Data must be a directory"):
        restore_user_data_archive(inst, archive=archive_path, force=True)


def test_restore_user_data_archive_rejects_special_tar_members(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    archive_path = tmp_path / "evil.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        data_dir = tarfile.TarInfo("Data")
        data_dir.type = tarfile.DIRTYPE
        archive.addfile(data_dir)
        fifo = tarfile.TarInfo("Data/fifo")
        fifo.type = tarfile.FIFOTYPE
        archive.addfile(fifo)
    monkeypatch.setattr("foundry_admin_cli.backups.get_status", lambda instance: FakeStatus("stopped"))

    with pytest.raises(BackupOperationError, match="unsupported archive member"):
        restore_user_data_archive(inst, archive=archive_path, force=True)
