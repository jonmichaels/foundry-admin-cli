from foundry_admin_cli.cli import run
from foundry_admin_cli.config import ConfigurationError


def test_cli_version_is_0_3(capsys):
    try:
        run(["--cli-version"])
    except SystemExit as exc:
        assert exc.code == 0

    out = capsys.readouterr().out
    assert "fvtt 0.3.0" in out


def test_top_level_help_uses_singular_setup_commands_and_game_namespace(capsys):
    try:
        run(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    out = capsys.readouterr().out
    assert "{status,restart,logs,wait,admin,system,module,game,world}" in out
    assert "systems" not in out
    assert "modules" not in out
    assert "worlds" not in out


def test_plural_setup_commands_are_not_accepted(capsys):
    for command in ("worlds", "systems", "modules"):
        try:
            run([command, "list"])
        except SystemExit as exc:
            assert exc.code == 2
        assert "invalid choice" in capsys.readouterr().err


def test_status_json_outputs_process_status_with_global_before_command(monkeypatch, capsys):
    class FakeStatus:
        def to_dict(self):
            return {
                "version": "v13",
                "pm2_name": "foundry-v13",
                "status": "online",
                "pid": 123,
                "port": 30000,
                "configured_world": "module-test-black-flag",
                "active_world": "test-world",
                "memory_mb": 256,
            }

    monkeypatch.setattr("foundry_admin_cli.cli.get_status", lambda instance: FakeStatus())

    rc = run(["--version", "v13", "--json", "status"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "online"' in out
    assert '"active_world": "test-world"' in out


def test_status_json_outputs_process_status_with_global_after_command(monkeypatch, capsys):
    class FakeStatus:
        def to_dict(self):
            return {
                "version": "v13",
                "pm2_name": "foundry-v13",
                "status": "online",
                "pid": 123,
                "port": 30000,
                "configured_world": "module-test-black-flag",
                "active_world": "test-world",
                "memory_mb": 256,
            }

    monkeypatch.setattr("foundry_admin_cli.cli.get_status", lambda instance: FakeStatus())

    rc = run(["--version", "v13", "status", "--json"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "online"' in out
    assert '"active_world": "test-world"' in out


def test_status_human_outputs_concise_line(monkeypatch, capsys):
    class FakeStatus:
        def to_dict(self):
            return {
                "version": "v13",
                "pm2_name": "foundry-v13",
                "status": "online",
                "pid": 123,
                "port": 30000,
                "configured_world": "module-test-black-flag",
                "active_world": "test-world",
                "memory_mb": 256,
            }

    monkeypatch.setattr("foundry_admin_cli.cli.get_status", lambda instance: FakeStatus())

    rc = run(["status"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "v13: online | PID 123 | port 30000 | active: test-world | configured: module-test-black-flag" in out


def test_configuration_errors_after_load_are_clean_cli_errors(monkeypatch, capsys):
    monkeypatch.setattr(
        "foundry_admin_cli.cli.get_status",
        lambda instance: (_ for _ in ()).throw(ConfigurationError("status requires local access")),
    )

    rc = run(["status", "--json"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "error: status requires local access" in captured.err
    assert "Traceback" not in captured.err
