"""High-level agent bootstrap orchestration for Foundry MCP Bridge access."""

from __future__ import annotations

import time
from typing import Any

from .admin_client import AdminClient, read_password_from_env
from .config import FoundryInstance
from .license_client import LicenseClient, read_license_from_env
from .packages import install_package, validate_manifest_url
from .process import get_status, wait_until_ready, restart_instance
from .world_client import WorldClient, WorldClientError, read_secret_from_env, resolve_world_user_id
from .world_modules import ModuleSettingError, enable_world_module, list_world_modules
from .world_settings import GameSettingError, apply_mcp_bridge_settings, list_game_settings
from .world_users import UserManagementError, list_game_users, set_game_user_role
from .worlds import configure_world

DEFAULT_MCP_MODULE_ID = "foundry-mcp-bridge"
DEFAULT_MCP_MANIFEST_URL = "https://github.com/jonmichaels/foundry-vtt-mcp/releases/latest/download/module.json"


class BootstrapAgentError(RuntimeError):
    """Raised when agent bootstrap inputs or verification are invalid."""


class BootstrapAgentRunner:
    """Dependency boundary for bootstrap orchestration.

    Tests provide a fake runner; production uses existing CLI primitives.
    """

    def wait(self, instance: FoundryInstance, *, timeout_seconds: float) -> dict[str, Any]:
        return wait_until_ready(instance, timeout_seconds=timeout_seconds)

    def license_status(self, instance: FoundryInstance) -> dict[str, Any]:
        return LicenseClient(instance).status()

    def activate_license(self, instance: FoundryInstance, *, license_env: str) -> dict[str, Any]:
        license_key = read_license_from_env(license_env, env_file=instance.data_dir / ".env")
        return LicenseClient(instance).activate(license_key)

    def status(self, instance: FoundryInstance) -> dict[str, Any]:
        return get_status(instance).to_dict()

    def admin_login(self, instance: FoundryInstance, *, password_env: str) -> dict[str, Any]:
        client = AdminClient(instance)
        password = read_password_from_env(password_env, env_file=instance.data_dir / ".env")
        return client.login(password)

    def install_module(self, instance: FoundryInstance, *, manifest_url: str, module_id: str) -> dict[str, Any]:
        return install_package(
            instance,
            package_type="module",
            manifest=manifest_url,
            package_id=module_id,
            client=AdminClient(instance),
        )

    def run_world(self, instance: FoundryInstance, *, world_id: str) -> dict[str, Any]:
        return configure_world(instance, world_id)

    def return_to_setup(
        self,
        instance: FoundryInstance,
        *,
        world_id: str,
        admin_password_env: str,
    ) -> dict[str, Any]:
        admin_password = read_password_from_env(admin_password_env, env_file=instance.data_dir / ".env")
        return WorldClient(instance).return_to_setup(
            world_id,
            admin_password=admin_password,
            admin_client=AdminClient(instance),
        )

    def restart(self, instance: FoundryInstance, *, timeout_seconds: float) -> dict[str, Any]:
        return restart_instance(instance, timeout_seconds=timeout_seconds)

    def game_login(
        self,
        instance: FoundryInstance,
        *,
        world_id: str,
        user: str,
        password_env: str | None,
        allow_empty_password: bool,
    ) -> dict[str, Any]:
        if allow_empty_password:
            password = ""
        elif password_env:
            password = read_secret_from_env(password_env, env_file=instance.data_dir / ".env")
        else:  # pragma: no cover - validated before runner call
            raise BootstrapAgentError("--gm-password-env is required unless --allow-empty-password is set")
        resolved_user = resolve_world_user_id(instance, world_id, user)
        return WorldClient(instance).login(
            world_id,
            user=resolved_user,
            password=password,
            allow_empty_password=allow_empty_password,
        )

    def list_users(self, instance: FoundryInstance, *, world_id: str) -> dict[str, Any]:
        return list_game_users(instance, world_id)

    def set_user_role(self, instance: FoundryInstance, *, world_id: str, user: str, role: str) -> dict[str, Any]:
        return set_game_user_role(instance, world_id, user, role)

    def enable_module(self, instance: FoundryInstance, *, world_id: str, module_id: str) -> dict[str, Any]:
        return enable_world_module(instance, world_id, module_id)

    def apply_bridge_settings(self, instance: FoundryInstance, *, world_id: str, server_host_env: str) -> dict[str, Any]:
        server_host = read_secret_from_env(server_host_env, env_file=instance.data_dir / ".env")
        return apply_mcp_bridge_settings(instance, world_id, server_host=server_host)

    def game_ping(self, instance: FoundryInstance) -> dict[str, Any]:
        return WorldClient(instance).ping()

    def bridge_probe(self, instance: FoundryInstance, *, world_id: str, module_id: str) -> dict[str, Any]:
        modules = list_world_modules(instance, world_id)["modules"]
        module_row = next((row for row in modules if row.get("id") == module_id), None)
        settings = list_game_settings(instance, world_id, namespace=module_id)["settings"]
        setting_rows = {row["qualified_key"]: row for row in settings}
        required_settings = [
            f"{module_id}.enabled",
            f"{module_id}.serverHost",
            f"{module_id}.mapGenAutoStart",
        ]
        return {
            "installed": module_row is not None,
            "active": bool(module_row and module_row.get("active")),
            "settings_applied": all(key in setting_rows for key in required_settings),
            "module": module_row,
            "settings": required_settings,
        }


