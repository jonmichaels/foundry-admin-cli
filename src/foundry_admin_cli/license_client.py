"""Foundry software license activation helpers for fresh installs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, build_opener

from .config import FoundryInstance


class LicenseActivationError(RuntimeError):
    """Raised for license activation failures safe to show in CLI output."""


def read_license_from_env(env_name: str, *, env_file: Path | None = None) -> str:
    """Read the Foundry license from environment/local .env without echoing it."""

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
    raise LicenseActivationError(f"Required environment variable is not set: {env_name}")


@dataclass
class LicenseClient:
    """Small urllib client for Foundry /license activation."""

    instance: FoundryInstance
    opener: Any | None = None
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if self.opener is None:
            self.opener = build_opener()

    def _url(self, path: str) -> str:
        return urljoin(self.instance.url.rstrip("/") + "/", path.lstrip("/"))

    def status(self) -> dict[str, Any]:
        """Return whether this server currently requires license activation."""

        request = Request(self._url("/"), method="GET")
        try:
            assert self.opener is not None
            response = self.opener.open(request, timeout=self.timeout)
            response.read()
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise LicenseActivationError("Could not inspect Foundry license status") from exc
            raise LicenseActivationError(f"Foundry HTTP error {exc.code}") from exc
        except URLError as exc:
            raise LicenseActivationError(f"Could not reach Foundry: {exc.reason}") from exc
        path = urlparse(response.geturl()).path.rstrip("/") or "/"
        return {
            "version": self.instance.version,
            "license_required": path == "/license",
            "redirect_path": path,
        }

    def activate(self, license_key: str) -> dict[str, Any]:
        """Submit license key and sign EULA. Does not expose the key in output."""

        if not license_key.strip():
            raise LicenseActivationError("Foundry license value cannot be empty")
        before = self.status()
        if not before["license_required"]:
            return {"version": self.instance.version, "changed": False, "license_required": False}

        first = self._post_license({"licenseKey": license_key, "action": "enterKey"})
        first_path = urlparse(first.geturl()).path.rstrip("/") or "/"
        if first_path == "/license":
            body = first.read().decode("utf-8", errors="ignore")
            if "licenseKey" in body and "End User" not in body and "EULA" not in body:
                raise LicenseActivationError("Foundry license activation failed")
        else:
            first.read()

        second = self._post_license({"action": "accept"})
        second.read()
        final_path = urlparse(second.geturl()).path.rstrip("/") or "/"
        if final_path not in {"/setup", "/auth"}:
            raise LicenseActivationError("Foundry license EULA signing did not reach setup")
        return {
            "version": self.instance.version,
            "changed": True,
            "license_required": False,
            "redirect_path": final_path,
        }

    def _post_license(self, data: dict[str, str]):
        encoded = urlencode(data).encode("utf-8")
        request = Request(
            self._url("/license"),
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            assert self.opener is not None
            return self.opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            raise LicenseActivationError(f"Foundry license HTTP error {exc.code}") from exc
        except URLError as exc:
            raise LicenseActivationError(f"Could not reach Foundry: {exc.reason}") from exc
