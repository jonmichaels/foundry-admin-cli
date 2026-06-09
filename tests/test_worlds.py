import json

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.worlds import list_worlds


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
    (world_dir / "world.json").write_text(json.dumps(data))


def test_list_worlds_reads_world_json_and_marks_configured(tmp_path):
    inst = instance(tmp_path)
    (inst.options_path.parent).mkdir(parents=True)
    inst.options_path.write_text(json.dumps({"world": "module-test-black-flag"}))
    write_world(
        inst.data_dir,
        "module-test-black-flag",
        {"id": "module-test-black-flag", "title": "BF Test", "system": "black-flag", "compatibility": {"minimum": "13"}},
    )
    write_world(inst.data_dir, "module-test-dnd5e", {"title": "DND Test", "system": "dnd5e"})

    worlds = list_worlds(inst, active_world="module-test-dnd5e")

    assert [w["id"] for w in worlds] == ["module-test-black-flag", "module-test-dnd5e"]
    bf = worlds[0]
    dnd = worlds[1]
    assert bf["title"] == "BF Test"
    assert bf["system"] == "black-flag"
    assert bf["configured"] is True
    assert bf["active"] is False
    assert bf["compatibility"] == {"minimum": "13"}
    assert dnd["id"] == "module-test-dnd5e"
    assert dnd["active"] is True


def test_list_worlds_reports_invalid_world_json_without_crashing(tmp_path):
    inst = instance(tmp_path)
    world_dir = inst.worlds_dir / "broken-world"
    world_dir.mkdir(parents=True)
    (world_dir / "world.json").write_text("{not json")

    worlds = list_worlds(inst)

    assert worlds == [
        {
            "id": "broken-world",
            "directory_id": "broken-world",
            "manifest_id": None,
            "title": None,
            "system": None,
            "compatibility": {},
            "path": str(world_dir),
            "active": False,
            "configured": False,
            "valid": False,
            "error": "Invalid JSON in world.json",
        }
    ]


def test_list_worlds_reports_manifest_id_mismatch(tmp_path):
    inst = instance(tmp_path)
    write_world(inst.data_dir, "dir-id", {"id": "manifest-id", "title": "Mismatch", "system": "dnd5e"})

    worlds = list_worlds(inst)

    assert worlds[0]["id"] == "manifest-id"
    assert worlds[0]["directory_id"] == "dir-id"
    assert worlds[0]["manifest_id"] == "manifest-id"
    assert worlds[0]["id_matches_directory"] is False


def test_list_worlds_reports_non_object_world_json_without_crashing(tmp_path):
    inst = instance(tmp_path)
    world_dir = inst.worlds_dir / "array-world"
    world_dir.mkdir(parents=True)
    (world_dir / "world.json").write_text("[]")

    worlds = list_worlds(inst)

    assert worlds[0]["valid"] is False
    assert worlds[0]["error"] == "world.json root must be an object"


def test_list_worlds_reports_non_string_manifest_id_without_crashing(tmp_path):
    inst = instance(tmp_path)
    write_world(inst.data_dir, "bad-id", {"id": [], "title": "Bad", "system": "dnd5e"})

    worlds = list_worlds(inst)

    assert worlds[0]["valid"] is False
    assert worlds[0]["error"] == "world.json id must be a string"


def test_list_worlds_matches_active_and_configured_by_manifest_id(tmp_path):
    inst = instance(tmp_path)
    (inst.options_path.parent).mkdir(parents=True)
    inst.options_path.write_text(json.dumps({"world": "manifest-id"}))
    write_world(inst.data_dir, "dir-id", {"id": "manifest-id", "title": "Mismatch", "system": "dnd5e"})

    worlds = list_worlds(inst, active_world="manifest-id")

    assert worlds[0]["active"] is True
    assert worlds[0]["configured"] is True


def test_list_worlds_returns_empty_list_when_worlds_dir_missing(tmp_path):
    assert list_worlds(instance(tmp_path)) == []
