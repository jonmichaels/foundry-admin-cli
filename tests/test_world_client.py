import json
from http.cookiejar import MozillaCookieJar
from urllib.error import HTTPError
from email.message import Message

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.world_client import WorldClient, WorldClientError, read_secret_from_env


class FakeResponse:
    def __init__(self, body=b"{}", code=200, url="http://foundry.test/game"):
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


def test_read_secret_from_env_supports_local_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("FOUNDRY_GM_PASSWORD", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("FOUNDRY_GM_PASSWORD=from-file\n", encoding="utf-8")

    assert read_secret_from_env("FOUNDRY_GM_PASSWORD", env_file=env_file) == "from-file"


def test_login_posts_v13_join_action_and_persists_owner_only_cookie(tmp_path):
    opener = RecordingOpener([FakeResponse(json.dumps({"status": "success", "redirect": "/game"}).encode())])
    cookie_path = tmp_path / "cache" / "world-cookies.txt"
    client = WorldClient(instance(tmp_path), cookie_path=cookie_path, opener=opener, active_world_provider=lambda inst: "module-test")

    result = client.login("module-test", user="Gamemaster", password="gm-secret")

    assert result["authenticated"] is True
    assert result["world"] == "module-test"
    request = opener.requests[0]
    assert request.full_url == "http://foundry.test/join"
    assert request.get_method() == "POST"
    body = request.data.decode()
    assert "action=join" in body
    assert "userid=Gamemaster" in body
    assert "password=gm-secret" in body
    assert cookie_path.exists()
    assert oct(cookie_path.parent.stat().st_mode & 0o777) == "0o700"
    assert oct(cookie_path.stat().st_mode & 0o777) == "0o600"


def test_login_rejects_success_response_without_game_redirect(tmp_path):
    opener = RecordingOpener([FakeResponse(json.dumps({"status": "success", "redirect": "/join"}).encode())])
    client = WorldClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener, active_world_provider=lambda inst: "module-test")

    with pytest.raises(WorldClientError, match="did not redirect to game"):
        client.login("module-test", user="Gamemaster", password="pw")


def test_login_verifies_expected_world_when_active_world_provider_supplied(tmp_path):
    opener = RecordingOpener([FakeResponse(json.dumps({"status": "success", "redirect": "/game"}).encode())])
    client = WorldClient(
        instance(tmp_path),
        cookie_path=tmp_path / "cookies.txt",
        opener=opener,
        active_world_provider=lambda inst: "other-world",
    )

    with pytest.raises(WorldClientError, match="running world is other-world"):
        client.login("module-test", user="Gamemaster", password="pw")


def test_login_rejects_failed_join_response(tmp_path):
    opener = RecordingOpener([FakeResponse(json.dumps({"status": "failed"}).encode(), code=401, url="http://foundry.test/join")])
    client = WorldClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener, active_world_provider=lambda inst: "module-test")

    with pytest.raises(WorldClientError, match="world authentication failed"):
        client.login("module-test", user="Gamemaster", password="wrong")


def test_login_rejects_http_unauthorized(tmp_path):
    error = HTTPError("http://foundry.test/join", 401, "Unauthorized", Message(), None)
    opener = RecordingOpener([error])
    client = WorldClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener, active_world_provider=lambda inst: "module-test")

    with pytest.raises(WorldClientError, match="world authentication failed"):
        client.login("module-test", user="Gamemaster", password="wrong")


def test_ping_gets_game_with_persisted_session(tmp_path):
    opener = RecordingOpener([FakeResponse(b"<html>game</html>", code=200, url="http://foundry.test/game")])
    client = WorldClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    result = client.ping()

    assert result["authenticated"] is True
    assert result["url"] == "http://foundry.test/game"
    assert opener.requests[0].full_url == "http://foundry.test/game"


def test_ping_reports_redirect_to_join_as_unauthenticated(tmp_path):
    opener = RecordingOpener([FakeResponse(b"", code=200, url="http://foundry.test/join")])
    client = WorldClient(instance(tmp_path), cookie_path=tmp_path / "cookies.txt", opener=opener)

    result = client.ping()

    assert result["authenticated"] is False
    assert result["reason"] == "redirected_to_join"


def test_existing_cookie_jar_permissions_are_tightened(tmp_path):
    cookie_path = tmp_path / "cookies.txt"
    jar = MozillaCookieJar(str(cookie_path))
    jar.save(ignore_discard=True, ignore_expires=True)
    cookie_path.chmod(0o644)

    WorldClient(instance(tmp_path), cookie_path=cookie_path, opener=RecordingOpener([]))

    assert oct(cookie_path.stat().st_mode & 0o777) == "0o600"
