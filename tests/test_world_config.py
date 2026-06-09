import json
import stat

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.worlds import WorldConfigError, configure_world, stop_world


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


def write_world(data_dir, world_id, data=None):
    world_dir = data_dir / "Data" / "worlds" / world_id
    world_dir.mkdir(parents=True)
    (world_dir / "world.json").write_text(json.dumps(data or {"id": world_id, "title": world_id, "system": "dnd5e"}))
    return world_dir


def write_options(inst, data):
    inst.options_path.parent.mkdir(parents=True)
    inst.options_path.write_text(json.dumps(data, indent=2))


def test_configure_world_sets_options_world_and_writes_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_world(inst.data_dir, "module-test-dnd5e")
    write_options(inst, {"port": 30000, "world": "old-world"})

    result = configure_world(inst, "module-test-dnd5e")

    assert json.loads(inst.options_path.read_text())["world"] == "module-test-dnd5e"
    assert result["world"] == "module-test-dnd5e"
    assert result["restart_required"] is True
    backup_path = tmp_path / "hermes" / "backups" / "foundry-admin-cli" / "v13" / "options.json"
    backups = list(backup_path.glob("*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["world"] == "old-world"


def test_configure_world_refuses_unknown_world_without_modifying_options(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_options(inst, {"port": 30000, "world": "old-world"})

    with pytest.raises(WorldConfigError, match="World not found"):
        configure_world(inst, "missing-world")

    assert json.loads(inst.options_path.read_text())["world"] == "old-world"


def test_configure_world_rejects_path_traversal_world_id(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_options(inst, {"port": 30000, "world": "old-world"})

    with pytest.raises(WorldConfigError, match="Invalid world id"):
        configure_world(inst, "../outside")

    assert json.loads(inst.options_path.read_text())["world"] == "old-world"


def test_configure_world_writes_restrictive_unique_backups(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_world(inst.data_dir, "world-a")
    write_world(inst.data_dir, "world-b")
    write_options(inst, {"port": 30000, "world": "old-world"})

    configure_world(inst, "world-a")
    configure_world(inst, "world-b")

    backup_dir = tmp_path / "hermes" / "backups" / "foundry-admin-cli" / "v13" / "options.json"
    backups = sorted(backup_dir.glob("*.json"))
    assert len(backups) == 2
    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in backups)


def test_stop_world_sets_options_world_to_none_and_writes_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_options(inst, {"port": 30000, "world": "module-test-dnd5e"})

    result = stop_world(inst)

    assert json.loads(inst.options_path.read_text())["world"] is None
    assert result["world"] is None
    assert result["restart_required"] is True
    backups = list((tmp_path / "hermes" / "backups" / "foundry-admin-cli" / "v13" / "options.json").glob("*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["world"] == "module-test-dnd5e"


def test_configure_world_reports_no_change_when_already_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    inst = instance(tmp_path)
    write_world(inst.data_dir, "module-test-dnd5e")
    write_options(inst, {"port": 30000, "world": "module-test-dnd5e"})

    result = configure_world(inst, "module-test-dnd5e")

    assert result["changed"] is False
    assert result["restart_required"] is False
    assert not (tmp_path / "hermes" / "backups").exists()


def test_world_configuration_requires_local_instance(tmp_path):
    inst = FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
        mode="http-only",
    )

    with pytest.raises(Exception, match="requires local"):
        stop_world(inst)
