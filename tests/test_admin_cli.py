from foundry_admin_cli.cli import run


def test_admin_login_uses_password_env_and_emits_json(monkeypatch, capsys):
    calls = {}

    class FakeClient:
        def __init__(self, instance):
            calls["instance"] = instance

        def login(self, password):
            calls["password"] = password
            return {"authenticated": True, "cookie_path": "/tmp/cookies.txt"}

    monkeypatch.setenv("FOUNDRY_ADMIN_PASSWORD", "secret")
    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", FakeClient)

    rc = run(["--version", "v13", "--json", "admin", "login", "--password-env", "FOUNDRY_ADMIN_PASSWORD"])

    assert rc == 0
    assert calls["password"] == "secret"
    out = capsys.readouterr().out
    assert '"authenticated": true' in out
    assert "secret" not in out


def test_admin_probe_calls_non_mutating_setup_probe(monkeypatch, capsys):
    calls = {}

    class FakeClient:
        def __init__(self, instance):
            calls["instance"] = instance

        def setup_probe(self, package_type="module"):
            calls["package_type"] = package_type
            return {"packages": []}

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", FakeClient)

    rc = run(["admin", "probe", "--type", "system", "--json"])

    assert rc == 0
    assert calls["package_type"] == "system"
    assert '"packages": []' in capsys.readouterr().out


def test_admin_logout_calls_client(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, instance):
            pass

        def logout(self):
            return {"redirect": "/setup"}

    monkeypatch.setattr("foundry_admin_cli.cli.AdminClient", FakeClient)

    rc = run(["admin", "logout", "--json"])

    assert rc == 0
    assert '"redirect": "/setup"' in capsys.readouterr().out
