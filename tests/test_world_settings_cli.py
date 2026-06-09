import pytest

from foundry_admin_cli.cli import run


def test_game_settings_list_wires_filters(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_game_settings",
        lambda instance, world_id, namespace=None, category=None, query=None, config_only=False, world_only=False: calls.append(
            (world_id, namespace, category, query, config_only, world_only)
        )
        or {"world": world_id, "settings": []},
    )

    rc = run([
        "game",
        "settings",
        "list",
        "--world",
        "module-test",
        "--namespace",
        "foundry-mcp-bridge",
        "--category",
        "module",
        "--query",
        "host",
        "--config-only",
        "--world-only",
        "--json",
    ])

    assert rc == 0
    assert calls == [("module-test", "foundry-mcp-bridge", "module", "host", True, True)]
    assert '"settings": []' in capsys.readouterr().out


def test_game_settings_get_wires_key(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.get_game_setting",
        lambda instance, world_id, qualified_key: calls.append((world_id, qualified_key))
        or {"world": world_id, "setting": {"qualified_key": qualified_key}},
    )

    rc = run(["game", "settings", "get", "--world", "module-test", "foundry-mcp-bridge.enabled", "--json"])

    assert rc == 0
    assert calls == [("module-test", "foundry-mcp-bridge.enabled")]


def test_game_settings_set_parses_json_value(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.set_game_setting",
        lambda instance, world_id, qualified_key, value, value_source="json": calls.append(
            (world_id, qualified_key, value, value_source)
        )
        or {"world": world_id, "qualified_key": qualified_key, "changed": True},
    )

    rc = run(["game", "settings", "set", "--world", "module-test", "foundry-mcp-bridge.enabled", "--value-json", "true", "--json"])

    assert rc == 0
    assert calls == [("module-test", "foundry-mcp-bridge.enabled", True, "json")]


def test_game_settings_set_reads_env_value(monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("FVTT_SETTING_VALUE", "foundry.example.com")
    monkeypatch.setattr(
        "foundry_admin_cli.cli.set_game_setting",
        lambda instance, world_id, qualified_key, value, value_source="json": calls.append(
            (world_id, qualified_key, value, value_source)
        )
        or {"world": world_id, "qualified_key": qualified_key, "changed": True, "new_value": "[REDACTED]"},
    )

    rc = run([
        "game",
        "settings",
        "set",
        "--world",
        "module-test",
        "foundry-mcp-bridge.serverHost",
        "--value-env",
        "FVTT_SETTING_VALUE",
        "--json",
    ])

    assert rc == 0
    assert calls == [("module-test", "foundry-mcp-bridge.serverHost", "foundry.example.com", "env")]
    assert "foundry.example.com" not in capsys.readouterr().out


def test_game_settings_set_human_output_does_not_leak_env_value(monkeypatch, capsys):
    monkeypatch.setenv("FVTT_SETTING_VALUE", "private-host.example")
    monkeypatch.setattr(
        "foundry_admin_cli.cli.set_game_setting",
        lambda instance, world_id, qualified_key, value, value_source="json": {
            "world": world_id,
            "qualified_key": qualified_key,
            "changed": True,
            "old_value": "[REDACTED]",
            "new_value": "[REDACTED]",
        },
    )

    rc = run([
        "game",
        "settings",
        "set",
        "--world",
        "module-test",
        "foundry-mcp-bridge.serverHost",
        "--value-env",
        "FVTT_SETTING_VALUE",
    ])

    assert rc == 0
    assert "private-host.example" not in capsys.readouterr().out


def test_game_settings_set_requires_one_value_source(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run([
            "game",
            "settings",
            "set",
            "--world",
            "module-test",
            "foundry-mcp-bridge.enabled",
            "--value-json",
            "true",
            "--value-env",
            "FVTT_SETTING_VALUE",
        ])

    assert excinfo.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_game_settings_apply_mcp_bridge_wires_host_env(monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("MCP_HOST", "foundry.example.com")
    monkeypatch.setattr(
        "foundry_admin_cli.cli.apply_mcp_bridge_settings",
        lambda instance, world_id, server_host: calls.append((world_id, server_host))
        or {"world": world_id, "changes": [], "reload_required": False},
    )

    rc = run([
        "game",
        "settings",
        "apply-mcp-bridge",
        "--world",
        "module-test",
        "--server-host-env",
        "MCP_HOST",
        "--json",
    ])

    assert rc == 0
    assert calls == [("module-test", "foundry.example.com")]
