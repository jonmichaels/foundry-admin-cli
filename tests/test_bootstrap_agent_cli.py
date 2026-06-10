from foundry_admin_cli import cli


def test_bootstrap_agent_parser_dispatches(monkeypatch, tmp_path, capsys):
    captured = {}

    def fake_get_instance(version, *, config):
        captured["version"] = version
        return object()

    def fake_bootstrap_agent(instance, **kwargs):
        captured.update(kwargs)
        return {"version": "v13", "world": kwargs["world_id"], "verified": True, "steps": []}

    monkeypatch.setattr(cli, "get_instance", fake_get_instance)
    monkeypatch.setattr(cli, "bootstrap_agent", fake_bootstrap_agent)

    assert cli.run([
        "--version",
        "v13",
        "bootstrap-agent",
        "--world",
        "agent-world",
        "--gm-user",
        "Gamemaster",
        "--allow-empty-password",
        "--admin-password-env",
        "FOUNDRY_ADMIN_PASSWORD",
        "--license-env",
        "FOUNDRY_LICENSE",
        "--mcp-server-host-env",
        "FOUNDRY_MCP_BRIDGE_HOST",
        "--json",
    ]) == 0

    assert captured["version"] == "v13"
    assert captured["world_id"] == "agent-world"
    assert captured["gm_user"] == "Gamemaster"
    assert captured["gm_password_env"] is None
    assert captured["allow_empty_password"] is True
    assert captured["admin_password_env"] == "FOUNDRY_ADMIN_PASSWORD"
    assert captured["license_env"] == "FOUNDRY_LICENSE"
    assert captured["mcp_manifest_url"] == "https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json"
    assert captured["mcp_server_host_env"] == "FOUNDRY_MCP_BRIDGE_HOST"
    assert '"verified": true' in capsys.readouterr().out


def test_bootstrap_agent_parser_accepts_manifest_override(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "get_instance", lambda version, *, config: object())
    monkeypatch.setattr(cli, "bootstrap_agent", lambda instance, **kwargs: captured.update(kwargs) or {"ok": True})

    assert cli.run([
        "bootstrap-agent",
        "--world",
        "agent-world",
        "--gm-user",
        "Agent",
        "--gm-password-env",
        "FOUNDRY_USER_PASSWORD",
        "--admin-password-env",
        "FOUNDRY_ADMIN_PASSWORD",
        "--mcp-manifest-url",
        "https://example.test/module.json",
        "--mcp-server-host-env",
        "FOUNDRY_MCP_BRIDGE_HOST",
    ]) == 0

    assert captured["mcp_manifest_url"] == "https://example.test/module.json"
    assert captured["allow_empty_password"] is False
