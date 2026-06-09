import json

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.world_modules import (
    ModuleSettingError,
    disable_world_module,
    enable_world_module,
    list_world_modules,
    set_world_modules,
)


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


class FakeTransport:
    def __init__(self, world="module-test", modules=None, settings=None, response=None):
        self.world = world
        self.modules = modules or [
            {"id": "a", "title": "A Module", "version": "1.0.0"},
            {"id": "b", "title": "B Module", "version": "2.0.0"},
        ]
        self.settings = [
            {"_id": "setting-id", "key": "core.moduleConfiguration", "value": json.dumps({"a": True, "b": False})}
        ] if settings is None else settings
        self.response = response or {"result": [{"_id": "setting-id"}]}
        self.requests = []

    def get_world_data(self, instance):
        return {"world": {"id": self.world}, "modules": self.modules, "settings": self.settings}

    def modify_setting(self, instance, *, setting_id, value):
        self.requests.append((setting_id, value))
        return self.response


def test_list_world_modules_reads_module_configuration(tmp_path):
    transport = FakeTransport()

    result = list_world_modules(instance(tmp_path), "module-test", transport=transport)

    assert result["world"] == "module-test"
    assert result["reload_required"] is False
    assert result["modules"] == [
        {"id": "a", "title": "A Module", "version": "1.0.0", "active": True},
        {"id": "b", "title": "B Module", "version": "2.0.0", "active": False},
    ]


def test_module_configuration_rejects_non_object_values(tmp_path):
    for value in ("null", None):
        transport = FakeTransport(settings=[{"_id": "setting-id", "key": "core.moduleConfiguration", "value": value}])

        try:
            list_world_modules(instance(tmp_path), "module-test", transport=transport)
        except ModuleSettingError as exc:
            assert "must be an object" in str(exc)
        else:
            raise AssertionError("expected ModuleSettingError")


def test_module_configuration_rejects_non_boolean_values(tmp_path):
    transport = FakeTransport(settings=[{"_id": "setting-id", "key": "core.moduleConfiguration", "value": json.dumps({"a": "false"})}])

    try:
        list_world_modules(instance(tmp_path), "module-test", transport=transport)
    except ModuleSettingError as exc:
        assert "must be boolean" in str(exc)
    else:
        raise AssertionError("expected ModuleSettingError")


def test_enable_world_module_sets_module_true(tmp_path):
    transport = FakeTransport()

    result = enable_world_module(instance(tmp_path), "module-test", "b", transport=transport)

    assert result["changed"] is True
    assert result["reload_required"] is True
    assert transport.requests == [("setting-id", {"a": True, "b": True})]


def test_disable_world_module_sets_module_false(tmp_path):
    transport = FakeTransport()

    result = disable_world_module(instance(tmp_path), "module-test", "a", transport=transport)

    assert result["changed"] is True
    assert result["reload_required"] is True
    assert transport.requests == [("setting-id", {"a": False, "b": False})]


def test_set_world_modules_replaces_configuration(tmp_path):
    transport = FakeTransport(modules=[{"id": "a"}, {"id": "b"}, {"id": "c"}])

    result = set_world_modules(instance(tmp_path), "module-test", ["b", "c"], transport=transport)

    assert result["changed"] is True
    assert transport.requests == [("setting-id", {"a": False, "b": True, "c": True})]


def test_set_world_modules_rejects_missing_installed_module(tmp_path):
    transport = FakeTransport(modules=[{"id": "a"}])

    try:
        set_world_modules(instance(tmp_path), "module-test", ["missing"], transport=transport)
    except ModuleSettingError as exc:
        assert "not installed" in str(exc)
    else:
        raise AssertionError("expected ModuleSettingError")


def test_set_world_modules_creates_setting_when_missing(tmp_path):
    transport = FakeTransport(settings=[])

    result = set_world_modules(instance(tmp_path), "module-test", ["a"], transport=transport)

    assert result["changed"] is True
    assert transport.requests == [(None, {"a": True, "b": False})]


def test_world_mismatch_is_rejected(tmp_path):
    transport = FakeTransport(world="other-world")

    try:
        list_world_modules(instance(tmp_path), "module-test", transport=transport)
    except ModuleSettingError as exc:
        assert "running world is other-world" in str(exc)
    else:
        raise AssertionError("expected ModuleSettingError")
