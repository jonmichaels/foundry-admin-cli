from foundry_admin_cli.cli import run


def test_worlds_edit_updates_title_and_system(monkeypatch, capsys):
    calls = []

    def fake_edit(instance, world_id, **kwargs):
        calls.append((world_id, kwargs))
        return {"version": instance.version, "world": world_id, "changed": True, "fields": ["system", "title"]}

    monkeypatch.setattr("foundry_admin_cli.cli.edit_world", fake_edit)

    rc = run(["worlds", "edit", "module-test-dnd5e", "--title", "New Title", "--system", "black-flag", "--json"])

    assert rc == 0
    assert calls == [("module-test-dnd5e", {"title": "New Title", "system": "black-flag"})]
    out = capsys.readouterr().out
    assert '"world": "module-test-dnd5e"' in out
    assert '"fields": [' in out


def test_worlds_edit_reports_config_errors(monkeypatch, capsys):
    from foundry_admin_cli.worlds import WorldConfigError

    def fail(instance, world_id, **kwargs):
        raise WorldConfigError("No fields provided to update")

    monkeypatch.setattr("foundry_admin_cli.cli.edit_world", fail)

    rc = run(["worlds", "edit", "module-test-dnd5e"])

    assert rc == 1
    assert "No fields provided" in capsys.readouterr().err
