from foundry_admin_cli.cli import run


def test_world_login_reads_password_env_and_calls_client(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("foundry_admin_cli.cli.read_world_secret_from_env", lambda name, env_file=None: "pw")

    class FakeClient:
        def __init__(self, instance):
            pass

        def login(self, world_id, *, user, password):
            calls.append((world_id, user, password))
            return {"world": world_id, "authenticated": True}

    monkeypatch.setattr("foundry_admin_cli.cli.WorldClient", FakeClient)

    rc = run(["world", "login", "module-test", "--user", "Gamemaster", "--password-env", "FOUNDRY_GM_PASSWORD", "--json"])

    assert rc == 0
    assert calls == [("module-test", "Gamemaster", "pw")]
    assert '"authenticated": true' in capsys.readouterr().out


def test_world_ping_calls_client(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, instance):
            pass

        def ping(self):
            return {"authenticated": True, "url": "http://foundry.test/game"}

    monkeypatch.setattr("foundry_admin_cli.cli.WorldClient", FakeClient)

    rc = run(["world", "ping", "--json"])

    assert rc == 0
    assert '"authenticated": true' in capsys.readouterr().out


def test_world_login_reports_secret_errors(monkeypatch, capsys):
    from foundry_admin_cli.world_client import WorldClientError

    monkeypatch.setattr(
        "foundry_admin_cli.cli.read_world_secret_from_env",
        lambda name, env_file=None: (_ for _ in ()).throw(WorldClientError("missing secret")),
    )

    rc = run(["world", "login", "module-test", "--user", "Gamemaster", "--password-env", "FOUNDRY_GM_PASSWORD"])

    assert rc == 1
    assert "missing secret" in capsys.readouterr().err
