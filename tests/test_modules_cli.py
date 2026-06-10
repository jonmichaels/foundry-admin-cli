from foundry_admin_cli.cli import run


def test_module_list_calls_list_modules(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_modules",
        lambda instance: [{"id": "m", "title": "M", "version": "1", "valid": True, "symlink": False}],
    )

    rc = run(["module", "list", "--json"])

    assert rc == 0
    assert '"id": "m"' in capsys.readouterr().out


def test_module_install_uses_admin_client(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())

    def fake_install(instance, *, package_type, manifest=None, package_id=None, client=None):
        calls.append((package_type, manifest, package_id, isinstance(client, FakeClient)))
        return {"type": package_type, "manifest": manifest, "changed": True}

    monkeypatch.setattr("foundry_admin_cli.cli.install_package", fake_install)

    rc = run(["module", "install", "https://example.test/module.json", "--id", "m", "--json"])

    assert rc == 0
    assert calls == [("module", "https://example.test/module.json", "m", True)]
    assert '"changed": true' in capsys.readouterr().out


def test_module_install_accepts_package_id(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())

    def fake_install(instance, *, package_type, manifest=None, package_id=None, client=None):
        calls.append((package_type, manifest, package_id, isinstance(client, FakeClient)))
        return {"type": package_type, "id": package_id, "manifest": "https://example.test/tidy/module.json", "changed": True}

    monkeypatch.setattr("foundry_admin_cli.cli.install_package", fake_install)

    rc = run(["module", "install", "tidy5e-sheet", "--json"])

    assert rc == 0
    assert calls == [("module", None, "tidy5e-sheet", True)]
    assert '"id": "tidy5e-sheet"' in capsys.readouterr().out


def test_module_library_search_wires_query(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())
    monkeypatch.setattr(
        "foundry_admin_cli.cli.get_package_library",
        lambda instance, *, package_type, query=None, client=None: calls.append((package_type, query, isinstance(client, FakeClient)))
        or {"type": package_type, "packages": [{"id": "tidy5e-sheet"}]},
    )

    rc = run(["module", "library", "search", "tidy", "--json"])

    assert rc == 0
    assert calls == [("module", "tidy", True)]
    assert '"id": "tidy5e-sheet"' in capsys.readouterr().out


def test_module_library_show_wires_package_id(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())
    monkeypatch.setattr(
        "foundry_admin_cli.cli.resolve_package_from_library",
        lambda instance, *, package_type, package_id, client=None: calls.append((package_type, package_id, isinstance(client, FakeClient)))
        or {"id": package_id, "manifest": "https://example.test/tidy/module.json"},
    )

    rc = run(["module", "library", "show", "tidy5e-sheet", "--json"])

    assert rc == 0
    assert calls == [("module", "tidy5e-sheet", True)]
    assert '"manifest": "https://example.test/tidy/module.json"' in capsys.readouterr().out


def test_module_update_uses_admin_client(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())
    monkeypatch.setattr(
        "foundry_admin_cli.cli.update_module",
        lambda instance, module_id, client=None: calls.append((module_id, isinstance(client, FakeClient)))
        or {"module": module_id, "changed": True},
    )

    rc = run(["module", "update", "m", "--json"])

    assert rc == 0
    assert calls == [("m", True)]
    assert '"module": "m"' in capsys.readouterr().out


def test_module_create_wires_arguments(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.create_module",
        lambda instance, module_id, **kwargs: calls.append((module_id, kwargs))
        or {"module": module_id, "changed": True},
    )

    rc = run(["module", "create", "new-module", "--title", "New Module", "--projects-dir", "/tmp/custom-projects", "--symlink", "--json"])

    assert rc == 0
    assert calls[0][0] == "new-module"
    assert calls[0][1]["title"] == "New Module"
    assert str(calls[0][1]["projects_dir"]) == "/tmp/custom-projects"
    assert calls[0][1]["symlink"] is True
    assert '"module": "new-module"' in capsys.readouterr().out


def test_module_edit_wires_manifest_fields(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.edit_module",
        lambda instance, module_id, **kwargs: calls.append((module_id, kwargs))
        or {"module": module_id, "changed": True},
    )

    rc = run(["module", "edit", "m", "--title", "M2", "--manifest", "https://example.test/m.json", "--json"])

    assert rc == 0
    assert calls == [("m", {"title": "M2", "manifest_url": "https://example.test/m.json"})]
    assert '"changed": true' in capsys.readouterr().out


def test_module_remove_wires_flags(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.remove_module",
        lambda instance, module_id, permanent=False, force=False: calls.append((module_id, permanent, force))
        or {"module": module_id, "changed": True, "removed": True},
    )

    rc = run(["module", "remove", "m", "--permanent", "--force", "--json"])

    assert rc == 0
    assert calls == [("m", True, True)]
    assert '"removed": true' in capsys.readouterr().out
