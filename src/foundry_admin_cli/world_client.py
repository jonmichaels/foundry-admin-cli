"""Authenticated in-world Foundry session client."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from .config import FoundryInstance
from .process import fetch_active_world


class WorldClientError(RuntimeError):
    """Raised for world-login/session failures safe to show in CLI output."""


def _default_cookie_path(instance: FoundryInstance) -> Path:
    return instance.resolved_cache_dir() / instance.version / "world-cookies.txt"


def read_secret_from_env(env_name: str, *, env_file: Path | None = None) -> str:
    """Read a secret from environment or local .env without echoing it."""

    value = os.environ.get(env_name)
    if value:
        return value
    if env_file and env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, candidate = line.split("=", 1)
            if key.strip() == env_name:
                stripped = candidate.strip()
                if (stripped.startswith('"') and stripped.endswith('"')) or (
                    stripped.startswith("'") and stripped.endswith("'")
                ):
                    stripped = stripped[1:-1]
                if stripped:
                    return stripped
    raise WorldClientError(f"{env_name} is not set")


def resolve_world_user_id(instance: FoundryInstance, world_id: str, user: str) -> str:
    """Resolve a Foundry display name to its internal user id when local data is available."""

    users_dir = instance.worlds_dir / world_id / "data" / "users"
    if not users_dir.exists():
        return user
    for path in sorted(users_dir.iterdir()):
        if path.suffix not in {".log", ".ldb"}:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        # LevelDB value bytes can interleave control bytes into JSON strings while
        # the key remains nearby as !users!<id>. Prefer that key when the display
        # name is visible in the same record fragment.
        for match in re.finditer(rb"!users!([A-Za-z0-9_-]{8,32}).{0,256}?\"name\"\s*:\s*\"([^\"]+)\"", raw, re.DOTALL):
            document_id = match.group(1).decode("ascii", errors="ignore")
            document_name = match.group(2).decode("utf-8", errors="ignore")
            if document_id == user:
                return user
            if document_name == user and document_id:
                return document_id
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r'\{[^\n]*"name"\s*:\s*"[^"\n]+"[^\n]*\}', text):
            try:
                document = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            document_id = document.get("_id")
            document_name = document.get("name")
            if document_id == user:
                return user
            if document_name == user and isinstance(document_id, str) and document_id:
                return document_id
    return user


class WorldClient:
    """Small urllib client for Foundry v13 /join and /game session checks."""

    def __init__(
        self,
        instance: FoundryInstance,
        *,
        cookie_path: Path | None = None,
        opener: Any | None = None,
        active_world_provider: Any | None = None,
    ) -> None:
        self.instance = instance
        self.active_world_provider = active_world_provider or fetch_active_world
        self.cookie_path = cookie_path or _default_cookie_path(instance)
        self.cookie_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.cookie_path.parent, 0o700)
        self.cookie_jar = MozillaCookieJar(str(self.cookie_path))
        if self.cookie_path.exists():
            self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
            os.chmod(self.cookie_path, 0o600)
        self.opener = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))

    def _url(self, path: str) -> str:
        return urllib.parse.urljoin(self.instance.url, path.lstrip("/"))

    def _save_cookies(self) -> None:
        self.cookie_jar.save(ignore_discard=True, ignore_expires=True)
        os.chmod(self.cookie_path, 0o600)

    def login(
        self,
        world_id: str,
        *,
        user: str,
        password: str,
        allow_empty_password: bool = False,
    ) -> dict[str, Any]:
        """POST Foundry v13 /join with action=join, userid, and password."""

        if not world_id.strip():
            raise WorldClientError("world id cannot be empty")
        if not user.strip():
            raise WorldClientError("user cannot be empty")
        if not password and not allow_empty_password:
            raise WorldClientError("password cannot be empty")
        active_world = self.active_world_provider(self.instance)
        if active_world != world_id:
            raise WorldClientError(f"running world is {active_world}; expected {world_id}")
        user_id = resolve_world_user_id(self.instance, world_id, user)
        body = urllib.parse.urlencode({"action": "join", "userid": user_id, "password": password}).encode("utf-8")
        request = urllib.request.Request(
            self._url("/join"),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                final_url = response.geturl()
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise WorldClientError("world authentication failed") from exc
            raise WorldClientError(f"game login failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise WorldClientError(f"game login failed: {exc.reason}") from exc
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise WorldClientError("game login response was not JSON") from exc
        if not isinstance(payload, dict):
            raise WorldClientError("game login response root must be an object")
        if payload.get("status") != "success":
            raise WorldClientError("world authentication failed")
        redirect = payload.get("redirect")
        if urllib.parse.urlparse(str(redirect)).path.rstrip("/") != "/game":
            raise WorldClientError("game login did not redirect to game")
        self._save_cookies()
        return {
            "version": self.instance.version,
            "world": world_id,
            "user": user,
            "authenticated": True,
            "redirect": payload.get("redirect"),
            "url": final_url,
            "cookie_path": str(self.cookie_path),
        }

    def return_to_setup(
        self,
        world_id: str,
        *,
        admin_password: str | None = None,
        admin_client: Any | None = None,
    ) -> dict[str, Any]:
        """Shut down the running world via the v13 game shutdown path and return to setup."""

        if not world_id.strip():
            raise WorldClientError("world id cannot be empty")
        active_world = self.active_world_provider(self.instance)
        if active_world != world_id:
            raise WorldClientError(f"running world is {active_world}; expected {world_id}")

        body = json.dumps({"shutdown": True}).encode("utf-8")
        request = urllib.request.Request(
            self._url("/setup"),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                response.read()
                final_url = response.geturl()
                code = response.code
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise WorldClientError("game shutdown failed: unauthorized") from exc
            raise WorldClientError(f"game shutdown failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise WorldClientError(f"game shutdown failed: {exc.reason}") from exc

        self._save_cookies()
        path = urllib.parse.urlparse(final_url).path.rstrip("/") or "/"
        result: dict[str, Any] = {
            "version": self.instance.version,
            "world": world_id,
            "shutdown": True,
            "status": code,
            "redirect_url": final_url,
            "cookie_path": str(self.cookie_path),
            "setup_authenticated": path == "/setup",
            "admin_required": path == "/auth",
            "admin_reauthenticated": False,
        }
        if path == "/auth" and admin_password:
            if admin_client is None:
                from .admin_client import AdminClient

                admin_client = AdminClient(self.instance)
            admin_result = admin_client.login(admin_password)
            result["setup_authenticated"] = True
            result["admin_required"] = False
            result["admin_reauthenticated"] = True
            result["admin_redirect_url"] = admin_result.get("redirect_url")
            if admin_result.get("cookie_path"):
                result["admin_cookie_path"] = admin_result["cookie_path"]
        elif path not in {"/setup", "/auth"}:
            raise WorldClientError(f"game shutdown redirected to unexpected path: {path}")
        return result

    def ping(self) -> dict[str, Any]:
        """Verify the persisted world session can reach /game without redirecting to /join."""

        request = urllib.request.Request(self._url("/game"), method="GET")
        try:
            with self.opener.open(request, timeout=15) as response:
                response.read()
                final_url = response.geturl()
                code = response.code
        except HTTPError as exc:
            if exc.code in {401, 403}:
                return {
                    "version": self.instance.version,
                    "authenticated": False,
                    "status": exc.code,
                    "reason": "unauthorized",
                    "cookie_path": str(self.cookie_path),
                }
            raise WorldClientError(f"game ping failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise WorldClientError(f"game ping failed: {exc.reason}") from exc
        path = urllib.parse.urlparse(final_url).path.rstrip("/")
        authenticated = path != "/join"
        return {
            "version": self.instance.version,
            "authenticated": authenticated,
            "status": code,
            "reason": None if authenticated else "redirected_to_join",
            "url": final_url,
            "cookie_path": str(self.cookie_path),
        }
