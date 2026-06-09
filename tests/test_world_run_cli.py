from foundry_admin_cli.cli import run


def test_worlds_run_configures_world(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.configure_world",
        lambda instance, world_id: {
            "version": instance.version,
            "world": world_id,
            "previous_world": "old-world",
            "changed": True,
            "restart_required": True,
        },
    )

    rc = run(["worlds", "run", "module-test-dnd5e", "--json"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"world": "module-test-dnd5e"' in out
    assert '"restart_required": true' in out


def test_worlds_stop_clears_world(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.stop_world",
        lambda instance: {
            "version": instance.version,
            "world": None,
            "previous_world": "module-test-dnd5e",
            "changed": True,
            "restart_required": True,
        },
    )

    rc = run(["worlds", "stop", "--json"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"world": null' in out
    assert '"previous_world": "module-test-dnd5e"' in out


def test_worlds_run_reports_config_errors(monkeypatch, capsys):
    from foundry_admin_cli.worlds import WorldConfigError

    def fail(instance, world_id):
        raise WorldConfigError("World not found: missing")

    monkeypatch.setattr("foundry_admin_cli.cli.configure_world", fail)

    rc = run(["worlds", "run", "missing"])

    assert rc == 1
    assert "World not found: missing" in capsys.readouterr().err
