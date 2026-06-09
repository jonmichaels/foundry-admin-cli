from __future__ import annotations

from foundry_admin_cli import cli


class FakeWorldClient:
    def __init__(self, instance):
        self.instance = instance

    def login(self, world_id, *, user, password, allow_empty_password=False):
        return {
            "version": self.instance.version,
            "world": world_id,
            "user": user,
            "authenticated": True,
            "password_empty": password == "",
            "allow_empty_password": allow_empty_password,
        }


def test_world_login_can_explicitly_allow_empty_default_gamemaster_password(monkeypatch, capsys):
    monkeypatch.setattr(cli, "WorldClient", FakeWorldClient)

    exit_code = cli.run(
        [
            "--version",
            "v13",
            "world",
            "login",
            "fvtt-cli-smoke",
            "--user",
            "Gamemaster",
            "--allow-empty-password",
            "--json",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"authenticated": true' in output
    assert '"password_empty": true' in output
    assert '"allow_empty_password": true' in output


def test_world_login_requires_password_env_without_explicit_empty_password(capsys):
    exit_code = cli.run(
        [
            "--version",
            "v13",
            "world",
            "login",
            "fvtt-cli-smoke",
            "--user",
            "Gamemaster",
            "--json",
        ]
    )

    assert exit_code == 1
    assert "--password-env is required unless --allow-empty-password is set" in capsys.readouterr().err


def test_world_login_rejects_password_env_with_empty_password_flag(capsys):
    exit_code = cli.run(
        [
            "--version",
            "v13",
            "world",
            "login",
            "fvtt-cli-smoke",
            "--user",
            "Gamemaster",
            "--password-env",
            "FOUNDRY_USER_PASSWORD",
            "--allow-empty-password",
            "--json",
        ]
    )

    assert exit_code == 1
    assert "--password-env cannot be combined with --allow-empty-password" in capsys.readouterr().err
