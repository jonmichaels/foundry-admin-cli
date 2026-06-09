from foundry_admin_cli.cli import run


def test_worlds_create_wires_cli_arguments(monkeypatch, capsys):
    calls = []

    def fake_create(instance, world_id, **kwargs):
        calls.append((world_id, kwargs))
        return {"version": instance.version, "world": world_id, "changed": True, "path": "/tmp/world"}

    monkeypatch.setattr("foundry_admin_cli.cli.create_world", fake_create)

    rc = run(["worlds", "create", "fvtt-cli-smoke", "--title", "Smoke World", "--system", "dnd5e", "--json"])

    assert rc == 0
    assert calls == [("fvtt-cli-smoke", {"title": "Smoke World", "system": "dnd5e"})]
    out = capsys.readouterr().out
    assert '"world": "fvtt-cli-smoke"' in out


def test_worlds_create_reports_config_errors(monkeypatch, capsys):
    from foundry_admin_cli.worlds import WorldConfigError

    def fail(instance, world_id, **kwargs):
        raise WorldConfigError("System not found: dnd5e")

    monkeypatch.setattr("foundry_admin_cli.cli.create_world", fail)

    rc = run(["worlds", "create", "fvtt-cli-smoke", "--title", "Smoke", "--system", "dnd5e"])

    assert rc == 1
    assert "System not found: dnd5e" in capsys.readouterr().err
