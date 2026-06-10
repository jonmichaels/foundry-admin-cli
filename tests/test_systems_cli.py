from foundry_admin_cli.cli import run


def test_system_list_calls_list_systems(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_systems",
        lambda instance: [{"id": "dnd5e", "title": "D&D 5e", "version": "5.3.3", "valid": True, "worlds": []}],
    )

    rc = run(["system", "list", "--json"])

    assert rc == 0
    assert '"id": "dnd5e"' in capsys.readouterr().out


def test_system_install_uses_admin_client(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())

    def fake_install(instance, *, package_type, manifest=None, package_id=None, client=None):
        calls.append((package_type, manifest, package_id, isinstance(client, FakeClient)))
        return {"type": package_type, "manifest": manifest, "changed": True}

    monkeypatch.setattr("foundry_admin_cli.cli.install_package", fake_install)

    rc = run(["system", "install", "https://example.test/system.json", "--json"])

    assert rc == 0
    assert calls == [("system", "https://example.test/system.json", None, True)]
    assert '"changed": true' in capsys.readouterr().out


def test_system_install_accepts_package_id(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())

    def fake_install(instance, *, package_type, manifest=None, package_id=None, client=None):
        calls.append((package_type, manifest, package_id, isinstance(client, FakeClient)))
        return {"type": package_type, "id": package_id, "manifest": "https://example.test/dnd5e/system.json", "changed": True}

    monkeypatch.setattr("foundry_admin_cli.cli.install_package", fake_install)

    rc = run(["system", "install", "dnd5e", "--json"])

    assert rc == 0
    assert calls == [("system", None, "dnd5e", True)]
    assert '"id": "dnd5e"' in capsys.readouterr().out


def test_system_library_search_wires_query(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())
    monkeypatch.setattr(
        "foundry_admin_cli.cli.get_package_library",
        lambda instance, *, package_type, query=None, client=None: calls.append((package_type, query, isinstance(client, FakeClient)))
        or {"type": package_type, "packages": [{"id": "dnd5e"}]},
    )

    rc = run(["system", "library", "search", "dragon", "--json"])

    assert rc == 0
    assert calls == [("system", "dragon", True)]
    assert '"id": "dnd5e"' in capsys.readouterr().out


def test_system_library_show_wires_package_id(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())
    monkeypatch.setattr(
        "foundry_admin_cli.cli.resolve_package_from_library",
        lambda instance, *, package_type, package_id, client=None: calls.append((package_type, package_id, isinstance(client, FakeClient)))
        or {"id": package_id, "manifest": "https://example.test/dnd5e/system.json"},
    )

    rc = run(["system", "library", "show", "dnd5e", "--json"])

    assert rc == 0
    assert calls == [("system", "dnd5e", True)]
    assert '"manifest": "https://example.test/dnd5e/system.json"' in capsys.readouterr().out


def test_system_install_rejects_non_http_url_before_library_lookup(monkeypatch, capsys):
    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())

    rc = run(["system", "install", "file:///etc/passwd", "--json"])

    assert rc == 1
    assert "Manifest URL must use http or https" in capsys.readouterr().err


def test_system_update_uses_admin_client(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())
    monkeypatch.setattr(
        "foundry_admin_cli.cli.update_system",
        lambda instance, system_id, client=None: calls.append((system_id, isinstance(client, FakeClient)))
        or {"system": system_id, "changed": True},
    )

    rc = run(["system", "update", "dnd5e", "--json"])

    assert rc == 0
    assert calls == [("dnd5e", True)]
    assert '"system": "dnd5e"' in capsys.readouterr().out


def test_system_remove_wires_flags(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.remove_system",
        lambda instance, system_id, permanent=False, force=False: calls.append((system_id, permanent, force))
        or {"system": system_id, "changed": True, "removed": True},
    )

    rc = run(["system", "remove", "dnd5e", "--permanent", "--force", "--json"])

    assert rc == 0
    assert calls == [("dnd5e", True, True)]
    assert '"removed": true' in capsys.readouterr().out
