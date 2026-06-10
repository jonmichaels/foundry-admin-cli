from foundry_admin_cli.cli import run


def test_game_permission_audit_wires_world_and_type(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.audit_permissions",
        lambda instance, world_id, document_type=None: calls.append((world_id, document_type))
        or {"world": world_id, "documents": {document_type: []}},
    )

    rc = run(["game", "permission", "audit", "--world", "module-test", "--type", "actor", "--json"])

    assert rc == 0
    assert calls == [("module-test", "actor")]
    assert '"world": "module-test"' in capsys.readouterr().out


def test_game_permission_set_wires_document_user_and_level(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.set_document_permission",
        lambda instance, world_id, *, document_type, document, user, level: calls.append(
            (world_id, document_type, document, user, level)
        )
        or {"world": world_id, "changed": True, "reload_required": False},
    )

    rc = run([
        "game",
        "permission",
        "set",
        "--world",
        "module-test",
        "--type",
        "journal",
        "--document",
        "Quest Log",
        "--user",
        "Player One",
        "--level",
        "observer",
        "--json",
    ])

    assert rc == 0
    assert calls == [("module-test", "journal", "Quest Log", "Player One", "observer")]
    assert '"changed": true' in capsys.readouterr().out


def test_game_permission_export_wires_world_and_type(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.export_permissions",
        lambda instance, world_id, document_type=None: calls.append((world_id, document_type))
        or {"world": world_id, "export_version": 1, "documents": {"scene": []}},
    )

    rc = run(["game", "permission", "export", "--world", "module-test", "--type", "scene", "--json"])

    assert rc == 0
    assert calls == [("module-test", "scene")]
    assert '"export_version": 1' in capsys.readouterr().out
