from foundry_admin_cli.cli import run


def test_modules_list_calls_list_modules(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_modules",
        lambda instance: [{"id": "m", "title": "M", "version": "1", "valid": True, "symlink": False}],
    )

    rc = run(["modules", "list", "--json"])

    assert rc == 0
    assert '"id": "m"' in capsys.readouterr().out


def test_modules_install_uses_admin_client(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())

    def fake_install(instance, *, package_type, manifest, package_id=None, client=None):
        calls.append((package_type, manifest, package_id, isinstance(client, FakeClient)))
        return {"type": package_type, "manifest": manifest, "changed": True}

    monkeypatch.setattr("foundry_admin_cli.cli.install_package", fake_install)

    rc = run(["modules", "install", "https://example.test/module.json", "--id", "m", "--json"])

    assert rc == 0
    assert calls == [("module", "https://example.test/module.json", "m", True)]
    assert '"changed": true' in capsys.readouterr().out


def test_modules_update_uses_admin_client(monkeypatch, capsys):
    calls = []

    class FakeClient:
        pass

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", lambda instance: FakeClient())
    monkeypatch.setattr(
        "foundry_admin_cli.cli.update_module",
        lambda instance, module_id, client=None: calls.append((module_id, isinstance(client, FakeClient)))
        or {"module": module_id, "changed": True},
    )

    rc = run(["modules", "update", "m", "--json"])

    assert rc == 0
    assert calls == [("m", True)]
    assert '"module": "m"' in capsys.readouterr().out


def test_modules_create_wires_arguments(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.create_module",
        lambda instance, module_id, **kwargs: calls.append((module_id, kwargs))
        or {"module": module_id, "changed": True},
    )

    rc = run(["modules", "create", "new-module", "--title", "New Module", "--projects-dir", "/tmp/custom-projects", "--symlink", "--json"])

    assert rc == 0
    assert calls[0][0] == "new-module"
    assert calls[0][1]["title"] == "New Module"
    assert str(calls[0][1]["projects_dir"]) == "/tmp/custom-projects"
    assert calls[0][1]["symlink"] is True
    assert '"module": "new-module"' in capsys.readouterr().out


def test_modules_edit_wires_manifest_fields(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.edit_module",
        lambda instance, module_id, **kwargs: calls.append((module_id, kwargs))
        or {"module": module_id, "changed": True},
    )

    rc = run(["modules", "edit", "m", "--title", "M2", "--manifest", "https://example.test/m.json", "--json"])

    assert rc == 0
    assert calls == [("m", {"title": "M2", "manifest_url": "https://example.test/m.json"})]
    assert '"changed": true' in capsys.readouterr().out


def test_modules_remove_wires_flags(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.remove_module",
        lambda instance, module_id, permanent=False, force=False: calls.append((module_id, permanent, force))
        or {"module": module_id, "changed": True, "removed": True},
    )

    rc = run(["modules", "remove", "m", "--permanent", "--force", "--json"])

    assert rc == 0
    assert calls == [("m", True, True)]
    assert '"removed": true' in capsys.readouterr().out
