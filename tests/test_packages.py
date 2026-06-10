from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.packages import (
    PackageOperationError,
    get_package_library,
    install_package,
    resolve_package_from_library,
)

import pytest


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
    )


def test_install_package_uses_verified_setup_action_manifest_first(tmp_path):
    calls = []

    class FakeClient:
        def setup_action(self, action, payload=None):
            calls.append((action, payload))
            return {"id": "dnd5e", "status": "installed"}

    result = install_package(
        instance(tmp_path),
        package_type="system",
        manifest="https://example.test/dnd5e/system.json",
        client=FakeClient(),
    )

    assert calls == [("installPackage", {"type": "system", "manifest": "https://example.test/dnd5e/system.json"})]
    assert result["changed"] is True
    assert result["type"] == "system"
    assert result["manifest"] == "https://example.test/dnd5e/system.json"


def test_install_package_rejects_non_http_manifest_url(tmp_path):
    with pytest.raises(PackageOperationError, match="Manifest URL must use http or https"):
        install_package(instance(tmp_path), package_type="system", manifest="file:///etc/passwd", client=object())


def test_get_package_library_calls_foundry_setup_get_packages(tmp_path):
    calls = []

    class FakeClient:
        def setup_action(self, action, payload=None):
            calls.append((action, payload))
            return {
                "packages": [
                    {
                        "id": "dnd5e",
                        "title": "Dungeons & Dragons Fifth Edition",
                        "manifest": "https://example.test/dnd5e/system.json",
                        "version": "5.0.0",
                    }
                ]
            }

    result = get_package_library(instance(tmp_path), package_type="system", client=FakeClient())

    assert calls == [("getPackages", {"type": "system"})]
    assert result["version"] == "v13"
    assert result["type"] == "system"
    assert result["packages"] == [
        {
            "id": "dnd5e",
            "title": "Dungeons & Dragons Fifth Edition",
            "manifest": "https://example.test/dnd5e/system.json",
            "version": "5.0.0",
        }
    ]


def test_get_package_library_filters_query_case_insensitive(tmp_path):
    class FakeClient:
        def setup_action(self, action, payload=None):
            return {
                "packages": [
                    {"id": "dnd5e", "title": "Dungeons & Dragons", "manifest": "https://example.test/dnd5e/system.json"},
                    {"id": "pf2e", "title": "Pathfinder Second Edition", "manifest": "https://example.test/pf2e/system.json"},
                ]
            }

    result = get_package_library(instance(tmp_path), package_type="system", query="dragon", client=FakeClient())

    assert [package["id"] for package in result["packages"]] == ["dnd5e"]


def test_get_package_library_redacts_unexpected_sensitive_fields(tmp_path):
    class FakeClient:
        def setup_action(self, action, payload=None):
            return {
                "packages": [
                    {
                        "id": "premium-module",
                        "title": "Premium Module",
                        "manifest": "https://example.test/premium/module.json",
                        "token": "secret-token",
                        "authorization": "Bearer secret",
                        "license": {"key": "secret-license"},
                        "extra_private_payload": "private",
                    }
                ]
            }

    result = get_package_library(instance(tmp_path), package_type="module", client=FakeClient())

    assert result["packages"] == [
        {
            "id": "premium-module",
            "title": "Premium Module",
            "manifest": "https://example.test/premium/module.json",
        }
    ]


def test_resolve_package_from_library_requires_exact_id(tmp_path):
    class FakeClient:
        def setup_action(self, action, payload=None):
            return {
                "packages": [
                    {"id": "tidy5e-sheet", "title": "Tidy 5e Sheet", "manifest": "https://example.test/tidy/module.json"},
                    {"id": "tidy-ui", "title": "Tidy UI", "manifest": "https://example.test/tidy-ui/module.json"},
                ]
            }

    resolved = resolve_package_from_library(instance(tmp_path), package_type="module", package_id="tidy5e-sheet", client=FakeClient())

    assert resolved["id"] == "tidy5e-sheet"
    assert resolved["manifest"] == "https://example.test/tidy/module.json"


@pytest.mark.parametrize("package_id", ["missing", "Tidy 5e Sheet"])
def test_resolve_package_from_library_rejects_missing_or_non_id_matches(tmp_path, package_id):
    class FakeClient:
        def setup_action(self, action, payload=None):
            return {
                "packages": [
                    {"id": "tidy5e-sheet", "title": "Tidy 5e Sheet", "manifest": "https://example.test/tidy/module.json"},
                ]
            }

    with pytest.raises(PackageOperationError, match="No module package with id"):
        resolve_package_from_library(instance(tmp_path), package_type="module", package_id=package_id, client=FakeClient())


def test_resolve_package_from_library_rejects_missing_manifest(tmp_path):
    class FakeClient:
        def setup_action(self, action, payload=None):
            return {"packages": [{"id": "bad-module", "title": "Bad Module"}]}

    with pytest.raises(PackageOperationError, match="does not include a manifest URL"):
        resolve_package_from_library(instance(tmp_path), package_type="module", package_id="bad-module", client=FakeClient())


def test_install_package_resolves_id_through_library_then_installs_manifest(tmp_path):
    calls = []

    class FakeClient:
        def setup_action(self, action, payload=None):
            calls.append((action, payload))
            if action == "getPackages":
                return {"packages": [{"id": "tidy5e-sheet", "title": "Tidy", "manifest": "https://example.test/tidy/module.json"}]}
            if action == "installPackage":
                return {"id": "tidy5e-sheet", "status": "installed"}
            raise AssertionError(action)

    result = install_package(instance(tmp_path), package_type="module", package_id="tidy5e-sheet", client=FakeClient())

    assert calls == [
        ("getPackages", {"type": "module"}),
        ("installPackage", {"type": "module", "manifest": "https://example.test/tidy/module.json", "id": "tidy5e-sheet"}),
    ]
    assert result["id"] == "tidy5e-sheet"
    assert result["manifest"] == "https://example.test/tidy/module.json"
    assert result["resolved_from_library"] is True


def test_install_package_rejects_unknown_type(tmp_path):
    with pytest.raises(PackageOperationError, match="Unsupported package type"):
        install_package(
            instance(tmp_path),
            package_type="world",
            manifest="https://example.test/world.json",
            client=object(),
        )
