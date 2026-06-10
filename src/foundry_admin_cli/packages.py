"""Shared Foundry package operation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from .config import FoundryInstance

SUPPORTED_PACKAGE_TYPES = {"system", "module"}
SAFE_PACKAGE_LIBRARY_FIELDS = {
    "id",
    "name",
    "title",
    "version",
    "description",
    "authors",
    "url",
    "manifest",
    "manifestUrl",
    "manifest_url",
    "compatibility",
    "relationships",
    "tags",
    "type",
    "system",
    "systems",
    "availability",
    "locked",
    "exclusive",
    "owned",
    "protected",
    "hasStorage",
}


class PackageOperationError(RuntimeError):
    """Raised when a package operation is unsafe or invalid."""


def validate_manifest_url(manifest: str) -> None:
    parsed = urlparse(manifest)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PackageOperationError("Manifest URL must use http or https")


def _ensure_supported_package_type(package_type: str) -> None:
    if package_type not in SUPPORTED_PACKAGE_TYPES:
        raise PackageOperationError(f"Unsupported package type: {package_type}")


def looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme)


def _normalize_package_record(package: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in package.items() if key in SAFE_PACKAGE_LIBRARY_FIELDS}


def _extract_packages(setup_result: Any) -> list[dict[str, Any]]:
    if isinstance(setup_result, list):
        candidates: Iterable[Any] = setup_result
    elif isinstance(setup_result, dict):
        raw = setup_result.get("packages") or setup_result.get("items") or setup_result.get("results") or []
        if isinstance(raw, dict):
            candidates = raw.values()
        elif isinstance(raw, list):
            candidates = raw
        else:
            raise PackageOperationError("Foundry package library package list was not a list or object")
    else:
        raise PackageOperationError("Foundry package library response was not a list or object")

    packages: list[dict[str, Any]] = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            packages.append(_normalize_package_record(dict(candidate)))
    return packages


def _package_matches_query(package: dict[str, Any], query: str) -> bool:
    needle = query.casefold()
    searchable = [package.get("id"), package.get("name"), package.get("title"), package.get("description")]
    return any(isinstance(value, str) and needle in value.casefold() for value in searchable)


def get_package_library(
    instance: FoundryInstance,
    *,
    package_type: str,
    client: Any,
    query: str | None = None,
) -> dict[str, Any]:
    """Return Foundry's package library for systems or modules via setup getPackages."""

    _ensure_supported_package_type(package_type)
    setup_result = client.setup_action("getPackages", {"type": package_type})
    packages = _extract_packages(setup_result)
    if query:
        packages = [package for package in packages if _package_matches_query(package, query)]
    return {
        "version": instance.version,
        "type": package_type,
        "query": query,
        "count": len(packages),
        "packages": packages,
    }


def resolve_package_from_library(
    instance: FoundryInstance,
    *,
    package_type: str,
    package_id: str,
    client: Any,
) -> dict[str, Any]:
    """Resolve an exact package id to library metadata including manifest URL."""

    library = get_package_library(instance, package_type=package_type, client=client)
    matches = [package for package in library["packages"] if package.get("id") == package_id]
    if not matches:
        raise PackageOperationError(f"No {package_type} package with id {package_id!r} was found in the Foundry package library")
    if len(matches) > 1:
        raise PackageOperationError(f"Foundry package library returned multiple {package_type} packages with id {package_id!r}")
    package = matches[0]
    manifest = package.get("manifest") or package.get("manifestUrl") or package.get("manifest_url")
    if not isinstance(manifest, str) or not manifest:
        raise PackageOperationError(f"{package_type} package {package_id!r} does not include a manifest URL")
    validate_manifest_url(manifest)
    package["manifest"] = manifest
    return package


def install_package(
    instance: FoundryInstance,
    *,
    package_type: str,
    manifest: str | None = None,
    package_id: str | None = None,
    client: Any,
) -> dict[str, Any]:
    """Install a Foundry package through the verified setup installPackage action."""

    _ensure_supported_package_type(package_type)
    resolved_from_library = False
    if not manifest:
        if not package_id:
            raise PackageOperationError("manifest URL or package id is required")
        package = resolve_package_from_library(instance, package_type=package_type, package_id=package_id, client=client)
        manifest = package["manifest"]
        resolved_from_library = True
    assert manifest is not None
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
        "resolved_from_library": resolved_from_library,
        "setup_result": setup_result,
    }
