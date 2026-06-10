from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError

import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.license_client import LicenseActivationError, LicenseClient


class FakeResponse:
    def __init__(self, url, body=b"", code=200):
        self._url = url
        self._body = body
        self.code = code

    def geturl(self):
        return self._url

    def read(self):
        return self._body


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("no fake response queued")
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
        pm2_name="foundry-test",
    )


def test_license_status_detects_required_license(tmp_path):
    opener = FakeOpener([FakeResponse("http://foundry.test/license")])

    result = LicenseClient(instance(tmp_path), opener=opener).status()

    assert result["license_required"] is True
    assert result["redirect_path"] == "/license"


def test_license_status_detects_setup_ready(tmp_path):
    opener = FakeOpener([FakeResponse("http://foundry.test/setup")])

    result = LicenseClient(instance(tmp_path), opener=opener).status()

    assert result["license_required"] is False
    assert result["redirect_path"] == "/setup"


def test_license_activate_posts_key_then_eula_without_echoing_key(tmp_path):
    opener = FakeOpener([
        FakeResponse("http://foundry.test/license"),
        FakeResponse("http://foundry.test/license", b"End User License Agreement"),
        FakeResponse("http://foundry.test/setup", b"Found. Redirecting to /setup", 302),
    ])

    result = LicenseClient(instance(tmp_path), opener=opener).activate("SECRET-LICENSE-KEY")

    assert result == {"version": "v13", "changed": True, "license_required": False, "redirect_path": "/setup"}
    bodies = [request.data.decode("utf-8") for request in opener.requests if getattr(request, "data", None)]
    assert any("licenseKey=SECRET-LICENSE-KEY" in body for body in bodies)
    assert "SECRET-LICENSE-KEY" not in str(result)


def test_license_activate_noops_when_already_licensed(tmp_path):
    opener = FakeOpener([FakeResponse("http://foundry.test/setup")])

    result = LicenseClient(instance(tmp_path), opener=opener).activate("SECRET-LICENSE-KEY")

    assert result["changed"] is False
    assert len(opener.requests) == 1


def test_license_activate_fails_if_key_form_remains(tmp_path):
    opener = FakeOpener([
        FakeResponse("http://foundry.test/license"),
        FakeResponse("http://foundry.test/license", b'<input name="licenseKey">'),
    ])

    with pytest.raises(LicenseActivationError, match="activation failed"):
        LicenseClient(instance(tmp_path), opener=opener).activate("BAD-LICENSE")
