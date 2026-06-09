from foundry_admin_cli.cli import run


def test_worlds_delete_archives_by_default(monkeypatch, capsys):
    calls = []

    def fake_delete(instance, world_id, **kwargs):
        calls.append((world_id, kwargs))
        return {
            "version": instance.version,
            "world": world_id,
            "changed": True,
            "deleted": False,
            "archive_path": "/tmp/archive/fvtt-cli-smoke",
        }

    monkeypatch.setattr("foundry_admin_cli.cli.delete_world", fake_delete)

    rc = run(["worlds", "delete", "fvtt-cli-smoke", "--json"])

    assert rc == 0
    assert calls == [("fvtt-cli-smoke", {"permanent": False, "force": False})]
    out = capsys.readouterr().out
    assert '"deleted": false' in out
    assert '"archive_path": "/tmp/archive/fvtt-cli-smoke"' in out


def test_worlds_delete_passes_permanent_and_force(monkeypatch, capsys):
    calls = []

    def fake_delete(instance, world_id, **kwargs):
        calls.append((world_id, kwargs))
        return {"version": instance.version, "world": world_id, "changed": True, "deleted": True, "archive_path": None}

    monkeypatch.setattr("foundry_admin_cli.cli.delete_world", fake_delete)

    rc = run(["worlds", "delete", "fvtt-cli-smoke", "--permanent", "--force", "--json"])

    assert rc == 0
    assert calls == [("fvtt-cli-smoke", {"permanent": True, "force": True})]
    assert '"deleted": true' in capsys.readouterr().out


def test_worlds_delete_reports_config_errors(monkeypatch, capsys):
    from foundry_admin_cli.worlds import WorldConfigError

    def fail(instance, world_id, **kwargs):
        raise WorldConfigError("Permanent delete requires --force")

    monkeypatch.setattr("foundry_admin_cli.cli.delete_world", fail)

    rc = run(["worlds", "delete", "fvtt-cli-smoke", "--permanent"])

    assert rc == 1
    assert "Permanent delete requires --force" in capsys.readouterr().err
