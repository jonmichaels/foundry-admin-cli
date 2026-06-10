"""HTTP session client for Foundry setup/admin operations."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .config import FoundryInstance


class AdminClientError(RuntimeError):
    """Raised for setup/admin client failures safe to show in CLI output."""


def read_password_from_env(env_name: str, *, env_file: Path | None = None) -> str:
    """Read a secret from environment or local .env without ever echoing it."""

    value = os.environ.get(env_name)
    if value:
        return value
    if env_file is not None and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, candidate = stripped.split("=", 1)
            if key.strip() == env_name:
                value = candidate.strip().strip('"').strip("'")
                if value:
                    return value
    raise AdminClientError(f"Required environment variable is not set: {env_name}")


def default_cookie_path(instance: FoundryInstance) -> Path:
    """Return configured cookie cache path for a Foundry instance."""

    return instance.resolved_cache_dir() / f"{instance.version}-cookies.txt"


def _flatten_form_data(data: dict[str, Any]) -> dict[str, str]:
    """Flatten nested dict/list data into Foundry setup bracket-form keys."""

    flattened: dict[str, str] = {}

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(f"{prefix}[{key}]", child)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(f"{prefix}[{index}]", child)
        elif value is None:
            flattened[prefix] = ""
        elif isinstance(value, bool):
            flattened[prefix] = "true" if value else "false"
        else:
            flattened[prefix] = str(value)

    for key, value in data.items():
        visit(key, value)
    return flattened


@dataclass
class AdminClient:
    """Small urllib-based client for Foundry v13 admin/setup endpoints."""

    instance: FoundryInstance
    cookie_path: Path | None = None
    opener: Any | None = None
    timeout: float = 15.0

    def __post_init__(self) -> None:
        if self.cookie_path is None:
            self.cookie_path = default_cookie_path(self.instance)
        self.cookie_path = Path(self.cookie_path)
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.cookie_path.parent.chmod(0o700)
        self.cookie_jar = MozillaCookieJar(str(self.cookie_path))
        if self.cookie_path.exists():
            self.cookie_path.chmod(0o600)
            self.cookie_jar.load(ignore_discard=True, ignore_expires=False)
        if self.opener is None:
            self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))

    def login(self, admin_password: str) -> dict[str, Any]:
        """Authenticate against POST /auth and persist session cookies."""

        response = self._post_form("auth", {"adminPassword": admin_password}, expect_json=False)
        redirect_path = urlparse(response.geturl()).path.rstrip("/") or "/"
        if redirect_path != "/setup":
            raise AdminClientError("Foundry admin authentication failed or is unavailable")
        self._save_cookies()
        return {
            "authenticated": True,
            "redirect_url": response.geturl(),
            "cookie_path": str(self.cookie_path),
        }

    def logout(self) -> dict[str, Any]:
        """Revoke admin access for the current session via non-destructive setup action."""

        result = self.setup_action("adminLogout")
        self._save_cookies()
        return result

    def setup_probe(self, package_type: str = "module") -> dict[str, Any]:
        """Call a non-mutating setup action to verify the admin session.

        `getPackages` is read-only in Foundry v13 and exercises the same `/setup`
        auth gate as mutating package/world actions.
        """

        return self.setup_action("getPackages", {"type": package_type})

    def status(self) -> dict[str, Any]:
        """Return whether the persisted admin session can access setup actions."""

        try:
            self.setup_probe(package_type="module")
        except AdminClientError as exc:
            return {
                "version": self.instance.version,
                "authenticated": False,
                "setup_access": False,
                "cookie_path": str(self.cookie_path),
                "message": str(exc),
            }
        return {
            "version": self.instance.version,
            "authenticated": True,
            "setup_access": True,
            "cookie_path": str(self.cookie_path),
        }

    def setup_action(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST an action payload to /setup and return decoded JSON."""

        data = {"action": action}
        if payload:
            data.update(payload)
        response = self._post_form("setup", data, expect_json=True)
        raw = response.read().decode("utf-8")
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AdminClientError("Foundry setup response was not JSON") from exc
        if isinstance(decoded, dict) and decoded.get("error"):
            raise AdminClientError(str(decoded["error"]))
        if not isinstance(decoded, dict):
            raise AdminClientError("Foundry setup response was not a JSON object")
        self._save_cookies()
        return decoded

    def _post_form(self, route: str, data: dict[str, Any], *, expect_json: bool):
        encoded = urlencode(_flatten_form_data(data)).encode("utf-8")
        url = urljoin(self.instance.url.rstrip("/") + "/", route.lstrip("/"))
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if expect_json:
            headers["Accept"] = "application/json"
        request = Request(url, data=encoded, headers=headers, method="POST")
        try:
            assert self.opener is not None
            return self.opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise AdminClientError("Foundry admin authentication failed or is unavailable") from exc
            raise AdminClientError(f"Foundry HTTP error {exc.code}") from exc
        except URLError as exc:
            raise AdminClientError(f"Could not reach Foundry: {exc.reason}") from exc

    def _save_cookies(self) -> None:
        assert self.cookie_path is not None
        if not self.cookie_path.exists():
            self.cookie_path.touch(mode=0o600)
        self.cookie_path.chmod(0o600)
        self.cookie_jar.save(ignore_discard=True, ignore_expires=False)
        self.cookie_path.chmod(0o600)
