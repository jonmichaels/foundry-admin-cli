import json
from datetime import date
from io import BytesIO
from urllib.error import URLError

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.process import ProcessError, collect_logs, restart_instance, wait_until_ready


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


class FakeResponse:
    def __init__(self, body=b"<title>Foundry Virtual Tabletop</title>", code=200):
        self._body = body
        self.status = code

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_restart_uses_pm2_name_and_waits_for_readiness(monkeypatch, tmp_path):
    inst = instance(tmp_path)
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("foundry_admin_cli.process.run_pm2", lambda *args: calls.append(args) or Result())
    monkeypatch.setattr("foundry_admin_cli.process.wait_until_ready", lambda instance, **kwargs: {"ready": True, "attempts": 1, "url": instance.url})

    result = restart_instance(inst, timeout_seconds=10)

    assert calls == [("restart", "foundry-v13")]
    assert result["restarted"] is True
    assert result["ready"] is True


def test_restart_reports_pm2_failure_without_waiting(monkeypatch, tmp_path):
    inst = instance(tmp_path)

    class Result:
        returncode = 1
        stdout = ""
        stderr = "bad things"

    monkeypatch.setattr("foundry_admin_cli.process.run_pm2", lambda *args: Result())

    with pytest.raises(ProcessError, match="PM2 restart failed"):
        restart_instance(inst)


def test_wait_until_ready_rejects_invalid_timing(tmp_path):
    inst = instance(tmp_path)

    with pytest.raises(ProcessError, match="timeout must be positive"):
        wait_until_ready(inst, timeout_seconds=0)
    with pytest.raises(ProcessError, match="interval must be positive"):
        wait_until_ready(inst, interval_seconds=-1)


def test_wait_until_ready_retries_until_http_get_succeeds(monkeypatch, tmp_path):
    inst = instance(tmp_path)
    calls = []
    responses = [URLError("down"), FakeResponse()]

    def fake_urlopen(url, timeout=0):
        calls.append((url, timeout))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("foundry_admin_cli.process.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("foundry_admin_cli.process.sleep", lambda seconds: None)
    monkeypatch.setattr("foundry_admin_cli.process.monotonic", iter([0, 0, 1]).__next__)

    result = wait_until_ready(inst, timeout_seconds=5, interval_seconds=0.1)

    assert result["ready"] is True
    assert result["attempts"] == 2
    assert calls[0][0] == "http://foundry.test/"


def test_wait_until_ready_times_out(monkeypatch, tmp_path):
    inst = instance(tmp_path)

    monkeypatch.setattr("foundry_admin_cli.process.urllib.request.urlopen", lambda url, timeout=0: (_ for _ in ()).throw(URLError("down")))
    monkeypatch.setattr("foundry_admin_cli.process.sleep", lambda seconds: None)
    monkeypatch.setattr("foundry_admin_cli.process.monotonic", iter([0, 0, 2]).__next__)

    with pytest.raises(ProcessError, match="Timed out"):
        wait_until_ready(inst, timeout_seconds=1, interval_seconds=0.1)


def test_collect_logs_tails_debug_and_error_with_filter(tmp_path, monkeypatch):
    inst = instance(tmp_path)
    log_dir = inst.data_dir / "Logs"
    log_dir.mkdir(parents=True)
    today = date(2026, 6, 9)
    (log_dir / "debug.2026-06-09.log").write_text("alpha\nneedle debug\n", encoding="utf-8")
    (log_dir / "error.2026-06-09.log").write_text("needle error\nomega\n", encoding="utf-8")

    result = collect_logs(inst, lines=5, contains="needle", today=today)

    assert result["debug"] == ["needle debug"]
    assert result["error"] == ["needle error"]
    assert result["debug_path"].endswith("debug.2026-06-09.log")


def test_collect_logs_handles_missing_files(tmp_path):
    inst = instance(tmp_path)

    result = collect_logs(inst, lines=5, today=date(2026, 6, 9))

    assert result["debug"] == []
    assert result["error"] == []
