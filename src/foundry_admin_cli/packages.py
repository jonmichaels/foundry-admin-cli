"""Shared Foundry package operation helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .config import FoundryInstance

SUPPORTED_PACKAGE_TYPES = {"system", "module"}


class PackageOperationError(RuntimeError):
    """Raised when a package operation is unsafe or invalid."""


def validate_manifest_url(manifest: str) -> None:
    parsed = urlparse(manifest)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PackageOperationError("Manifest URL must use http or https")


def install_package(
    instance: FoundryInstance,
    *,
    package_type: str,
    manifest: str | None = None,
    package_id: str | None = None,
    client: Any,
) -> dict[str, Any]:
    """Install a Foundry package through the verified setup installPackage action."""

    if package_type not in SUPPORTED_PACKAGE_TYPES:
        raise PackageOperationError(f"Unsupported package type: {package_type}")
    if not manifest:
        raise PackageOperationError("manifest URL is required; ID-only registry lookup is not implemented yet")
    validate_manifest_url(manifest)
    payload: dict[str, Any] = {"type": package_type, "manifest": manifest}
    if package_id:
        payload["id"] = package_id
    setup_result = client.setup_action("installPackage", payload)
    return {
        "version": instance.version,
        "type": package_type,
        "id": package_id or setup_result.get("id"),
        "manifest": manifest,
        "changed": True,
        "setup_result": setup_result,
    }
