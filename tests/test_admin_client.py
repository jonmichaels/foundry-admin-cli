import json
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from email.message import Message
from urllib.error import HTTPError

import pytest

from foundry_admin_cli.admin_client import AdminClient, AdminClientError, _flatten_form_data, read_password_from_env
from foundry_admin_cli.config import FoundryInstance


class FakeResponse:
    def __init__(self, body=b"{}", code=200, url="http://foundry.test/setup"):
        self._body = body
        self.code = code
        self._url = url
        self.headers = {}

    def read(self):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class RecordingOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


def test_flatten_form_data_encodes_nested_foundry_setup_payloads():
    flattened = _flatten_form_data(
        {
            "action": "createBackup",
            "backups": [{"type": "world", "packageId": "my-world", "note": "before"}],
        }
    )

    assert flattened == {
        "action": "createBackup",
        "backups[0][type]": "world",
        "backups[0][packageId]": "my-world",
        "backups[0][note]": "before",
    }


def test_read_password_from_env_requires_existing_env(monkeypatch):
    monkeypatch.delenv("FOUNDRY_ADMIN_PASSWORD", raising=False)

    with pytest.raises(AdminClientError, match="FOUNDRY_ADMIN_PASSWORD"):
        read_password_from_env("FOUNDRY_ADMIN_PASSWORD")


def test_read_password_from_env_can_load_local_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("FOUNDRY_ADMIN_PASSWORD", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("FOUNDRY_ADMIN_PASSWORD=from-file\n", encoding="utf-8")

    assert read_password_from_env("FOUNDRY_ADMIN_PASSWORD", env_file=env_file) == "from-file"


def test_login_posts_admin_password_without_leaking_secret(tmp_path):
    opener = RecordingOpener([FakeResponse(b"", url="http://foundry.test/setup")])
    client = AdminClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    result = client.login("super-secret")

    assert result["authenticated"] is True
    request = opener.requests[0]
    assert request.full_url == "http://foundry.test/auth"
    assert request.get_method() == "POST"
    body = request.data.decode()
    assert "adminPassword=super-secret" in body
    assert result["redirect_url"] == "http://foundry.test/setup"


def test_setup_probe_posts_non_mutating_get_packages_action(tmp_path):
    opener = RecordingOpener([FakeResponse(json.dumps({"packages": []}).encode())])
    client = AdminClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    result = client.setup_probe(package_type="module")

    assert result == {"packages": []}
    request = opener.requests[0]
    assert request.full_url == "http://foundry.test/setup"
    assert request.get_method() == "POST"
    body = request.data.decode()
    assert "action=getPackages" in body
    assert "type=module" in body


def test_setup_action_posts_nested_backup_payload_with_bracket_keys(tmp_path):
    opener = RecordingOpener([FakeResponse(json.dumps({}).encode())])
    client = AdminClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    client.setup_action(
        "createBackup",
        {"backups": [{"type": "world", "packageId": "my-world", "note": "before"}]},
    )

    body = opener.requests[0].data.decode()
    assert "action=createBackup" in body
    assert "backups%5B0%5D%5Btype%5D=world" in body
    assert "backups%5B0%5D%5BpackageId%5D=my-world" in body
    assert "backups%5B0%5D%5Bnote%5D=before" in body


def test_setup_probe_reports_unauthorized_without_secret(tmp_path):
    error = HTTPError(
        url="http://foundry.test/setup",
        code=403,
        msg="Forbidden",
        hdrs=Message(),
        fp=None,
    )
    opener = RecordingOpener([error])
    client = AdminClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    with pytest.raises(AdminClientError, match="admin authentication failed"):
        client.setup_probe()


def test_login_rejects_redirect_back_to_auth(tmp_path):
    opener = RecordingOpener([FakeResponse(b"", url="http://foundry.test/auth")])
    client = AdminClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    with pytest.raises(AdminClientError, match="authentication failed"):
        client.login("wrong-password")


def test_cookie_directory_is_owner_only(tmp_path):
    opener = RecordingOpener([FakeResponse(b"", url="http://foundry.test/setup")])
    cookie_path = tmp_path / "cache" / "cookies.txt"

    AdminClient(instance(tmp_path), cookie_path=cookie_path, opener=opener)

    assert oct(cookie_path.parent.stat().st_mode & 0o777) == "0o700"


def test_cookie_file_is_created_with_owner_only_permissions(tmp_path):
    opener = RecordingOpener([FakeResponse(b"", url="http://foundry.test/setup")])
    cookie_path = tmp_path / "cookies.txt"
    client = AdminClient(instance(tmp_path), cookie_path=cookie_path, opener=opener)

    client.login("secret")

    assert cookie_path.exists()
    assert oct(cookie_path.stat().st_mode & 0o777) == "0o600"


def test_existing_cookie_jar_permissions_are_tightened_on_load(tmp_path):
    cookie_path = tmp_path / "cookies.txt"
    jar = MozillaCookieJar(str(cookie_path))
    jar.save(ignore_discard=True, ignore_expires=True)
    cookie_path.chmod(0o644)

    AdminClient(instance(tmp_path), cookie_path=cookie_path, opener=RecordingOpener([]))

    assert oct(cookie_path.stat().st_mode & 0o777) == "0o600"


def test_existing_cookie_jar_can_be_loaded(tmp_path):
    cookie_path = tmp_path / "cookies.txt"
    jar = MozillaCookieJar(str(cookie_path))
    jar.save(ignore_discard=True, ignore_expires=True)
    cookie_path.chmod(0o600)

    client = AdminClient(instance(tmp_path), cookie_path=cookie_path, opener=RecordingOpener([]))

    assert client.cookie_path == cookie_path


def test_status_uses_non_mutating_setup_probe(tmp_path):
    opener = RecordingOpener([FakeResponse(json.dumps({"packages": []}).encode())])
    client = AdminClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    result = client.status()

    assert result["authenticated"] is True
    assert result["setup_access"] is True
    assert result["cookie_path"].endswith("cookies.txt")


def test_status_reports_unauthenticated_without_raising(tmp_path):
    error = HTTPError(
        url="http://foundry.test/setup",
        code=403,
        msg="Forbidden",
        hdrs=Message(),
        fp=None,
    )
    opener = RecordingOpener([error])
    client = AdminClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    result = client.status()

    assert result["authenticated"] is False
    assert "admin authentication failed" in result["message"]
