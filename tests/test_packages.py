from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.packages import PackageOperationError, install_package

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


def test_install_package_rejects_id_only_for_now(tmp_path):
    with pytest.raises(PackageOperationError, match="manifest URL is required"):
        install_package(instance(tmp_path), package_type="system", package_id="dnd5e", client=object())


def test_install_package_rejects_unknown_type(tmp_path):
    with pytest.raises(PackageOperationError, match="Unsupported package type"):
        install_package(
            instance(tmp_path),
            package_type="world",
            manifest="https://example.test/world.json",
            client=object(),
        )
