"""Active-world module configuration through Foundry v13 world socket protocol."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import FoundryInstance
from .world_client import _default_cookie_path


class ModuleSettingError(RuntimeError):
    """Raised when active-world module settings cannot be read or changed."""


class SocketWorldModuleTransport:
    """Node/socket.io transport for Foundry's authenticated world socket."""

    def __init__(self, *, cookie_path: Path | None = None, timeout_seconds: int = 20) -> None:
        self.cookie_path = cookie_path
        self.timeout_seconds = timeout_seconds

    def _run(self, instance: FoundryInstance, payload: dict[str, Any]) -> dict[str, Any]:
        cookie_path = self.cookie_path or _default_cookie_path(instance)
        script = r'''
const fs = require('fs');
const {io} = require('socket.io-client');

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const cookieText = fs.readFileSync(input.cookiePath, 'utf8');
const match = cookieText.match(/\bsession\s+([^\s]+)/);
if (!match) throw new Error('No persisted world session cookie found; run world login first');
const session = match[1];
const socket = io(input.url, {
  path: '/socket.io',
  transports: ['websocket'],
  upgrade: false,
  reconnection: false,
  query: {session},
  cookie: false
});
let done = false;
const timer = setTimeout(() => fail('Timed out waiting for Foundry socket response'), input.timeoutMs);
function finish(data) {
  if (done) return;
  done = true;
  clearTimeout(timer);
  console.log(JSON.stringify(data));
  socket.disconnect();
}
function fail(message) {
  finish({ok: false, error: message});
  process.exitCode = 1;
}
socket.on('session', () => {
  if (input.action === 'get') {
    socket.emit('world', data => finish({ok: true, data}));
    return;
  }
  const request = input.settingId
    ? {type: 'Setting', action: 'update', operation: {updates: [{_id: input.settingId, value: JSON.stringify(input.value)}]}}
    : {type: 'Setting', action: 'create', operation: {data: [{key: 'core.moduleConfiguration', value: JSON.stringify(input.value)}]}};
  socket.emit('modifyDocument', request, response => finish({ok: !response.error, response}));
});
socket.on('connect_error', err => fail(err.message));
'''
        command = ["node", "-e", script]
        run_payload = {
            **payload,
            "url": instance.url,
            "cookiePath": str(cookie_path),
            "timeoutMs": self.timeout_seconds * 1000,
        }
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(run_payload),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds + 5,
                cwd=instance.install_dir,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ModuleSettingError(f"Foundry socket command failed: {exc}") from exc
        stdout = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ModuleSettingError(f"Foundry socket response was not JSON: {completed.stderr.strip()}") from exc
        if not result.get("ok"):
            message = result.get("error") or result.get("response", {}).get("error", {}).get("message") or "socket request failed"
            raise ModuleSettingError(str(message))
        return result

    def get_world_data(self, instance: FoundryInstance) -> dict[str, Any]:
        return self._run(instance, {"action": "get"})["data"]

    def modify_setting(self, instance: FoundryInstance, *, setting_id: str | None, value: dict[str, bool]) -> dict[str, Any]:
        return self._run(instance, {"action": "set", "settingId": setting_id, "value": value})["response"]


def _default_transport() -> SocketWorldModuleTransport:
    return SocketWorldModuleTransport()


def _parse_module_configuration(settings: list[dict[str, Any]]) -> tuple[str | None, dict[str, bool]]:
    for setting in settings:
        if setting.get("key") != "core.moduleConfiguration":
            continue
        value = setting.get("value")
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ModuleSettingError("core.moduleConfiguration is not valid JSON") from exc
        elif isinstance(value, dict):
            parsed = value
        else:
            raise ModuleSettingError("core.moduleConfiguration must be an object")
        if not isinstance(parsed, dict):
            raise ModuleSettingError("core.moduleConfiguration must be an object")
        cleaned: dict[str, bool] = {}
        for key, value in parsed.items():
            if not isinstance(key, str):
                raise ModuleSettingError("core.moduleConfiguration module ids must be strings")
            if not isinstance(value, bool):
                raise ModuleSettingError("core.moduleConfiguration values must be boolean")
            cleaned[key] = value
        return setting.get("_id"), cleaned
    return None, {}


