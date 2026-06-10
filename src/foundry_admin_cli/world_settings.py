"""Active-game settings control through Foundry v13 world socket protocol."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import FoundryInstance
from .world_client import _default_cookie_path


class GameSettingError(RuntimeError):
    """Raised when active-game settings cannot be read or changed safely."""


class SocketWorldSettingTransport:
    """Node/socket.io transport for authenticated Foundry Setting document operations."""

    def __init__(self, *, cookie_path: Path | None = None, timeout_seconds: int = 20) -> None:
        self.cookie_path = cookie_path
        self.timeout_seconds = timeout_seconds

    def _run(self, instance: FoundryInstance, payload: dict[str, Any]) -> dict[str, Any]:
        instance.require_local("game settings socket")
        cookie_path = self.cookie_path or _default_cookie_path(instance)
        script = r'''
const fs = require('fs');
const {io} = require('socket.io-client');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const cookieText = fs.readFileSync(input.cookiePath, 'utf8');
const matches = [...cookieText.matchAll(/\bsession\s+([^\s]+)/g)];
if (!matches.length) throw new Error('No persisted world session cookie found; run game login first');
const socket = io(input.url, {
  path: '/socket.io',
  transports: ['websocket'],
  upgrade: false,
  reconnection: false,
  query: {session: matches[matches.length - 1][1]},
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
  if (input.action !== 'set') return fail(`Unsupported settings action: ${input.action}`);
  const jsonValue = JSON.stringify(input.value);
  const request = input.settingId
    ? {type: 'Setting', action: 'update', operation: {updates: [{_id: input.settingId, value: jsonValue}]}}
    : {type: 'Setting', action: 'create', operation: {data: [{key: input.key, value: jsonValue}]}};
  socket.emit('modifyDocument', request, response => finish({ok: !response.error, response}));
});
socket.on('connect_error', err => fail(err.message));
'''
        run_payload = {
            **payload,
            "url": instance.url,
            "cookiePath": str(cookie_path),
            "timeoutMs": self.timeout_seconds * 1000,
        }
        try:
            completed = subprocess.run(
                [instance.node_bin, "-e", script],
                input=json.dumps(run_payload),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds + 5,
                cwd=instance.install_dir,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GameSettingError(f"Foundry settings socket command failed: {exc}") from exc
        stdout = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise GameSettingError(f"Foundry settings socket response was not JSON: {completed.stderr.strip()}") from exc
        if not result.get("ok"):
            message = result.get("error") or result.get("response", {}).get("error", {}).get("message") or "socket request failed"
            raise GameSettingError(str(message))
        return result

    def get_world_data(self, instance: FoundryInstance) -> dict[str, Any]:
        return self._run(instance, {"action": "get"})["data"]

    def modify_setting(self, instance: FoundryInstance, *, setting_id: str | None, key: str, value: Any) -> dict[str, Any]:
        return self._run(instance, {"action": "set", "settingId": setting_id, "key": key, "value": value})["response"]


def _default_transport() -> SocketWorldSettingTransport:
    return SocketWorldSettingTransport()


_KNOWN_SETTINGS: dict[str, dict[str, Any]] = {
    "foundry-mcp-bridge.enabled": {
        "namespace": "foundry-mcp-bridge",
        "key": "enabled",
        "category": "module",
        "scope": "world",
        "config": True,
        "type": "Boolean",
        "default": True,
        "choices": None,
        "range": None,
        "requires_reload": False,
    },
    "foundry-mcp-bridge.connectionType": {
        "namespace": "foundry-mcp-bridge",
        "key": "connectionType",
        "category": "module",
        "scope": "world",
        "config": True,
        "type": "String",
        "default": "auto",
        "choices": {"auto": "Auto (Recommended)", "webrtc": "WebRTC (Internet)", "websocket": "WebSocket (Local Only)"},
        "range": None,
        "requires_reload": False,
    },
    "foundry-mcp-bridge.serverHost": {
        "namespace": "foundry-mcp-bridge",
        "key": "serverHost",
        "category": "module",
        "scope": "world",
        "config": True,
        "type": "String",
        "default": "localhost",
        "choices": None,
        "range": None,
        "requires_reload": False,
        "sensitive": True,
    },
    "foundry-mcp-bridge.serverPort": {
        "namespace": "foundry-mcp-bridge",
        "key": "serverPort",
        "category": "module",
        "scope": "world",
        "config": False,
        "type": "Number",
        "default": 30001,
        "choices": None,
        "range": None,
        "requires_reload": False,
    },
    "foundry-mcp-bridge.allowWriteOperations": {
        "namespace": "foundry-mcp-bridge",
        "key": "allowWriteOperations",
        "category": "module",
        "scope": "world",
        "config": True,
        "type": "Boolean",
        "default": True,
        "choices": None,
        "range": None,
        "requires_reload": False,
    },
    "foundry-mcp-bridge.maxActorsPerRequest": {
        "namespace": "foundry-mcp-bridge",
        "key": "maxActorsPerRequest",
        "category": "module",
        "scope": "world",
        "config": True,
        "type": "Number",
        "default": 10,
        "choices": None,
        "range": {"min": 1, "max": 50, "step": 1},
        "requires_reload": False,
    },
    "foundry-mcp-bridge.mapGenAutoStart": {
        "namespace": "foundry-mcp-bridge",
        "key": "mapGenAutoStart",
        "category": "module",
        "scope": "world",
        "config": False,
        "type": "Boolean",
        "default": True,
        "choices": None,
        "range": None,
        "requires_reload": False,
    },
    "foundry-mcp-bridge.mapGenQuality": {
        "namespace": "foundry-mcp-bridge",
        "key": "mapGenQuality",
        "category": "module",
        "scope": "world",
        "config": False,
        "type": "String",
        "default": "low",
        "choices": {"low": "Low", "medium": "Medium", "high": "High"},
        "range": None,
        "requires_reload": False,
    },
    "core.maxFPS": {
        "namespace": "core",
        "key": "maxFPS",
        "category": "core",
        "scope": "client",
        "config": True,
        "type": "Number",
        "default": 60,
        "choices": None,
        "range": {"min": 10, "max": 60, "step": 10},
        "requires_reload": False,
    },
}


def _load_state(instance: FoundryInstance, world_id: str, transport: Any | None = None) -> tuple[Any, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    instance.require_local("game settings")
    active_transport = transport or _default_transport()
    data = active_transport.get_world_data(instance)
    active_world = data.get("world", {}).get("id")
    if active_world != world_id:
        raise GameSettingError(f"running world is {active_world}; expected {world_id}")
    settings = data.get("settings") or []
    if not isinstance(settings, list):
        raise GameSettingError("Foundry world data settings payload must be a list")
    modules = data.get("modules") or []
    if not isinstance(modules, list):
        raise GameSettingError("Foundry world data modules payload must be a list")
    return active_transport, data, [s for s in settings if isinstance(s, dict)], [m for m in modules if isinstance(m, dict)]


def _split_key(qualified_key: str) -> tuple[str, str]:
    namespace, sep, key = qualified_key.partition(".")
    if not sep or not namespace or not key:
        raise GameSettingError(f"setting key must be namespace.key: {qualified_key}")
    return namespace, key


def _parse_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _setting_id(setting: dict[str, Any]) -> str | None:
    value = setting.get("_id") or setting.get("id")
    return value if isinstance(value, str) else None


def _category(namespace: str, data: dict[str, Any], modules: list[dict[str, Any]]) -> str:
    if namespace == "core":
        return "core"
    system_id = data.get("system", {}).get("id") or data.get("world", {}).get("system")
    if namespace == system_id:
        return "system"
    if any(module.get("id") == namespace for module in modules):
        return "module"
    return "unknown"


def _metadata(qualified_key: str, data: dict[str, Any], modules: list[dict[str, Any]]) -> dict[str, Any]:
    namespace, key = _split_key(qualified_key)
    known = _KNOWN_SETTINGS.get(qualified_key, {})
    return {
        "qualified_key": qualified_key,
        "namespace": known.get("namespace", namespace),
        "key": known.get("key", key),
        "category": known.get("category", _category(namespace, data, modules)),
        "scope": known.get("scope", "world"),
        "config": known.get("config"),
        "type": known.get("type"),
        "default": known.get("default"),
        "choices": known.get("choices"),
        "range": known.get("range"),
        "requires_reload": known.get("requires_reload"),
        "sensitive": bool(known.get("sensitive", False)),
    }


def _format_setting(
    qualified_key: str,
    *,
    raw: dict[str, Any] | None,
    data: dict[str, Any],
    modules: list[dict[str, Any]],
    value_override: Any = None,
    redact: bool = False,
) -> dict[str, Any]:
    meta = _metadata(qualified_key, data, modules)
    value = value_override if value_override is not None else _parse_value(raw.get("value")) if raw is not None else meta.get("default")
    if redact or meta.get("sensitive"):
        value = "[REDACTED]"
    source = "known-metadata" if qualified_key in _KNOWN_SETTINGS else "persisted"
    row = {
        **meta,
        "value": value,
        "mutable_by_cli": meta["scope"] == "world",
        "source": source,
    }
    if not row.get("sensitive"):
        row.pop("sensitive", None)
    return row


def _index_settings(settings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for setting in settings:
        key = setting.get("key")
        if isinstance(key, str) and "." in key:
            indexed[key] = setting
    return indexed


def _matches(row: dict[str, Any], query: str) -> bool:
    haystack = " ".join(str(row.get(k) or "") for k in ("qualified_key", "namespace", "key", "category", "type"))
    choices = row.get("choices")
    if isinstance(choices, dict):
        haystack += " " + " ".join(f"{k} {v}" for k, v in choices.items())
    return query.lower() in haystack.lower()


def list_game_settings(
    instance: FoundryInstance,
    world_id: str,
    *,
    namespace: str | None = None,
    category: str | None = None,
    query: str | None = None,
    config_only: bool = False,
    world_only: bool = False,
    transport: Any | None = None,
) -> dict[str, Any]:
    _, data, settings, modules = _load_state(instance, world_id, transport)
    indexed = _index_settings(settings)
    keys = set(indexed) | set(_KNOWN_SETTINGS)
    rows = [_format_setting(key, raw=indexed.get(key), data=data, modules=modules) for key in keys]
    if namespace:
        rows = [row for row in rows if row["namespace"] == namespace]
    if category:
        rows = [row for row in rows if row["category"] == category]
    if config_only:
        rows = [row for row in rows if row["config"] is True]
    if world_only:
        rows = [row for row in rows if row["scope"] == "world"]
    if query:
        rows = [row for row in rows if _matches(row, query)]
    rows.sort(key=lambda row: (row["scope"] != "world", row["qualified_key"]))
    return {"version": instance.version, "world": world_id, "active_world": data.get("world", {}).get("id"), "settings": rows}


def get_game_setting(instance: FoundryInstance, world_id: str, qualified_key: str, *, transport: Any | None = None) -> dict[str, Any]:
    _, data, settings, modules = _load_state(instance, world_id, transport)
    indexed = _index_settings(settings)
    if qualified_key not in indexed and qualified_key not in _KNOWN_SETTINGS:
        raise GameSettingError(f"setting not found: {qualified_key}")
    return {
        "version": instance.version,
        "world": world_id,
        "setting": _format_setting(qualified_key, raw=indexed.get(qualified_key), data=data, modules=modules),
    }


def set_game_setting(
    instance: FoundryInstance,
    world_id: str,
    qualified_key: str,
    value: Any,
    *,
    value_source: str = "json",
    force_write: bool = False,
    transport: Any | None = None,
) -> dict[str, Any]:
    active_transport, data, settings, modules = _load_state(instance, world_id, transport)
    indexed = _index_settings(settings)
    if qualified_key not in indexed and qualified_key not in _KNOWN_SETTINGS:
        raise GameSettingError(f"setting not found: {qualified_key}")
    current_raw = indexed.get(qualified_key)
    meta = _metadata(qualified_key, data, modules)
    actual_old_value = _parse_value(current_raw.get("value")) if current_raw is not None else meta.get("default")
    current = _format_setting(qualified_key, raw=current_raw, data=data, modules=modules)
    if current["scope"] == "client":
        raise GameSettingError(f"cannot mutate client-scoped setting: {qualified_key}")
    if current["scope"] == "user":
        raise GameSettingError(f"cannot mutate user-scoped setting without a target user: {qualified_key}")
    old_value = actual_old_value
    changed = actual_old_value != value or (force_write and current_raw is None)
    if changed:
        active_transport.modify_setting(instance, setting_id=_setting_id(current_raw) if current_raw else None, key=qualified_key, value=value)
    redact = value_source == "env" or bool(current.get("sensitive"))
    return {
        "version": instance.version,
        "world": world_id,
        "qualified_key": qualified_key,
        "changed": changed,
        "old_value": "[REDACTED]" if redact else old_value,
        "new_value": "[REDACTED]" if redact else value,
        "reload_required": bool(current.get("requires_reload")) and changed,
        "setting": {**current, "value": "[REDACTED]" if redact else value},
    }


def _module_active(modules: list[dict[str, Any]], module_id: str) -> bool:
    for module in modules:
        if module.get("id") == module_id:
            if "active" in module:
                return bool(module.get("active"))
            return True
    return False


def apply_mcp_bridge_settings(
    instance: FoundryInstance,
    world_id: str,
    *,
    server_host: str,
    transport: Any | None = None,
) -> dict[str, Any]:
    if not server_host.strip():
        raise GameSettingError("MCP Bridge server host cannot be empty")
    active_transport, _, _, modules = _load_state(instance, world_id, transport)
    if not _module_active(modules, "foundry-mcp-bridge"):
        raise GameSettingError("foundry-mcp-bridge is not active; run game module enable foundry-mcp-bridge first")
    changes = []
    for key, value, source in [
        ("foundry-mcp-bridge.enabled", True, "json"),
        ("foundry-mcp-bridge.serverHost", server_host, "env"),
        ("foundry-mcp-bridge.mapGenAutoStart", False, "json"),
    ]:
        changes.append(
            set_game_setting(instance, world_id, key, value, value_source=source, force_write=True, transport=active_transport)
        )
    return {
        "version": instance.version,
        "world": world_id,
        "changed": any(change["changed"] for change in changes),
        "reload_required": any(change["reload_required"] for change in changes),
        "changes": [
            {
                "qualified_key": change["qualified_key"],
                "changed": change["changed"],
                "reload_required": change["reload_required"],
                "old_value": change["old_value"],
                "new_value": change["new_value"],
            }
            for change in changes
        ],
    }
