from pathlib import Path

from foundry_admin_cli.cli import run


def test_backup_data_create_wires_archive_arguments(monkeypatch, capsys, tmp_path):
    calls = []
    output = tmp_path / "full.tar.gz"
    monkeypatch.setattr(
        "foundry_admin_cli.cli.create_user_data_archive",
        lambda instance, *, output=None, include_config=False, require_stopped=True: calls.append((output, include_config, require_stopped))
        or {"created": True, "archive": str(output), "included": ["Data", "Config"]},
    )

    rc = run(["backup", "data-create", "--include-config", "--output", str(output), "--json"])

    assert rc == 0
    assert calls == [(output, True, True)]
    assert '"created": true' in capsys.readouterr().out


def test_backup_data_create_allow_running_disables_stopped_requirement(monkeypatch, capsys, tmp_path):
    calls = []
    monkeypatch.setattr(
        "foundry_admin_cli.cli.create_user_data_archive",
        lambda instance, *, output=None, include_config=False, require_stopped=True: calls.append(require_stopped)
        or {"created": True, "archive": "archive.tar.gz"},
    )

    rc = run(["backup", "data-create", "--allow-running", "--json"])

    assert rc == 0
    assert calls == [False]


def test_backup_data_restore_wires_force_and_archive(monkeypatch, capsys, tmp_path):
    calls = []
    archive = tmp_path / "full.tar.gz"
    archive.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "foundry_admin_cli.cli.restore_user_data_archive",
        lambda instance, *, archive, force=False, require_stopped=True: calls.append((archive, force, require_stopped))
        or {"restored": True, "archive": str(archive)},
    )

    rc = run(["backup", "data-restore", str(archive), "--force", "--json"])

    assert rc == 0
    assert calls == [(archive, True, True)]
    assert '"restored": true' in capsys.readouterr().out


def test_backup_data_restore_allow_running_disables_stopped_requirement(monkeypatch, capsys, tmp_path):
    calls = []
    archive = tmp_path / "full.tar.gz"
    archive.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "foundry_admin_cli.cli.restore_user_data_archive",
        lambda instance, *, archive, force=False, require_stopped=True: calls.append(require_stopped)
        or {"restored": True, "archive": str(archive)},
    )

    rc = run(["backup", "data-restore", str(archive), "--force", "--allow-running", "--json"])

    assert rc == 0
    assert calls == [False]
