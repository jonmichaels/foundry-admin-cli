import json

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.worlds import WorldConfigError, delete_world


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


def write_world(data_dir, world_id):
    world_dir = data_dir / "Data" / "worlds" / world_id
    world_dir.mkdir(parents=True)
    (world_dir / "world.json").write_text(json.dumps({"id": world_id, "title": world_id, "system": "dnd5e"}), encoding="utf-8")
    (world_dir / "notes.txt").write_text("world data", encoding="utf-8")
    return world_dir


def write_options(inst, data):
    inst.options_path.parent.mkdir(parents=True)
    inst.options_path.write_text(json.dumps(data), encoding="utf-8")


def test_delete_world_archives_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    world_dir = write_world(inst.data_dir, "fvtt-cli-smoke")

    result = delete_world(inst, "fvtt-cli-smoke")

    assert result["changed"] is True
    assert result["deleted"] is False
    assert result["archive_path"].endswith("fvtt-cli-smoke")
    archive_path = tmp_path / "hermes" / "backups" / "foundry-admin-cli" / "v13" / "worlds" / "fvtt-cli-smoke"
    assert archive_path.exists()
    assert (archive_path / "world.json").exists()
    assert not world_dir.exists()


def test_delete_world_uses_unique_archive_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_world(inst.data_dir, "fvtt-cli-smoke")
    archive_dir = tmp_path / "hermes" / "backups" / "foundry-admin-cli" / "v13" / "worlds" / "fvtt-cli-smoke"
    archive_dir.mkdir(parents=True)

    result = delete_world(inst, "fvtt-cli-smoke")

    assert result["archive_path"].endswith("fvtt-cli-smoke-1")
    assert (archive_dir.parent / "fvtt-cli-smoke-1" / "world.json").exists()


def test_delete_world_refuses_configured_world_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    world_dir = write_world(inst.data_dir, "module-test-dnd5e")
    write_options(inst, {"world": "module-test-dnd5e"})

    with pytest.raises(WorldConfigError, match="configured world"):
        delete_world(inst, "module-test-dnd5e")

    assert world_dir.exists()


def test_delete_world_refuses_configured_manifest_id_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    world_dir = inst.data_dir / "Data" / "worlds" / "dir-id"
    world_dir.mkdir(parents=True)
    (world_dir / "world.json").write_text(
        json.dumps({"id": "manifest-id", "title": "Mismatch", "system": "dnd5e"}),
        encoding="utf-8",
    )
    write_options(inst, {"world": "manifest-id"})

    with pytest.raises(WorldConfigError, match="configured world"):
        delete_world(inst, "dir-id")

    assert world_dir.exists()


def test_delete_world_can_archive_configured_world_with_force(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_world(inst.data_dir, "module-test-dnd5e")
    write_options(inst, {"world": "module-test-dnd5e"})

    result = delete_world(inst, "module-test-dnd5e", force=True)

    assert result["changed"] is True
    assert result["archive_path"]


def test_delete_world_permanent_requires_force(tmp_path):
    inst = instance(tmp_path)
    world_dir = write_world(inst.data_dir, "fvtt-cli-smoke")

    with pytest.raises(WorldConfigError, match="requires --force"):
        delete_world(inst, "fvtt-cli-smoke", permanent=True)

    assert world_dir.exists()


def test_delete_world_permanent_removes_directory_with_force(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    world_dir = write_world(inst.data_dir, "fvtt-cli-smoke")

    result = delete_world(inst, "fvtt-cli-smoke", permanent=True, force=True)

    assert result["deleted"] is True
    assert result["archive_path"] is None
    assert not world_dir.exists()


def test_delete_world_refuses_invalid_world_id(tmp_path):
    inst = instance(tmp_path)

    with pytest.raises(WorldConfigError, match="Invalid world id"):
        delete_world(inst, "../outside")


def test_delete_world_refuses_symlink_world_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    target_dir = write_world(inst.data_dir, "real-world")
    alias_dir = inst.worlds_dir / "alias-world"
    alias_dir.symlink_to(target_dir, target_is_directory=True)

    with pytest.raises(WorldConfigError, match="symlink"):
        delete_world(inst, "alias-world")

    assert target_dir.exists()
    assert alias_dir.exists()


def test_delete_world_refuses_missing_world(tmp_path):
    inst = instance(tmp_path)

    with pytest.raises(WorldConfigError, match="World not found"):
        delete_world(inst, "missing-world")
