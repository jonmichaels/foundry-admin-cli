from foundry_admin_cli.cli import run


def test_status_json_outputs_process_status_with_global_before_command(monkeypatch, capsys):
    class FakeStatus:
        def to_dict(self):
            return {
                "version": "v13",
                "pm2_name": "foundry-v13",
                "status": "online",
                "pid": 123,
                "port": 30000,
                "world": "test-world",
                "memory_mb": 256,
            }

    monkeypatch.setattr("foundry_admin_cli.cli.get_status", lambda instance: FakeStatus())

    rc = run(["--version", "v13", "--json", "status"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "online"' in out
    assert '"world": "test-world"' in out


def test_status_json_outputs_process_status_with_global_after_command(monkeypatch, capsys):
    class FakeStatus:
        def to_dict(self):
            return {
                "version": "v13",
                "pm2_name": "foundry-v13",
                "status": "online",
                "pid": 123,
                "port": 30000,
                "world": "test-world",
                "memory_mb": 256,
            }

    monkeypatch.setattr("foundry_admin_cli.cli.get_status", lambda instance: FakeStatus())

    rc = run(["--version", "v13", "status", "--json"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "online"' in out
    assert '"world": "test-world"' in out


def test_status_human_outputs_concise_line(monkeypatch, capsys):
    class FakeStatus:
        def to_dict(self):
            return {
                "version": "v13",
                "pm2_name": "foundry-v13",
                "status": "online",
                "pid": 123,
                "port": 30000,
                "world": "test-world",
                "memory_mb": 256,
            }

    monkeypatch.setattr("foundry_admin_cli.cli.get_status", lambda instance: FakeStatus())

    rc = run(["status"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "v13: online | PID 123 | port 30000 | world: test-world" in out
