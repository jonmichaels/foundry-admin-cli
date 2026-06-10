from pathlib import Path

import pytest

from foundry_admin_cli.config import ConfigurationError, apply_overrides, get_instance, load_config


def test_get_instance_loads_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDRY_V13_INSTALL_DIR", str(tmp_path / "foundry"))
    monkeypatch.setenv("FOUNDRY_V13_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FOUNDRY_V13_URL", "http://foundry.example.test:30000/")
    monkeypatch.setenv("FOUNDRY_V13_PM2_NAME", "foundry-test")
    monkeypatch.setenv("FOUNDRY_ADMIN_PM2_BIN", "/usr/local/bin/pm2")
    monkeypatch.setenv("FOUNDRY_ADMIN_RUN_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FOUNDRY_ADMIN_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("FOUNDRY_ADMIN_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FOUNDRY_ADMIN_BACKUP_DIR", str(tmp_path / "backup"))
    monkeypatch.setenv("FOUNDRY_ADMIN_NODE_BIN", "/usr/local/bin/node")

    instance = get_instance("v13", config_paths=[])

    assert instance.install_dir == tmp_path / "foundry"
    assert instance.data_dir == tmp_path / "data"
    assert instance.url == "http://foundry.example.test:30000/"
    assert instance.pm2_name == "foundry-test"
    assert instance.pm2_bin == "/usr/local/bin/pm2"
    assert instance.run_home == tmp_path / "home"
    assert instance.projects_dir == tmp_path / "projects"
    assert instance.cache_dir == tmp_path / "cache"
    assert instance.backup_dir == tmp_path / "backup"
    assert instance.node_bin == "/usr/local/bin/node"
    assert instance.modules_dir.name == "modules"


def test_config_file_env_and_process_env_precedence(monkeypatch, tmp_path):
    config_file = tmp_path / "foundry-admin-cli.toml"
    env_file = tmp_path / ".env"
    config_file.write_text(
        """
[shared]
pm2_bin = "/config/pm2"
projects_dir = "/config/projects"

[instances.v13]
install_dir = "/config/foundry"
data_dir = "/config/data"
url = "http://config.example/"
pm2_name = "config-pm2"
""".strip(),
        encoding="utf-8",
    )
    env_file.write_text(
        "\n".join(
            [
                "FOUNDRY_V13_INSTALL_DIR=/env-file/foundry",
                "FOUNDRY_V13_URL=http://env-file.example/",
                "FOUNDRY_ADMIN_PM2_BIN=/env-file/pm2",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("FOUNDRY_V13_INSTALL_DIR", raising=False)
    monkeypatch.delenv("FOUNDRY_V13_DATA_DIR", raising=False)
    monkeypatch.delenv("FOUNDRY_V13_PM2_NAME", raising=False)
    monkeypatch.delenv("FOUNDRY_ADMIN_PM2_BIN", raising=False)
    monkeypatch.delenv("FOUNDRY_ADMIN_RUN_HOME", raising=False)
    monkeypatch.delenv("FOUNDRY_ADMIN_PROJECTS_DIR", raising=False)
    monkeypatch.setenv("FOUNDRY_V13_URL", "http://process.example/")

    config = load_config(config_paths=[config_file], env_files=[env_file])
    instance = get_instance("v13", config=config)

    assert instance.install_dir == Path("/env-file/foundry")
    assert instance.data_dir == Path("/config/data")
    assert instance.url == "http://process.example/"
    assert instance.pm2_name == "config-pm2"
    assert instance.pm2_bin == "/env-file/pm2"
    assert instance.projects_dir == Path("/config/projects")


def test_cli_overrides_win_over_loaded_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDRY_V13_INSTALL_DIR", "/env/foundry")
    monkeypatch.setenv("FOUNDRY_V13_DATA_DIR", "/env/data")
    monkeypatch.setenv("FOUNDRY_V13_URL", "http://env.example/")
    monkeypatch.setenv("FOUNDRY_V13_PM2_NAME", "env-pm2")
    config = load_config(config_paths=[])

    overridden = apply_overrides(
        config,
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://override.example/",
        pm2_name="override-pm2",
        projects_dir=tmp_path / "projects",
    )
    instance = get_instance("v13", config=overridden)

    assert instance.install_dir == tmp_path / "foundry"
    assert instance.data_dir == tmp_path / "data"
    assert instance.url == "http://override.example/"
    assert instance.pm2_name == "override-pm2"
    assert instance.projects_dir == tmp_path / "projects"


def test_get_instance_rejects_missing_required_config(monkeypatch):
    monkeypatch.delenv("FOUNDRY_V13_INSTALL_DIR", raising=False)
    monkeypatch.delenv("FOUNDRY_V13_DATA_DIR", raising=False)
    monkeypatch.delenv("FOUNDRY_V13_URL", raising=False)
    monkeypatch.delenv("FOUNDRY_V13_PM2_NAME", raising=False)

    with pytest.raises(ConfigurationError, match="Missing required configuration"):
        get_instance("v13", config_paths=[], env_files=[])


def test_get_instance_rejects_unknown_version(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDRY_V13_INSTALL_DIR", str(tmp_path / "foundry"))
    monkeypatch.setenv("FOUNDRY_V13_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FOUNDRY_V13_URL", "http://foundry.example.test/")
    monkeypatch.setenv("FOUNDRY_V13_PM2_NAME", "foundry-test")

    with pytest.raises(ValueError, match="Unknown Foundry version"):
        get_instance("v12", config_paths=[])


def test_remote_instance_rejects_local_capabilities(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDRY_V13_INSTALL_DIR", str(tmp_path / "foundry"))
    monkeypatch.setenv("FOUNDRY_V13_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FOUNDRY_V13_URL", "http://remote.example.test/")
    monkeypatch.setenv("FOUNDRY_V13_PM2_NAME", "foundry-test")
    monkeypatch.setenv("FOUNDRY_V13_MODE", "http-only")
    instance = get_instance("v13", config_paths=[])

    with pytest.raises(ConfigurationError, match="requires local"):
        instance.require_local("status")
