import json

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.worlds import WorldConfigError, create_world


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


def write_system(inst, system_id="dnd5e", version="5.3.3"):
    system_dir = inst.data_dir / "Data" / "systems" / system_id
    system_dir.mkdir(parents=True)
    (system_dir / "system.json").write_text(json.dumps({"id": system_id, "title": system_id, "version": version}), encoding="utf-8")
    return system_dir


def test_create_world_writes_foundry_style_world_directory(tmp_path):
    inst = instance(tmp_path)
    write_system(inst, "dnd5e", "5.3.3")

    result = create_world(inst, "fvtt-cli-smoke", title="Smoke World", system="dnd5e")

    world_dir = inst.worlds_dir / "fvtt-cli-smoke"
    assert result["changed"] is True
    assert result["world"] == "fvtt-cli-smoke"
    assert (world_dir / "data").is_dir()
    assert (world_dir / "scenes").is_dir()
    manifest = json.loads((world_dir / "world.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "fvtt-cli-smoke"
    assert manifest["title"] == "Smoke World"
    assert manifest["system"] == "dnd5e"
    assert manifest["systemVersion"] == "5.3.3"
    assert manifest["coreVersion"]
    assert manifest["compatibility"]["minimum"] == 13
    assert manifest["compatibility"]["verified"] == 13
    assert manifest["lastPlayed"]


def test_create_world_rejects_existing_world(tmp_path):
    inst = instance(tmp_path)
    write_system(inst)
    (inst.worlds_dir / "fvtt-cli-smoke").mkdir(parents=True)

    with pytest.raises(WorldConfigError, match="already exists"):
        create_world(inst, "fvtt-cli-smoke", title="Smoke", system="dnd5e")


def test_create_world_rejects_symlink_world_target(tmp_path):
    inst = instance(tmp_path)
    write_system(inst)
    target = tmp_path / "outside"
    target.mkdir()
    inst.worlds_dir.mkdir(parents=True)
    (inst.worlds_dir / "fvtt-cli-smoke").symlink_to(target, target_is_directory=True)

    with pytest.raises(WorldConfigError, match="already exists"):
        create_world(inst, "fvtt-cli-smoke", title="Smoke", system="dnd5e")

    assert target.exists()


def test_create_world_rolls_back_partial_directory_on_write_failure(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    write_system(inst)

    def fail_write(path, data):
        raise OSError("disk full")

    monkeypatch.setattr("foundry_admin_cli.worlds._atomic_write_json", fail_write)

    with pytest.raises(OSError, match="disk full"):
        create_world(inst, "fvtt-cli-smoke", title="Smoke", system="dnd5e")

    assert not (inst.worlds_dir / "fvtt-cli-smoke").exists()


def test_create_world_rejects_missing_system(tmp_path):
    inst = instance(tmp_path)

    with pytest.raises(WorldConfigError, match="System not found"):
        create_world(inst, "fvtt-cli-smoke", title="Smoke", system="dnd5e")


def test_create_world_rejects_invalid_world_id(tmp_path):
    inst = instance(tmp_path)
    write_system(inst)

    with pytest.raises(WorldConfigError, match="Invalid world id"):
        create_world(inst, "../outside", title="Smoke", system="dnd5e")


def test_create_world_rejects_empty_title_and_system(tmp_path):
    inst = instance(tmp_path)
    write_system(inst)

    with pytest.raises(WorldConfigError, match="title cannot be empty"):
        create_world(inst, "fvtt-cli-smoke", title="", system="dnd5e")
    with pytest.raises(WorldConfigError, match="system cannot be empty"):
        create_world(inst, "fvtt-cli-smoke", title="Smoke", system="")
