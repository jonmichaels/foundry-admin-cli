import json

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.world_settings import (
    GameSettingError,
    apply_mcp_bridge_settings,
    get_game_setting,
    list_game_settings,
    set_game_setting,
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
    def __init__(self, world="module-test", settings=None, modules=None):
        self.world = world
        self.settings = settings if settings is not None else [
            {"_id": "enabled-id", "key": "foundry-mcp-bridge.enabled", "value": "true"},
            {"_id": "host-id", "key": "foundry-mcp-bridge.serverHost", "value": '"foundry.example.com"'},
            {"_id": "core-id", "key": "core.editorAutosaveSecs", "value": "60"},
        ]
        self.modules = modules if modules is not None else [
            {"id": "foundry-mcp-bridge", "title": "Foundry MCP Bridge", "active": True},
            {"id": "simplefog", "title": "Simple Fog", "active": False},
        ]
        self.response_value = None
        self.requests = []

    def get_world_data(self, instance):
        return {
            "world": {"id": self.world, "system": "black-flag"},
            "system": {"id": "black-flag", "title": "Black Flag"},
            "modules": self.modules,
            "settings": self.settings,
        }

    def modify_setting(self, instance, *, setting_id, key, value):
        self.requests.append({"setting_id": setting_id, "key": key, "value": value})
        response_value = self.response_value if self.response_value is not None else value
        return {"result": [{"_id": setting_id or "new-id", "key": key, "value": json.dumps(response_value)}]}


def test_list_game_settings_reports_persisted_settings_with_categories(tmp_path):
    result = list_game_settings(instance(tmp_path), "module-test", transport=FakeTransport())

    assert result["world"] == "module-test"
    assert result["active_world"] == "module-test"
    rows = {row["qualified_key"]: row for row in result["settings"]}
    assert rows["core.editorAutosaveSecs"] == {
        "qualified_key": "core.editorAutosaveSecs",
        "namespace": "core",
        "key": "editorAutosaveSecs",
        "category": "core",
        "scope": "world",
        "config": None,
        "type": None,
        "value": 60,
        "default": None,
        "choices": None,
        "range": None,
        "requires_reload": None,
        "mutable_by_cli": True,
        "source": "persisted",
    }
    assert rows["foundry-mcp-bridge.enabled"] == {
        "qualified_key": "foundry-mcp-bridge.enabled",
        "namespace": "foundry-mcp-bridge",
        "key": "enabled",
        "category": "module",
        "scope": "world",
        "config": True,
        "type": "Boolean",
        "value": True,
        "default": True,
        "choices": None,
        "range": None,
        "requires_reload": False,
        "mutable_by_cli": True,
        "source": "known-metadata",
    }
    assert rows["foundry-mcp-bridge.serverHost"] == {
        "qualified_key": "foundry-mcp-bridge.serverHost",
        "namespace": "foundry-mcp-bridge",
        "key": "serverHost",
        "category": "module",
        "scope": "world",
        "config": True,
        "type": "String",
        "value": "[REDACTED]",
        "default": "localhost",
        "choices": None,
        "range": None,
        "requires_reload": False,
        "sensitive": True,
        "mutable_by_cli": True,
        "source": "known-metadata",
    }


def test_list_game_settings_filters_namespace_and_query(tmp_path):
    result = list_game_settings(
        instance(tmp_path),
        "module-test",
        namespace="foundry-mcp-bridge",
        query="host",
        transport=FakeTransport(),
    )

    assert [row["qualified_key"] for row in result["settings"]] == ["foundry-mcp-bridge.serverHost"]


def test_get_game_setting_returns_default_for_known_missing_mcp_setting(tmp_path):
    result = get_game_setting(
        instance(tmp_path),
        "module-test",
        "foundry-mcp-bridge.mapGenAutoStart",
        transport=FakeTransport(settings=[]),
    )

    assert result["setting"]["value"] is True
    assert result["setting"]["source"] == "known-metadata"


def test_get_game_setting_rejects_unknown_key(tmp_path):
    with pytest.raises(GameSettingError, match="setting not found"):
        get_game_setting(instance(tmp_path), "module-test", "missing.setting", transport=FakeTransport())


def test_set_game_setting_updates_existing_world_setting(tmp_path):
    transport = FakeTransport()

    result = set_game_setting(
        instance(tmp_path),
        "module-test",
        "foundry-mcp-bridge.enabled",
        False,
        transport=transport,
    )

    assert result["changed"] is True
    assert result["old_value"] is True
    assert result["new_value"] is False
    assert transport.requests == [
        {"setting_id": "enabled-id", "key": "foundry-mcp-bridge.enabled", "value": False}
    ]


def test_set_game_setting_creates_missing_known_world_setting(tmp_path):
    transport = FakeTransport(settings=[])

    result = set_game_setting(
        instance(tmp_path),
        "module-test",
        "foundry-mcp-bridge.mapGenAutoStart",
        False,
        transport=transport,
    )

    assert result["changed"] is True
    assert result["reload_required"] is False
    assert transport.requests == [
        {"setting_id": None, "key": "foundry-mcp-bridge.mapGenAutoStart", "value": False}
    ]


def test_set_game_setting_rejects_client_scope(tmp_path):
    with pytest.raises(GameSettingError, match="client-scoped"):
        set_game_setting(instance(tmp_path), "module-test", "core.maxFPS", 30, transport=FakeTransport())


def test_set_game_setting_rejects_unknown_setting(tmp_path):
    with pytest.raises(GameSettingError, match="setting not found"):
        set_game_setting(instance(tmp_path), "module-test", "unknown.value", 1, transport=FakeTransport())


def test_set_game_setting_redacts_env_sourced_values(tmp_path):
    transport = FakeTransport(settings=[])

    result = set_game_setting(
        instance(tmp_path),
        "module-test",
        "foundry-mcp-bridge.serverHost",
        "secret-host.example",
        value_source="env",
        transport=transport,
    )

    assert result["new_value"] == "[REDACTED]"
    assert result["old_value"] == "[REDACTED]"
    assert "socket_response" not in result
    assert transport.requests[0]["value"] == "secret-host.example"


def test_apply_mcp_bridge_settings_sets_required_values(tmp_path):
    transport = FakeTransport(settings=[])

    result = apply_mcp_bridge_settings(
        instance(tmp_path),
        "module-test",
        server_host="foundry.example.com",
        transport=transport,
    )

    assert [change["qualified_key"] for change in result["changes"]] == [
        "foundry-mcp-bridge.enabled",
        "foundry-mcp-bridge.serverHost",
        "foundry-mcp-bridge.mapGenAutoStart",
    ]
    assert [request["value"] for request in transport.requests] == [True, "foundry.example.com", False]
    assert result["reload_required"] is False


def test_apply_mcp_bridge_settings_requires_active_bridge_module(tmp_path):
    transport = FakeTransport(modules=[{"id": "foundry-mcp-bridge", "active": False}])

    with pytest.raises(GameSettingError, match="not active"):
        apply_mcp_bridge_settings(
            instance(tmp_path),
            "module-test",
            server_host="foundry.example.com",
            transport=transport,
        )


def test_world_mismatch_is_rejected(tmp_path):
    with pytest.raises(GameSettingError, match="running world is other"):
        list_game_settings(instance(tmp_path), "module-test", transport=FakeTransport(world="other"))


def test_game_settings_require_local_instance(tmp_path):
    inst = FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
        mode="http-only",
    )

    with pytest.raises(Exception, match="requires local"):
        list_game_settings(inst, "module-test", transport=FakeTransport())