def _step(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "result": _sanitize_result(result)}


def _sanitize_result(value: Any) -> Any:
    """Remove low-level transport fields and sensitive values from bootstrap output."""

    if isinstance(value, dict):
        omitted = {"socket_response", "cookie_path", "url", "redirect_url", "admin_redirect_url"}
        sanitized = {key: _sanitize_result(item) for key, item in value.items() if key not in omitted}
        if sanitized.get("qualified_key") == "foundry-mcp-bridge.serverHost":
            for sensitive_key in ("value", "old_value", "new_value", "default"):
                if sensitive_key in sanitized:
                    sanitized[sensitive_key] = "[REDACTED]"
            setting = sanitized.get("setting")
            if isinstance(setting, dict):
                sanitized["setting"] = _sanitize_result({**setting, "qualified_key": "foundry-mcp-bridge.serverHost"})
        return sanitized
    if isinstance(value, list):
        return [_sanitize_result(item) for item in value]
    return value


def _ensure_gm_capable(
    runner: BootstrapAgentRunner,
    instance: FoundryInstance,
    *,
    world_id: str,
    gm_user: str,
) -> dict[str, Any]:
    users_result = runner.list_users(instance, world_id=world_id)
    users = users_result.get("users") or []
    matches = [user for user in users if user.get("id") == gm_user or user.get("name") == gm_user]
    if not matches:
        raise BootstrapAgentError(f"GM user not found after login: {gm_user}")
    if len(matches) > 1:
        raise BootstrapAgentError(f"ambiguous GM user after login: {gm_user}")
    user = matches[0]
    if user.get("role_key") == "GAMEMASTER" or user.get("role_value") == 4:
        return {"changed": False, "user": user}
    role_result = runner.set_user_role(instance, world_id=world_id, user=gm_user, role="gm")
    return {"changed": True, "user": user, "role_update": role_result}


def _module_package_installed(instance: FoundryInstance, module_id: str) -> bool:
    try:
        candidate = (instance.modules_dir / module_id).resolve()
        root = instance.modules_dir.resolve()
    except OSError:
        return False
    if not candidate.is_relative_to(root):
        return False
    return (candidate / "module.json").is_file()


