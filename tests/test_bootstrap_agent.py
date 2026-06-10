import pytest

from foundry_admin_cli.bootstrap_agent import BootstrapAgentError, BootstrapAgentRunner, bootstrap_agent
from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.world_users import UserManagementError


def instance(tmp_path):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-test",
    )


class FakeRunner(BootstrapAgentRunner):
    def __init__(self, *, users=None, module_changed=True, settings_changed=True, license_required=False, active_initial=False):
        self.calls = []
        self.license_required = license_required
        self.users = users if users is not None else [
            {"id": "gm-id", "name": "Gamemaster", "role_key": "GAMEMASTER", "role_value": 4}
        ]
        self.module_changed = module_changed
        self.settings_changed = settings_changed
        self.world_started = active_initial

    def wait(self, instance, *, timeout_seconds):
        self.calls.append(("wait", timeout_seconds))
        return {"ready": True}

    def license_status(self, instance):
        self.calls.append(("license_status",))
        return {"license_required": self.license_required}

    def activate_license(self, instance, *, license_env):
        self.calls.append(("activate_license", license_env))
        return {"changed": True, "license_required": False}

    def status(self, instance):
        self.calls.append(("status",))
        return {"active_world": "agent-world" if self.world_started else None}

    def admin_login(self, instance, *, password_env):
        self.calls.append(("admin_login", password_env))
        return {"authenticated": True}

    def install_module(self, instance, *, manifest_url, module_id):
        self.calls.append(("install_module", manifest_url, module_id))
        return {"changed": True, "id": module_id}

    def run_world(self, instance, *, world_id):
        self.calls.append(("run_world", world_id))
        self.world_started = True
        return {"world": world_id, "restart_required": True}

    def return_to_setup(self, instance, *, world_id, admin_password_env):
        self.calls.append(("return_to_setup", world_id, admin_password_env))
        self.world_started = False
        return {"shutdown": True, "setup_authenticated": True}

    def restart(self, instance, *, timeout_seconds):
        self.calls.append(("restart", timeout_seconds))
        return {"ready": True}

    def game_login(self, instance, *, world_id, user, password_env, allow_empty_password):
        self.calls.append(("game_login", world_id, user, password_env, allow_empty_password))
        return {"authenticated": True, "user": user, "world": world_id}

    def list_users(self, instance, *, world_id):
        self.calls.append(("list_users", world_id))
        return {"users": self.users}

    def set_user_role(self, instance, *, world_id, user, role):
        self.calls.append(("set_user_role", world_id, user, role))
        return {"updated": True}

    def enable_module(self, instance, *, world_id, module_id):
        self.calls.append(("enable_module", world_id, module_id))
        return {"changed": self.module_changed, "reload_required": self.module_changed, "socket_response": {"raw": True}}

    def apply_bridge_settings(self, instance, *, world_id, server_host_env):
        self.calls.append(("apply_bridge_settings", world_id, server_host_env))
        return {"changed": self.settings_changed, "reload_required": False}

    def game_ping(self, instance):
        self.calls.append(("game_ping",))
        return {"authenticated": True}

    def bridge_probe(self, instance, *, world_id, module_id):
        self.calls.append(("bridge_probe", world_id, module_id))
        return {"installed": True, "active": True, "settings_applied": True}


def test_bootstrap_agent_orchestrates_install_launch_login_enable_settings_and_reload(tmp_path):
    runner = FakeRunner(module_changed=True)

    result = bootstrap_agent(
        instance(tmp_path),
        world_id="agent-world",
        gm_user="Gamemaster",
        gm_password_env=None,
        allow_empty_password=True,
        admin_password_env="FOUNDRY_ADMIN_PASSWORD",
        mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
        mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
        runner=runner,
    )

    assert result["world"] == "agent-world"
    assert result["module_id"] == "foundry-mcp-bridge"
    assert result["reload_performed"] is True
    assert result["verified"] is True
    assert "socket_response" not in str(result)
    assert "cookie_path" not in str(result)
    assert "redirect_url" not in str(result)
    assert [call[0] for call in runner.calls] == [
        "wait",
        "license_status",
        "status",
        "admin_login",
        "install_module",
        "run_world",
        "restart",
        "status",
        "game_login",
        "list_users",
        "enable_module",
        "restart",
        "game_login",
        "apply_bridge_settings",
        "game_ping",
        "bridge_probe",
    ]


def test_bootstrap_agent_promotes_existing_non_gm_user(tmp_path):
    runner = FakeRunner(users=[{"id": "agent-id", "name": "Agent", "role_key": "PLAYER", "role_value": 1}])

    bootstrap_agent(
        instance(tmp_path),
        world_id="agent-world",
        gm_user="Agent",
        gm_password_env="FOUNDRY_USER_PASSWORD",
        allow_empty_password=False,
        admin_password_env="FOUNDRY_ADMIN_PASSWORD",
        mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
        mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
        runner=runner,
    )

    assert ("set_user_role", "agent-world", "Agent", "gm") in runner.calls


def test_bootstrap_agent_returns_active_world_to_setup_when_module_missing(tmp_path):
    runner = FakeRunner(active_initial=True)

    bootstrap_agent(
        instance(tmp_path),
        world_id="agent-world",
        gm_user="Gamemaster",
        gm_password_env=None,
        allow_empty_password=True,
        admin_password_env="FOUNDRY_ADMIN_PASSWORD",
        mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
        mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
        runner=runner,
    )

    names = [call[0] for call in runner.calls]
    assert "return_to_setup" in names
    assert names.index("return_to_setup") < names.index("install_module")


