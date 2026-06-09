from foundry_admin_cli.cli import run


def test_restart_command_calls_restart_instance(monkeypatch, capsys):
    calls = []

    def fake_restart(instance, timeout_seconds=60.0):
        calls.append((instance.version, timeout_seconds))
        return {"version": instance.version, "pm2_name": instance.pm2_name, "restarted": True, "ready": True}

    monkeypatch.setattr("foundry_admin_cli.cli.restart_instance", fake_restart)

    rc = run(["--version", "v13", "restart", "--timeout", "12", "--json"])

    assert rc == 0
    assert calls == [("v13", 12.0)]
    assert '"restarted": true' in capsys.readouterr().out


def test_wait_command_calls_wait_until_ready(monkeypatch, capsys):
    calls = []

    def fake_wait(instance, timeout_seconds=60.0, interval_seconds=1.0):
        calls.append((timeout_seconds, interval_seconds))
        return {"version": instance.version, "ready": True, "attempts": 1, "url": instance.url}

    monkeypatch.setattr("foundry_admin_cli.cli.wait_until_ready", fake_wait)

    rc = run(["wait", "--timeout", "7", "--interval", "0.5", "--json"])

    assert rc == 0
    assert calls == [(7.0, 0.5)]
    assert '"ready": true' in capsys.readouterr().out


def test_logs_command_calls_collect_logs(monkeypatch, capsys):
    calls = []

    def fake_logs(instance, lines=50, contains=None, today=None):
        calls.append((lines, contains))
        return {"version": instance.version, "debug": ["debug line"], "error": []}

    monkeypatch.setattr("foundry_admin_cli.cli.collect_logs", fake_logs)

    rc = run(["logs", "--lines", "10", "--filter", "needle", "--json"])

    assert rc == 0
    assert calls == [(10, "needle")]
    assert '"debug line"' in capsys.readouterr().out


def test_process_command_errors_return_one(monkeypatch, capsys):
    from foundry_admin_cli.process import ProcessError

    def fail(instance, timeout_seconds=60.0):
        raise ProcessError("nope")

    monkeypatch.setattr("foundry_admin_cli.cli.restart_instance", fail)

    rc = run(["restart"])

    assert rc == 1
    assert "nope" in capsys.readouterr().err