def _load_state(instance: FoundryInstance, world_id: str, transport: Any | None = None) -> tuple[Any, dict[str, Any], str | None, dict[str, bool], list[dict[str, Any]]]:
    active_transport = transport or _default_transport()
    data = active_transport.get_world_data(instance)
    active_world = data.get("world", {}).get("id")
    if active_world != world_id:
        raise ModuleSettingError(f"running world is {active_world}; expected {world_id}")
    modules = data.get("modules") or []
    if not isinstance(modules, list):
        raise ModuleSettingError("Foundry world data modules payload must be a list")
    settings = data.get("settings") or []
    if not isinstance(settings, list):
        raise ModuleSettingError("Foundry world data settings payload must be a list")
    setting_id, configuration = _parse_module_configuration(settings)
    return active_transport, data, setting_id, configuration, modules


def _module_ids(modules: list[dict[str, Any]]) -> set[str]:
    return {m["id"] for m in modules if isinstance(m, dict) and isinstance(m.get("id"), str)}


def list_world_modules(instance: FoundryInstance, world_id: str, *, transport: Any | None = None) -> dict[str, Any]:
    _, _, _, configuration, modules = _load_state(instance, world_id, transport)
    rows = []
    for module in sorted(modules, key=lambda m: str(m.get("id", ""))):
        module_id = module.get("id")
        if not isinstance(module_id, str):
            continue
        rows.append(
            {
                "id": module_id,
                "title": module.get("title"),
                "version": module.get("version"),
                "active": bool(configuration.get(module_id, False)),
            }
        )
    return {"version": instance.version, "world": world_id, "modules": rows, "reload_required": False}


def _write_configuration(
    instance: FoundryInstance,
    world_id: str,
    new_configuration: dict[str, bool],
    *,
    transport: Any | None = None,
) -> dict[str, Any]:
    transport, _, setting_id, old_configuration, modules = _load_state(instance, world_id, transport)
    installed = _module_ids(modules)
    unknown = sorted(mid for mid in new_configuration if mid not in installed)
    if unknown:
        raise ModuleSettingError(f"Module not installed in running world: {', '.join(unknown)}")
    complete_configuration = {mid: bool(new_configuration.get(mid, False)) for mid in sorted(installed)}
    changed = complete_configuration != {mid: bool(old_configuration.get(mid, False)) for mid in sorted(installed)}
    response = None
    if changed:
        response = transport.modify_setting(instance, setting_id=setting_id, value=complete_configuration)
    return {
        "version": instance.version,
        "world": world_id,
        "changed": changed,
        "reload_required": changed,
        "modules": complete_configuration,
        "socket_response": response,
    }


def enable_world_module(instance: FoundryInstance, world_id: str, module_id: str, *, transport: Any | None = None) -> dict[str, Any]:
    _, _, _, configuration, modules = _load_state(instance, world_id, transport)
    if module_id not in _module_ids(modules):
        raise ModuleSettingError(f"Module not installed in running world: {module_id}")
    configuration[module_id] = True
    result = _write_configuration(instance, world_id, configuration, transport=transport)
    result["module"] = module_id
    return result


def disable_world_module(instance: FoundryInstance, world_id: str, module_id: str, *, transport: Any | None = None) -> dict[str, Any]:
    _, _, _, configuration, modules = _load_state(instance, world_id, transport)
    if module_id not in _module_ids(modules):
        raise ModuleSettingError(f"Module not installed in running world: {module_id}")
    configuration[module_id] = False
    result = _write_configuration(instance, world_id, configuration, transport=transport)
    result["module"] = module_id
    return result


def set_world_modules(instance: FoundryInstance, world_id: str, module_ids: list[str], *, transport: Any | None = None) -> dict[str, Any]:
    _, _, _, _, modules = _load_state(instance, world_id, transport)
    installed = _module_ids(modules)
    requested = {mid for mid in module_ids if mid}
    unknown = sorted(requested - installed)
    if unknown:
        raise ModuleSettingError(f"Module not installed in running world: {', '.join(unknown)}")
    return _write_configuration(instance, world_id, {mid: mid in requested for mid in installed}, transport=transport)
