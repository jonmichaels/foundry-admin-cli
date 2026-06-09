import json

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.modules import (
    ModulePackageError,
    create_module,
    edit_module,
    list_modules,
    remove_module,
    update_module,
)


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


def write_module(inst, module_id="test-module", **extra):
    module_dir = inst.modules_dir / module_id
    module_dir.mkdir(parents=True)
    manifest = {
        "id": module_id,
        "title": "Test Module",
        "version": "1.0.0",
        "compatibility": {"minimum": "13", "verified": "13"},
        "manifest": "https://example.test/module.json",
    }
    manifest.update(extra)
    (module_dir / "module.json").write_text(json.dumps(manifest), encoding="utf-8")
    return module_dir


def test_list_modules_reports_installed_modules(tmp_path):
    inst = instance(tmp_path)
    write_module(inst)

    modules = list_modules(inst)

    assert modules == [
        {
            "id": "test-module",
            "directory_id": "test-module",
            "manifest_id": "test-module",
            "id_matches_directory": True,
            "title": "Test Module",
            "version": "1.0.0",
            "compatibility": {"minimum": "13", "verified": "13"},
            "path": str(inst.modules_dir / "test-module"),
            "manifest": "https://example.test/module.json",
            "valid": True,
            "symlink": False,
            "enabled_worlds": [],
        }
    ]


def test_list_modules_reports_symlink_status(tmp_path):
    inst = instance(tmp_path)
    source = tmp_path / "source-module"
    source.mkdir()
    (source / "module.json").write_text(json.dumps({"id": "linked", "title": "Linked", "version": "1"}), encoding="utf-8")
    inst.modules_dir.mkdir(parents=True)
    (inst.modules_dir / "linked").symlink_to(source, target_is_directory=True)

    modules = list_modules(inst)

    assert modules[0]["symlink"] is True
    assert modules[0]["id"] == "linked"


def test_list_modules_reports_invalid_manifest_without_crashing(tmp_path):
    inst = instance(tmp_path)
    bad_dir = inst.modules_dir / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "module.json").write_text("[]", encoding="utf-8")

    modules = list_modules(inst)

    assert modules[0]["valid"] is False
    assert modules[0]["error"] == "module.json root must be an object"


def test_create_module_scaffolds_minimal_project_without_symlink(tmp_path):
    inst = instance(tmp_path)
    projects_dir = tmp_path / "projects"

    result = create_module(inst, "new-module", title="New Module", projects_dir=projects_dir)

    module_dir = projects_dir / "new-module"
    assert result["changed"] is True
    assert result["path"] == str(module_dir)
    assert (module_dir / "module.json").exists()
    assert (module_dir / "scripts").is_dir()
    assert (module_dir / "templates").is_dir()
    assert (module_dir / "styles").is_dir()
    assert json.loads((module_dir / "languages" / "en.json").read_text(encoding="utf-8")) == {}
    assert (module_dir / "CLAUDE.md").exists()
    manifest = json.loads((module_dir / "module.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "new-module"
    assert manifest["title"] == "New Module"
    assert not (inst.modules_dir / "new-module").exists()


def test_create_module_can_symlink_into_foundry_data(tmp_path):
    inst = instance(tmp_path)
    projects_dir = tmp_path / "projects"

    create_module(inst, "new-module", title="New Module", projects_dir=projects_dir, symlink=True)

    assert (inst.modules_dir / "new-module").is_symlink()
    assert (inst.modules_dir / "new-module").resolve() == (projects_dir / "new-module").resolve()


def test_create_module_rejects_existing_project(tmp_path):
    inst = instance(tmp_path)
    projects_dir = tmp_path / "projects"
    (projects_dir / "new-module").mkdir(parents=True)

    with pytest.raises(ModulePackageError, match="already exists"):
        create_module(inst, "new-module", title="New Module", projects_dir=projects_dir)


def test_edit_module_updates_manifest_with_backup(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    write_module(inst)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))

    result = edit_module(inst, "test-module", title="Renamed", manifest_url="https://example.test/new.json")

    data = json.loads((inst.modules_dir / "test-module" / "module.json").read_text(encoding="utf-8"))
    assert result["changed"] is True
    assert data["title"] == "Renamed"
    assert data["manifest"] == "https://example.test/new.json"
    assert list((tmp_path / "hermes" / "backups" / "foundry-admin-cli" / "v13" / "module.json").glob("*.json"))


def test_edit_module_rejects_empty_title(tmp_path):
    inst = instance(tmp_path)
    write_module(inst)

    with pytest.raises(ModulePackageError, match="title cannot be empty"):
        edit_module(inst, "test-module", title="")


def test_update_module_uses_manifest_when_remote_differs(tmp_path):
    inst = instance(tmp_path)
    write_module(inst, manifest="https://example.test/module.json")
    calls = []

    class FakeClient:
        def setup_action(self, action, payload=None):
            calls.append((action, payload))
            return {"status": "ok"}

    result = update_module(inst, "test-module", client=FakeClient(), fetch_manifest=lambda url: {"version": "2.0.0"})

    assert calls == [("installPackage", {"type": "module", "id": "test-module", "manifest": "https://example.test/module.json", "force": True})]
    assert result["changed"] is True
    assert result["current_version"] == "1.0.0"
    assert result["available_version"] == "2.0.0"


def test_update_module_skips_when_remote_manifest_matches(tmp_path):
    inst = instance(tmp_path)
    write_module(inst)

    class FakeClient:
        def setup_action(self, action, payload=None):
            raise AssertionError("should not install unchanged module")

    result = update_module(
        inst,
        "test-module",
        client=FakeClient(),
        fetch_manifest=lambda url: {"version": "1.0.0", "compatibility": {"minimum": "13", "verified": "13"}},
    )

    assert result["changed"] is False


def test_remove_module_archives_regular_directory_by_default(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    module_dir = write_module(inst)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))

    result = remove_module(inst, "test-module")

    assert result["changed"] is True
    assert result["removed"] is False
    assert not module_dir.exists()
    assert result["archive_path"].startswith(str(tmp_path / "hermes"))


def test_remove_module_unlinks_symlink_without_deleting_source(tmp_path):
    inst = instance(tmp_path)
    source = tmp_path / "source-module"
    source.mkdir()
    (source / "module.json").write_text(json.dumps({"id": "linked", "title": "Linked", "version": "1"}), encoding="utf-8")
    inst.modules_dir.mkdir(parents=True)
    (inst.modules_dir / "linked").symlink_to(source, target_is_directory=True)

    result = remove_module(inst, "linked")

    assert result["unlinked"] is True
    assert source.exists()
    assert not (inst.modules_dir / "linked").exists()


def test_remove_module_permanent_requires_force(tmp_path):
    inst = instance(tmp_path)
    write_module(inst)

    with pytest.raises(ModulePackageError, match="Permanent remove requires --force"):
        remove_module(inst, "test-module", permanent=True)
