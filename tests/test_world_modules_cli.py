from foundry_admin_cli.cli import run


def test_world_modules_list_wires_world(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_world_modules",
        lambda instance, world_id: calls.append(world_id) or {"world": world_id, "modules": [], "reload_required": False},
    )

    rc = run(["game", "module", "list", "--world", "module-test", "--json"])

    assert rc == 0
    assert calls == ["module-test"]
    assert '"world": "module-test"' in capsys.readouterr().out


def test_world_modules_enable_wires_module(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.enable_world_module",
        lambda instance, world_id, module_id: calls.append((world_id, module_id))
        or {"world": world_id, "module": module_id, "changed": True, "reload_required": True},
    )

    rc = run(["game", "module", "enable", "mcp", "--world", "module-test", "--json"])

    assert rc == 0
    assert calls == [("module-test", "mcp")]
    assert '"reload_required": true' in capsys.readouterr().out


def test_world_modules_disable_wires_module(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.disable_world_module",
        lambda instance, world_id, module_id: calls.append((world_id, module_id))
        or {"world": world_id, "module": module_id, "changed": True, "reload_required": True},
    )

    rc = run(["game", "module", "disable", "mcp", "--world", "module-test", "--json"])

    assert rc == 0
    assert calls == [("module-test", "mcp")]


def test_world_modules_set_parses_comma_list(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.set_world_modules",
        lambda instance, world_id, module_ids: calls.append((world_id, module_ids))
        or {"world": world_id, "modules": module_ids, "changed": True, "reload_required": True},
    )

    rc = run(["game", "module", "set", "--world", "module-test", "--modules", "a,b, c", "--json"])

    assert rc == 0
    assert calls == [("module-test", ["a", "b", "c"])]