def test_bootstrap_agent_rejects_password_env_with_empty_password(tmp_path):
    with pytest.raises(BootstrapAgentError, match="cannot be combined"):
        bootstrap_agent(
            instance(tmp_path),
            world_id="agent-world",
            gm_user="Gamemaster",
            gm_password_env="FOUNDRY_USER_PASSWORD",
            allow_empty_password=True,
            admin_password_env="FOUNDRY_ADMIN_PASSWORD",
            mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
            mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
            runner=FakeRunner(),
        )


def test_bootstrap_agent_requires_password_source(tmp_path):
    with pytest.raises(BootstrapAgentError, match="--gm-password-env is required"):
        bootstrap_agent(
            instance(tmp_path),
            world_id="agent-world",
            gm_user="Gamemaster",
            gm_password_env=None,
            allow_empty_password=False,
            admin_password_env="FOUNDRY_ADMIN_PASSWORD",
            mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
            mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
            runner=FakeRunner(),
        )


def test_bootstrap_agent_activates_license_when_required(tmp_path):
    runner = FakeRunner(license_required=True)

    result = bootstrap_agent(
        instance(tmp_path),
        world_id="agent-world",
        gm_user="Gamemaster",
        gm_password_env=None,
        allow_empty_password=True,
        admin_password_env="FOUNDRY_ADMIN_PASSWORD",
        license_env="FOUNDRY_LICENSE",
        mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
        mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
        runner=runner,
    )

    assert result["verified"] is True
    assert ("activate_license", "FOUNDRY_LICENSE") in runner.calls


def test_bootstrap_agent_fails_cleanly_when_license_required_without_env(tmp_path):
    with pytest.raises(BootstrapAgentError, match="license activation required"):
        bootstrap_agent(
            instance(tmp_path),
            world_id="agent-world",
            gm_user="Gamemaster",
            gm_password_env=None,
            allow_empty_password=True,
            admin_password_env="FOUNDRY_ADMIN_PASSWORD",
            mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
            mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
            runner=FakeRunner(license_required=True),
        )


def test_bootstrap_agent_redacts_nested_mcp_bridge_server_host_change_values(tmp_path):
    class LeakySettingsRunner(FakeRunner):
        def apply_bridge_settings(self, instance, *, world_id, server_host_env):
            self.calls.append(("apply_bridge_settings", world_id, server_host_env))
            return {
                "changed": True,
                "reload_required": False,
                "changes": [
                    {
                        "qualified_key": "foundry-mcp-bridge.serverHost",
                        "changed": True,
                        "reload_required": False,
                        "old_value": "old-private-host.example",
                        "new_value": "new-private-host.example",
                    },
                    {
                        "qualified_key": "foundry-mcp-bridge.enabled",
                        "changed": False,
                        "reload_required": False,
                        "old_value": True,
                        "new_value": True,
                    },
                ],
            }

    result = bootstrap_agent(
        instance(tmp_path),
        world_id="agent-world",
        gm_user="Gamemaster",
        gm_password_env=None,
        allow_empty_password=True,
        admin_password_env="FOUNDRY_ADMIN_PASSWORD",
        mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
        mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
        runner=LeakySettingsRunner(),
    )

    rendered = str(result)
    assert "old-private-host.example" not in rendered
    assert "new-private-host.example" not in rendered
    settings_step = next(step for step in result["steps"] if step["name"] == "apply_mcp_bridge_settings")
    host_change = settings_step["result"]["changes"][0]
    assert host_change["old_value"] == "[REDACTED]"
    assert host_change["new_value"] == "[REDACTED]"
    enabled_change = settings_step["result"]["changes"][1]
    assert enabled_change["old_value"] is True
    assert enabled_change["new_value"] is True


def test_bootstrap_agent_retries_transient_world_socket_not_ready_after_login(tmp_path):
    class TransientSocketRunner(FakeRunner):
        def __init__(self):
            super().__init__()
            self.list_user_attempts = 0

        def list_users(self, instance, *, world_id):
            self.calls.append(("list_users", world_id))
            self.list_user_attempts += 1
            if self.list_user_attempts == 1:
                raise UserManagementError("running world is None; expected agent-world")
            return {"users": self.users}

    runner = TransientSocketRunner()

    result = bootstrap_agent(
        instance(tmp_path),
        world_id="agent-world",
        gm_user="Gamemaster",
        gm_password_env=None,
        allow_empty_password=True,
        admin_password_env="FOUNDRY_ADMIN_PASSWORD",
        mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
        mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
        timeout_seconds=2,
        runner=runner,
    )

    assert result["verified"] is True
    assert [call[0] for call in runner.calls].count("list_users") == 2


def test_bootstrap_agent_does_not_retry_non_transient_world_socket_errors(tmp_path):
    class ValidationFailureRunner(FakeRunner):
        def list_users(self, instance, *, world_id):
            self.calls.append(("list_users", world_id))
            raise UserManagementError("GM user not found")

    runner = ValidationFailureRunner()

    with pytest.raises(UserManagementError, match="GM user not found"):
        bootstrap_agent(
            instance(tmp_path),
            world_id="agent-world",
            gm_user="Gamemaster",
            gm_password_env=None,
            allow_empty_password=True,
            admin_password_env="FOUNDRY_ADMIN_PASSWORD",
            mcp_manifest_url="https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json",
            mcp_server_host_env="FOUNDRY_MCP_BRIDGE_HOST",
            timeout_seconds=2,
            runner=runner,
        )

    assert [call[0] for call in runner.calls].count("list_users") == 1