def _wait_for_active_world(
    runner: BootstrapAgentRunner,
    instance: FoundryInstance,
    *,
    world_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    last_status: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        attempts += 1
        last_status = runner.status(instance)
        if last_status.get("active_world") == world_id:
            return {"ready": True, "attempts": attempts, "active_world": world_id}
        time.sleep(1)
    raise BootstrapAgentError(f"running world is {last_status.get('active_world')}; expected {world_id}")


def _game_login_with_retry(
    runner: BootstrapAgentRunner,
    instance: FoundryInstance,
    *,
    world_id: str,
    user: str,
    password_env: str | None,
    allow_empty_password: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() <= deadline:
        try:
            return runner.game_login(
                instance,
                world_id=world_id,
                user=user,
                password_env=password_env,
                allow_empty_password=allow_empty_password,
            )
        except WorldClientError as exc:
            if "running world is" not in str(exc):
                raise
            last_error = exc
            time.sleep(1)
    raise BootstrapAgentError(str(last_error or "game login timed out"))


def _is_transient_world_socket_error(exc: Exception) -> bool:
    message = str(exc)
    return (
        "running world is None" in message
        or "Timed out waiting for Foundry socket response" in message
        or "Module not installed in running world" in message
        or "foundry-mcp-bridge is not active" in message
    )


def _retry_world_socket(operation, *, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() <= deadline:
        try:
            return operation()
        except (UserManagementError, ModuleSettingError, GameSettingError) as exc:
            if not _is_transient_world_socket_error(exc):
                raise
            last_error = exc
            time.sleep(1)
    raise BootstrapAgentError(str(last_error or "world socket operation timed out"))


def bootstrap_agent(
    instance: FoundryInstance,
    *,
    world_id: str,
    gm_user: str,
    gm_password_env: str | None,
    allow_empty_password: bool,
    admin_password_env: str,
    mcp_manifest_url: str = DEFAULT_MCP_MANIFEST_URL,
    mcp_server_host_env: str,
    license_env: str | None = None,
    module_id: str = DEFAULT_MCP_MODULE_ID,
    timeout_seconds: float = 60.0,
    runner: BootstrapAgentRunner | None = None,
) -> dict[str, Any]:
    """Bootstrap a running world for agent access through Foundry MCP Bridge."""

    if not world_id.strip():
        raise BootstrapAgentError("--world cannot be empty")
    if not gm_user.strip():
        raise BootstrapAgentError("--gm-user cannot be empty")
    if allow_empty_password and gm_password_env:
        raise BootstrapAgentError("--gm-password-env cannot be combined with --allow-empty-password")
    if not allow_empty_password and not gm_password_env:
        raise BootstrapAgentError("--gm-password-env is required unless --allow-empty-password is set")
    if not admin_password_env.strip():
        raise BootstrapAgentError("--admin-password-env cannot be empty")
    if not mcp_server_host_env.strip():
        raise BootstrapAgentError("--mcp-server-host-env cannot be empty")
    validate_manifest_url(mcp_manifest_url)

    active_runner = runner or BootstrapAgentRunner()
    steps: list[dict[str, Any]] = []

    steps.append(_step("wait", active_runner.wait(instance, timeout_seconds=timeout_seconds)))
    license_status = active_runner.license_status(instance)
    steps.append(_step("license_status", license_status))
    if license_status.get("license_required"):
        if not license_env:
            raise BootstrapAgentError("Foundry license activation required; pass --license-env")
        steps.append(_step("license_activate", active_runner.activate_license(instance, license_env=license_env)))
        steps.append(_step("wait_after_license", active_runner.wait(instance, timeout_seconds=timeout_seconds)))
    status = active_runner.status(instance)
    steps.append(_step("status", status))
    if status.get("active_world") == world_id and _module_package_installed(instance, module_id):
        steps.append(_step("setup_phase", {"skipped": True, "reason": "target world already active and module installed"}))
    else:
        if status.get("active_world") == world_id:
            steps.append(
                _step(
                    "game_login_for_return_to_setup",
                    _game_login_with_retry(
                        active_runner,
                        instance,
                        world_id=world_id,
                        user=gm_user,
                        password_env=gm_password_env,
                        allow_empty_password=allow_empty_password,
                        timeout_seconds=timeout_seconds,
                    ),
                )
            )
            steps.append(
                _step(
                    "return_to_setup",
                    active_runner.return_to_setup(
                        instance,
                        world_id=world_id,
                        admin_password_env=admin_password_env,
                    ),
                )
            )
            steps.append(_step("wait_after_return_to_setup", active_runner.wait(instance, timeout_seconds=timeout_seconds)))
        steps.append(_step("admin_login", active_runner.admin_login(instance, password_env=admin_password_env)))
        steps.append(
            _step(
                "install_module",
                active_runner.install_module(instance, manifest_url=mcp_manifest_url, module_id=module_id),
            )
        )
        steps.append(_step("run_world", active_runner.run_world(instance, world_id=world_id)))
        steps.append(_step("restart_after_world_run", active_runner.restart(instance, timeout_seconds=timeout_seconds)))
        steps.append(
            _step(
                "wait_for_active_world",
                _wait_for_active_world(
                    active_runner,
                    instance,
                    world_id=world_id,
                    timeout_seconds=timeout_seconds,
                ),
            )
        )
    steps.append(
        _step(
            "game_login",
            _game_login_with_retry(
                active_runner,
                instance,
                world_id=world_id,
                user=gm_user,
                password_env=gm_password_env,
                allow_empty_password=allow_empty_password,
                timeout_seconds=timeout_seconds,
            ),
        )
    )
    steps.append(_step("ensure_gm_user", _retry_world_socket(
        lambda: _ensure_gm_capable(active_runner, instance, world_id=world_id, gm_user=gm_user),
        timeout_seconds=timeout_seconds,
    )))
    module_result = _retry_world_socket(
        lambda: active_runner.enable_module(instance, world_id=world_id, module_id=module_id),
        timeout_seconds=timeout_seconds,
    )
    steps.append(_step("enable_module", module_result))
    module_reload_performed = False
    if module_result.get("reload_required"):
        module_reload_performed = True
        steps.append(_step("restart_after_module_enable", active_runner.restart(instance, timeout_seconds=timeout_seconds)))
        steps.append(
            _step(
                "game_login_after_module_reload",
                _game_login_with_retry(
                    active_runner,
                    instance,
                    world_id=world_id,
                    user=gm_user,
                    password_env=gm_password_env,
                    allow_empty_password=allow_empty_password,
                    timeout_seconds=timeout_seconds,
                ),
            )
        )

    settings_result = _retry_world_socket(
        lambda: active_runner.apply_bridge_settings(
            instance,
            world_id=world_id,
            server_host_env=mcp_server_host_env,
        ),
        timeout_seconds=timeout_seconds,
    )
    steps.append(_step("apply_mcp_bridge_settings", settings_result))

    settings_reload_performed = False
    if settings_result.get("reload_required"):
        settings_reload_performed = True
        steps.append(_step("restart_after_settings", active_runner.restart(instance, timeout_seconds=timeout_seconds)))
        steps.append(
            _step(
                "game_login_after_settings_reload",
                _game_login_with_retry(
                    active_runner,
                    instance,
                    world_id=world_id,
                    user=gm_user,
                    password_env=gm_password_env,
                    allow_empty_password=allow_empty_password,
                    timeout_seconds=timeout_seconds,
                ),
            )
        )

    ping = active_runner.game_ping(instance)
    steps.append(_step("game_ping", ping))
    bridge = _retry_world_socket(
        lambda: active_runner.bridge_probe(instance, world_id=world_id, module_id=module_id),
        timeout_seconds=timeout_seconds,
    )
    steps.append(_step("bridge_probe", bridge))

    verified = bool(ping.get("authenticated") and bridge.get("installed") and bridge.get("active") and bridge.get("settings_applied"))
    if not verified:
        raise BootstrapAgentError("Agent bootstrap verification failed")
    return {
        "version": instance.version,
        "world": world_id,
        "module_id": module_id,
        "reload_required": bool(module_result.get("reload_required") or settings_result.get("reload_required")),
        "reload_performed": module_reload_performed or settings_reload_performed,
        "verified": verified,
        "steps": steps,
        "rollback": [
            f"Disable {module_id}: fvtt --version {instance.version} game module disable {module_id} --world {world_id}",
            f"Remove package if desired: fvtt --version {instance.version} module remove {module_id}",
        ],
    }
