import json
import stat

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.worlds import WorldConfigError, edit_world


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


def write_world(data_dir, world_id, data):
    world_dir = data_dir / "Data" / "worlds" / world_id
    world_dir.mkdir(parents=True)
    (world_dir / "world.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return world_dir / "world.json"


def test_edit_world_updates_supported_fields_and_backs_up_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    manifest = write_world(inst.data_dir, "module-test-dnd5e", {"id": "module-test-dnd5e", "title": "Old", "system": "dnd5e"})

    result = edit_world(inst, "module-test-dnd5e", title="New Title", system="black-flag")

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["title"] == "New Title"
    assert data["system"] == "black-flag"
    assert result["changed"] is True
    assert result["world"] == "module-test-dnd5e"
    backup_dir = tmp_path / "hermes" / "backups" / "foundry-admin-cli" / "v13" / "world.json"
    backups = list(backup_dir.glob("*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["title"] == "Old"
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600


def test_edit_world_reports_no_change_without_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_world(inst.data_dir, "module-test-dnd5e", {"id": "module-test-dnd5e", "title": "Same", "system": "dnd5e"})

    result = edit_world(inst, "module-test-dnd5e", title="Same")

    assert result["changed"] is False
    assert not (tmp_path / "hermes" / "backups").exists()


def test_edit_world_refuses_unknown_world_without_creating_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)

    with pytest.raises(WorldConfigError, match="World not found"):
        edit_world(inst, "missing-world", title="Nope")

    assert not (tmp_path / "hermes" / "backups").exists()


def test_edit_world_refuses_empty_update(tmp_path):
    inst = instance(tmp_path)
    write_world(inst.data_dir, "module-test-dnd5e", {"id": "module-test-dnd5e", "title": "Old", "system": "dnd5e"})

    with pytest.raises(WorldConfigError, match="No fields provided"):
        edit_world(inst, "module-test-dnd5e")


def test_edit_world_rejects_empty_title_and_system(tmp_path):
    inst = instance(tmp_path)
    write_world(inst.data_dir, "module-test-dnd5e", {"id": "module-test-dnd5e", "title": "Old", "system": "dnd5e"})

    with pytest.raises(WorldConfigError, match="title cannot be empty"):
        edit_world(inst, "module-test-dnd5e", title="")
    with pytest.raises(WorldConfigError, match="system cannot be empty"):
        edit_world(inst, "module-test-dnd5e", system="")


def test_edit_world_rejects_invalid_world_id(tmp_path):
    inst = instance(tmp_path)

    with pytest.raises(WorldConfigError, match="Invalid world id"):
        edit_world(inst, "../outside", title="Nope")
