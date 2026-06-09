import json

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.systems import SystemPackageError, list_systems, remove_system, update_system


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


def write_system(inst, system_id="dnd5e", **extra):
    system_dir = inst.data_dir / "Data" / "systems" / system_id
    system_dir.mkdir(parents=True)
    manifest = {
        "id": system_id,
        "title": "D&D 5e",
        "version": "5.3.3",
        "compatibility": {"minimum": "13", "verified": "13"},
        "manifest": "https://example.test/system.json",
    }
    manifest.update(extra)
    (system_dir / "system.json").write_text(json.dumps(manifest), encoding="utf-8")
    return system_dir


def write_world(inst, world_id="world-a", system="dnd5e"):
    world_dir = inst.worlds_dir / world_id
    world_dir.mkdir(parents=True)
    (world_dir / "world.json").write_text(json.dumps({"id": world_id, "title": world_id, "system": system}), encoding="utf-8")


def test_list_systems_reports_installed_systems(tmp_path):
    inst = instance(tmp_path)
    write_system(inst)

    systems = list_systems(inst)

    assert systems == [
        {
            "id": "dnd5e",
            "directory_id": "dnd5e",
            "manifest_id": "dnd5e",
            "id_matches_directory": True,
            "title": "D&D 5e",
            "version": "5.3.3",
            "compatibility": {"minimum": "13", "verified": "13"},
            "path": str(inst.systems_dir / "dnd5e"),
            "manifest": "https://example.test/system.json",
            "valid": True,
            "worlds": [],
        }
    ]


def test_list_systems_reports_invalid_manifests_without_crashing(tmp_path):
    inst = instance(tmp_path)
    bad_dir = inst.systems_dir / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "system.json").write_text("[]", encoding="utf-8")

    systems = list_systems(inst)

    assert systems[0]["id"] == "bad"
    assert systems[0]["valid"] is False
    assert systems[0]["error"] == "system.json root must be an object"


def test_list_systems_includes_world_dependencies(tmp_path):
    inst = instance(tmp_path)
    write_system(inst)
    write_world(inst, "one", "dnd5e")

    systems = list_systems(inst)

    assert systems[0]["worlds"] == ["one"]


def test_remove_system_archives_by_default(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    system_dir = write_system(inst)
    hermes_home = tmp_path / "hermes"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    result = remove_system(inst, "dnd5e")

    assert result["changed"] is True
    assert result["removed"] is False
    assert not system_dir.exists()
    assert result["archive_path"].startswith(str(hermes_home))


def test_remove_system_refuses_world_dependency_without_force(tmp_path):
    inst = instance(tmp_path)
    write_system(inst)
    write_world(inst, "one", "dnd5e")

    with pytest.raises(SystemPackageError, match="used by worlds"):
        remove_system(inst, "dnd5e")


def test_remove_system_refuses_world_dependency_by_manifest_id(tmp_path):
    inst = instance(tmp_path)
    write_system(inst, system_id="folder-name", id="manifest-id")
    write_world(inst, "one", "manifest-id")

    with pytest.raises(SystemPackageError, match="used by worlds"):
        remove_system(inst, "folder-name")


def test_remove_system_permanent_requires_force(tmp_path):
    inst = instance(tmp_path)
    write_system(inst)

    with pytest.raises(SystemPackageError, match="Permanent remove requires --force"):
        remove_system(inst, "dnd5e", permanent=True)


def test_remove_system_rejects_symlink_target(tmp_path):
    inst = instance(tmp_path)
    target = tmp_path / "outside"
    target.mkdir()
    inst.systems_dir.mkdir(parents=True)
    (inst.systems_dir / "dnd5e").symlink_to(target, target_is_directory=True)

    with pytest.raises(SystemPackageError, match="symlinked system"):
        remove_system(inst, "dnd5e", force=True)


def test_update_system_uses_manifest_from_installed_system(tmp_path):
    inst = instance(tmp_path)
    write_system(inst, manifest="https://example.test/dnd5e/system.json")
    calls = []

    class FakeClient:
        def setup_action(self, action, payload=None):
            calls.append((action, payload))
            return {"status": "ok"}

    result = update_system(inst, "dnd5e", client=FakeClient(), fetch_manifest=lambda url: {"version": "5.4.0"})

    assert calls == [("installPackage", {"type": "system", "id": "dnd5e", "manifest": "https://example.test/dnd5e/system.json", "force": True})]
    assert result["changed"] is True
    assert result["current_version"] == "5.3.3"
    assert result["available_version"] == "5.4.0"


def test_update_system_skips_when_remote_manifest_matches(tmp_path):
    inst = instance(tmp_path)
    write_system(inst, version="5.3.3", compatibility={"minimum": "13", "verified": "13"})

    class FakeClient:
        def setup_action(self, action, payload=None):
            raise AssertionError("should not install unchanged system")

    result = update_system(
        inst,
        "dnd5e",
        client=FakeClient(),
        fetch_manifest=lambda url: {"version": "5.3.3", "compatibility": {"minimum": "13", "verified": "13"}},
    )

    assert result["changed"] is False
    assert result["current_version"] == "5.3.3"
    assert result["available_version"] == "5.3.3"


def test_update_system_requires_http_manifest_url(tmp_path):
    inst = instance(tmp_path)
    write_system(inst, manifest="file:///etc/passwd")

    with pytest.raises(SystemPackageError, match="Manifest URL must use http or https"):
        update_system(inst, "dnd5e", client=object())


def test_update_system_requires_manifest_url(tmp_path):
    inst = instance(tmp_path)
    write_system(inst, manifest="")

    with pytest.raises(SystemPackageError, match="No manifest URL"):
        update_system(inst, "dnd5e", client=object())
