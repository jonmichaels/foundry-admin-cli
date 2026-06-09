from foundry_admin_cli.cli import run


def test_world_list_outputs_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_worlds",
        lambda instance, active_world=None: [
            {
                "id": "module-test-dnd5e",
                "title": "DND Test",
                "system": "dnd5e",
                "compatibility": {},
                "path": "/tmp/worlds/module-test-dnd5e",
                "active": True,
                "configured": False,
                "valid": True,
            }
        ],
    )
    monkeypatch.setattr("foundry_admin_cli.cli.fetch_active_world", lambda instance: "module-test-dnd5e")

    rc = run(["world", "list", "--json"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"id": "module-test-dnd5e"' in out
    assert '"active": true' in out


def test_world_list_outputs_human_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_worlds",
        lambda instance, active_world=None: [
            {
                "id": "module-test-dnd5e",
                "title": "DND Test",
                "system": "dnd5e",
                "compatibility": {},
                "path": "/tmp/worlds/module-test-dnd5e",
                "active": True,
                "configured": False,
                "valid": True,
            }
        ],
    )
    monkeypatch.setattr("foundry_admin_cli.cli.fetch_active_world", lambda instance: "module-test-dnd5e")

    rc = run(["world", "list"])

    assert rc == 0
    assert "* module-test-dnd5e | DND Test | system dnd5e | active" in capsys.readouterr().out
