from foundry_admin_cli.cli import run


def test_systems_list_calls_list_systems(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_systems",
        lambda instance: [{"id": "dnd5e", "title": "D&D 5e", "version": "5.3.3", "valid": True, "worlds": []}],
    )

    rc = run(["systems", "list", "--json"])

    assert rc == 0
    assert '"id": "dnd5e"' in capsys.readouterr().out


def test_systems_install_uses_admin_client(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())

    def fake_install(instance, *, package_type, manifest, package_id=None, client=None):
        calls.append((package_type, manifest, package_id, isinstance(client, FakeClient)))
        return {"type": package_type, "manifest": manifest, "changed": True}

    monkeypatch.setattr("foundry_admin_cli.cli.install_package", fake_install)

    rc = run(["systems", "install", "https://example.test/system.json", "--json"])

    assert rc == 0
    assert calls == [("system", "https://example.test/system.json", None, True)]
    assert '"changed": true' in capsys.readouterr().out


def test_systems_update_uses_admin_client(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())
    monkeypatch.setattr(
        "foundry_admin_cli.cli.update_system",
        lambda instance, system_id, client=None: calls.append((system_id, isinstance(client, FakeClient)))
        or {"system": system_id, "changed": True},
    )

    rc = run(["systems", "update", "dnd5e", "--json"])

    assert rc == 0
    assert calls == [("dnd5e", True)]
    assert '"system": "dnd5e"' in capsys.readouterr().out


def test_systems_remove_wires_flags(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.remove_system",
        lambda instance, system_id, permanent=False, force=False: calls.append((system_id, permanent, force))
        or {"system": system_id, "changed": True, "removed": True},
    )

    rc = run(["systems", "remove", "dnd5e", "--permanent", "--force", "--json"])

    assert rc == 0
    assert calls == [("dnd5e", True, True)]
    assert '"removed": true' in capsys.readouterr().out
