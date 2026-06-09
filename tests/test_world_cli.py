from foundry_admin_cli.cli import run


def test_world_login_reads_password_env_and_calls_client(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("foundry_admin_cli.cli.read_world_secret_from_env", lambda name, env_file=None: "pw")

    class FakeClient:
        def __init__(self, instance):
            pass

        def login(self, world_id, *, user, password, allow_empty_password=False):
            calls.append((world_id, user, password, allow_empty_password))
            return {"world": world_id, "authenticated": True}

    monkeypatch.setattr("foundry_admin_cli.cli.WorldClient", FakeClient)

    rc = run(["game", "login", "module-test", "--user", "Gamemaster", "--password-env", "FOUNDRY_GM_PASSWORD", "--json"])

    assert rc == 0
    assert calls == [("module-test", "Gamemaster", "pw", False)]
    assert '"authenticated": true' in capsys.readouterr().out


def test_world_ping_calls_client(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, instance):
            pass

        def ping(self):
            return {"authenticated": True, "url": "http://foundry.test/game"}

    monkeypatch.setattr("foundry_admin_cli.cli.WorldClient", FakeClient)

    rc = run(["game", "ping", "--json"])

    assert rc == 0
    assert '"authenticated": true' in capsys.readouterr().out


def test_game_return_to_setup_calls_client_without_admin_password(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, instance):
            pass

        def return_to_setup(self, world_id, *, admin_password=None):
            calls.append((world_id, admin_password))
            return {"world": world_id, "shutdown": True, "setup_authenticated": True}

    monkeypatch.setattr("foundry_admin_cli.cli.WorldClient", FakeClient)

    rc = run(["game", "return-to-setup", "--world", "module-test", "--json"])

    assert rc == 0
    assert calls == [("module-test", None)]
    assert '"shutdown": true' in capsys.readouterr().out


def test_game_return_to_setup_reads_optional_admin_password(monkeypatch):
    calls = []
    monkeypatch.setattr("foundry_admin_cli.cli.read_password_from_env", lambda name, env_file=None: "admin-pw")

    class FakeClient:
        def __init__(self, instance):
            pass

        def return_to_setup(self, world_id, *, admin_password=None):
            calls.append((world_id, admin_password))
            return {"world": world_id, "shutdown": True, "setup_authenticated": True}

    monkeypatch.setattr("foundry_admin_cli.cli.WorldClient", FakeClient)

    rc = run(["game", "return-to-setup", "--world", "module-test", "--admin-password-env", "FOUNDRY_ADMIN_PASSWORD"])

    assert rc == 0
    assert calls == [("module-test", "admin-pw")]


def test_game_return_to_setup_reports_missing_admin_secret(monkeypatch, capsys):
    from foundry_admin_cli.admin_client import AdminClientError

    monkeypatch.setattr(
        "foundry_admin_cli.cli.read_password_from_env",
        lambda name, env_file=None: (_ for _ in ()).throw(AdminClientError("missing admin secret")),
    )

    class FakeClient:
        def __init__(self, instance):
            pass

    monkeypatch.setattr("foundry_admin_cli.cli.WorldClient", FakeClient)

    rc = run(["game", "return-to-setup", "--world", "module-test", "--admin-password-env", "FOUNDRY_ADMIN_PASSWORD"])

    assert rc == 1
    assert "missing admin secret" in capsys.readouterr().err


def test_world_login_reports_secret_errors(monkeypatch, capsys):
    from foundry_admin_cli.world_client import WorldClientError

    monkeypatch.setattr(
        "foundry_admin_cli.cli.read_world_secret_from_env",
        lambda name, env_file=None: (_ for _ in ()).throw(WorldClientError("missing secret")),
    )

    rc = run(["game", "login", "module-test", "--user", "Gamemaster", "--password-env", "FOUNDRY_GM_PASSWORD"])

    assert rc == 1
    assert "missing secret" in capsys.readouterr().err
