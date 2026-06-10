from foundry_admin_cli.cli import run


def test_backup_list_wires_filters(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, instance):
            pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", FakeClient)
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_backups",
        lambda *, client, backup_type=None, package_id=None: calls.append((isinstance(client, FakeClient), backup_type, package_id))
        or {"count": 0, "backups": []},
    )

    rc = run(["backup", "list", "--type", "world", "--package-id", "my-world", "--json"])

    assert rc == 0
    assert calls == [(True, "world", "my-world")]
    assert '"count": 0' in capsys.readouterr().out


def test_backup_create_wires_type_package_and_note(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, instance):
            pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", FakeClient)
    monkeypatch.setattr(
        "foundry_admin_cli.cli.create_backup",
        lambda *, client, backup_type, package_id, note="": calls.append((backup_type, package_id, note))
        or {"created": True, "backup": {"id": "world.my-world.2026-06-09.1"}},
    )

    rc = run(["backup", "create", "--type", "world", "--package-id", "my-world", "--note", "before", "--json"])

    assert rc == 0
    assert calls == [("world", "my-world", "before")]
    assert '"created": true' in capsys.readouterr().out


def test_backup_snapshot_wires_note(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, instance):
            pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", FakeClient)
    monkeypatch.setattr(
        "foundry_admin_cli.cli.create_snapshot",
        lambda *, client, note="": calls.append(note) or {"created": True, "snapshot": {"id": "snapshot.2026-06-09.1"}},
    )

    rc = run(["backup", "snapshot", "--note", "before update", "--json"])

    assert rc == 0
    assert calls == ["before update"]
    assert '"snapshot"' in capsys.readouterr().out


def test_backup_restore_wires_force(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, instance):
            pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", FakeClient)
    monkeypatch.setattr(
        "foundry_admin_cli.cli.restore_backup",
        lambda *, client, backup_id, force=False: calls.append((backup_id, force))
        or {"restored": True, "backup": {"id": backup_id}},
    )

    rc = run(["backup", "restore", "world.my-world.2026-06-09.1", "--force", "--json"])

    assert rc == 0
    assert calls == [("world.my-world.2026-06-09.1", True)]
    assert '"restored": true' in capsys.readouterr().out


def test_backup_delete_snapshot_wires_force(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, instance):
            pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", FakeClient)
    monkeypatch.setattr(
        "foundry_admin_cli.cli.delete_snapshot",
        lambda *, client, snapshot_id, force=False: calls.append((snapshot_id, force))
        or {"deleted": True, "snapshot": {"id": snapshot_id}},
    )

    rc = run(["backup", "delete-snapshot", "snapshot.2026-06-09.1", "--force", "--json"])

    assert rc == 0
    assert calls == [("snapshot.2026-06-09.1", True)]
    assert '"deleted": true' in capsys.readouterr().out
