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

    result = client.login("module-test", user="abc123", password="gm-secret")

    assert result["authenticated"] is True
    assert result["world"] == "module-test"
    request = opener.requests[0]
    assert request.full_url == "http://foundry.test/join"
    assert request.get_method() == "POST"
    body = request.data.decode()
    assert "action=join" in body
    assert "userid=abc123" in body
    assert "password=gm-secret" in body
    assert cookie_path.exists()
    assert oct(cookie_path.parent.stat().st_mode & 0o777) == "0o700"
    assert oct(cookie_path.stat().st_mode & 0o777) == "0o600"


def test_login_resolves_display_name_to_internal_user_id_before_join(tmp_path):
    inst = instance(tmp_path)
    users_dir = inst.worlds_dir / "module-test" / "data" / "users"
    users_dir.mkdir(parents=True)
    (users_dir / "000001.log").write_text(
        '!users!abc123 {"name":"Gamemaster","role":4,"_id":"abc123"}',
        encoding="utf-8",
    )
    opener = RecordingOpener([FakeResponse(json.dumps({"status": "success", "redirect": "/game"}).encode())])
    client = WorldClient(inst, cookie_path=tmp_path / "cookies.txt", opener=opener, active_world_provider=lambda _inst: "module-test")

    client.login("module-test", user="Gamemaster", password="gm-secret")

    body = opener.requests[0].data.decode()
    assert "userid=abc123" in body
    assert "userid=Gamemaster" not in body


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


def test_return_to_setup_posts_shutdown_and_accepts_setup_redirect(tmp_path):
    opener = RecordingOpener([FakeResponse(b"", code=200, url="http://foundry.test/setup")])
    client = WorldClient(
        instance(tmp_path),
        cookie_path=tmp_path / "cookies.txt",
        opener=opener,
        active_world_provider=lambda inst: "module-test",
    )

    result = client.return_to_setup("module-test")

    assert result["shutdown"] is True
    assert result["world"] == "module-test"
    assert result["setup_authenticated"] is True
    request = opener.requests[0]
    assert request.full_url == "http://foundry.test/setup"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode()) == {"shutdown": True}


def test_return_to_setup_can_reauthenticate_admin_when_redirected_to_auth(tmp_path):
    opener = RecordingOpener([FakeResponse(b"", code=200, url="http://foundry.test/auth")])
    calls = []

    class FakeAdminClient:
        def login(self, password):
            calls.append(password)
            return {"authenticated": True, "redirect_url": "http://foundry.test/setup", "cookie_path": "/tmp/admin-cookies.txt"}

    client = WorldClient(
        instance(tmp_path),
        cookie_path=tmp_path / "cookies.txt",
        opener=opener,
        active_world_provider=lambda inst: "module-test",
    )

    result = client.return_to_setup("module-test", admin_password="pw", admin_client=FakeAdminClient())

    assert result["shutdown"] is True
    assert result["setup_authenticated"] is True
    assert result["admin_reauthenticated"] is True
    assert result["admin_cookie_path"] == "/tmp/admin-cookies.txt"
    assert calls == ["pw"]


def test_return_to_setup_reports_admin_auth_required_when_no_password_supplied(tmp_path):
    opener = RecordingOpener([FakeResponse(b"", code=200, url="http://foundry.test/auth")])
    client = WorldClient(
        instance(tmp_path),
        cookie_path=tmp_path / "cookies.txt",
        opener=opener,
        active_world_provider=lambda inst: "module-test",
    )

    result = client.return_to_setup("module-test")

    assert result["shutdown"] is True
    assert result["setup_authenticated"] is False
    assert result["admin_required"] is True


def test_return_to_setup_verifies_expected_world(tmp_path):
    client = WorldClient(
        instance(tmp_path),
        cookie_path=tmp_path / "cookies.txt",
        opener=RecordingOpener([]),
        active_world_provider=lambda inst: "other-world",
    )

    with pytest.raises(WorldClientError, match="running world is other-world"):
        client.return_to_setup("module-test")


def test_existing_cookie_jar_permissions_are_tightened(tmp_path):
    cookie_path = tmp_path / "cookies.txt"
    jar = MozillaCookieJar(str(cookie_path))
    jar.save(ignore_discard=True, ignore_expires=True)
    cookie_path.chmod(0o644)

    WorldClient(instance(tmp_path), cookie_path=cookie_path, opener=RecordingOpener([]))

    assert oct(cookie_path.stat().st_mode & 0o777) == "0o600"
