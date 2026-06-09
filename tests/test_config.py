from foundry_admin_cli.config import get_instance


def test_get_instance_returns_v13_paths():
    instance = get_instance("v13")

    assert str(instance.install_dir) == "/home/jon/foundry"
    assert str(instance.data_dir) == "/home/jon/foundryuserdata"
    assert instance.pm2_name == "foundry-v13"
    assert instance.modules_dir.name == "modules"


def test_get_instance_rejects_unknown_version():
    try:
        get_instance("v12")
    except ValueError as exc:
        assert "Unknown Foundry version" in str(exc)
    else:
        raise AssertionError("expected ValueError")
