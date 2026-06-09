from foundry_admin_cli.cli import run


def test_game_user_list_wires_world(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.list_game_users",
        lambda instance, world_id: calls.append(world_id) or {"world": world_id, "users": []},
    )

    rc = run(["game", "user", "list", "--world", "module-test", "--json"])

    assert rc == 0
    assert calls == ["module-test"]
    assert '"users": []' in capsys.readouterr().out


def test_game_user_create_reads_optional_password(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("foundry_admin_cli.cli.read_secret_from_env", lambda name, env_file=None: "pw")
    monkeypatch.setattr(
        "foundry_admin_cli.cli.create_game_user",
        lambda instance, world_id, *, name, role, password=None: calls.append((world_id, name, role, password))
        or {"world": world_id, "created": True, "user": {"name": name}},
    )

    rc = run([
        "game", "user", "create", "--world", "module-test", "--name", "Scout", "--role", "Trusted Player", "--password-env", "USER_PW", "--json"
    ])

    assert rc == 0
    assert calls == [("module-test", "Scout", "Trusted Player", "pw")]
    assert "pw" not in capsys.readouterr().out


def test_game_user_set_password_reads_secret(monkeypatch):
    calls = []
    monkeypatch.setattr("foundry_admin_cli.cli.read_secret_from_env", lambda name, env_file=None: "pw")
    monkeypatch.setattr(
        "foundry_admin_cli.cli.set_game_user_password",
        lambda instance, world_id, user_id, password: calls.append((world_id, user_id, password))
        or {"world": world_id, "password_changed": True},
    )

    rc = run(["game", "user", "set-password", "--world", "module-test", "--user", "player-id", "--password-env", "USER_PW"])

    assert rc == 0
    assert calls == [("module-test", "player-id", "pw")]


def test_game_user_set_role_wires_role(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.set_game_user_role",
        lambda instance, world_id, user_id, role: calls.append((world_id, user_id, role)) or {"world": world_id, "updated": True},
    )

    rc = run(["game", "user", "set-role", "--world", "module-test", "--user", "player-id", "--role", "Assistant Gamemaster"])

    assert rc == 0
    assert calls == [("module-test", "player-id", "Assistant Gamemaster")]


def test_game_user_disable_wires_user(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.disable_game_user",
        lambda instance, world_id, user_id: calls.append((world_id, user_id)) or {"world": world_id, "updated": True},
    )

    rc = run(["game", "user", "disable", "--world", "module-test", "--user", "player-id"])

    assert rc == 0
    assert calls == [("module-test", "player-id")]


def test_game_user_delete_requires_and_passes_force(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.delete_game_user",
        lambda instance, world_id, user_id, *, force=False: calls.append((world_id, user_id, force)) or {"world": world_id, "deleted": True},
    )

    rc = run(["game", "user", "delete", "--world", "module-test", "--user", "player-id", "--force"])

    assert rc == 0
    assert calls == [("module-test", "player-id", True)]
