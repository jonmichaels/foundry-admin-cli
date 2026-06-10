"""Active-game user management through Foundry v13 world socket protocol."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import FoundryInstance
from .world_client import _default_cookie_path


class UserManagementError(RuntimeError):
    """Raised when active-game user management cannot complete safely."""


_ROLE_BY_KEY: dict[str, tuple[str, str, int]] = {
    "NONE": ("None", "NONE", 0),
    "PLAYER": ("Player", "PLAYER", 1),
    "TRUSTED": ("Trusted Player", "TRUSTED", 2),
    "ASSISTANT": ("Assistant Gamemaster", "ASSISTANT", 3),
    "GAMEMASTER": ("Gamemaster", "GAMEMASTER", 4),
}
_ROLE_ALIASES = {
    "none": "NONE",
    "player": "PLAYER",
    "trusted": "TRUSTED",
    "trusted-player": "TRUSTED",
    "trusted player": "TRUSTED",
    "assistant": "ASSISTANT",
    "assistant-gm": "ASSISTANT",
    "assistant gm": "ASSISTANT",
    "assistant-gamemaster": "ASSISTANT",
    "assistant gamemaster": "ASSISTANT",
    "gm": "GAMEMASTER",
    "gamemaster": "GAMEMASTER",
    "game-master": "GAMEMASTER",
    "game master": "GAMEMASTER",
}


class SocketWorldUserTransport:
    """Node/socket.io transport for authenticated Foundry User document operations."""

    def __init__(self, *, cookie_path: Path | None = None, timeout_seconds: int = 20) -> None:
        self.cookie_path = cookie_path
        self.timeout_seconds = timeout_seconds

    def _run(self, instance: FoundryInstance, payload: dict[str, Any]) -> dict[str, Any]:
        instance.require_local("game user socket")
        cookie_path = self.cookie_path or _default_cookie_path(instance)
        script = r'''
const fs = require('fs');
const {io} = require('socket.io-client');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const cookieText = fs.readFileSync(input.cookiePath, 'utf8');
const matches = [...cookieText.matchAll(/\bsession\s+([^\s]+)/g)];
if (!matches.length) throw new Error('No persisted world session cookie found; run game login first');
const session = matches[matches.length - 1][1];
const socket = io(input.url, {
  path: '/socket.io',
  transports: ['websocket'],
  upgrade: false,
  reconnection: false,
  query: {session},
  extraHeaders: {Cookie: `session=${session}`},
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
    socket.emit('world', data => {
      if (data && data.world) return finish({ok: true, data});
      socket.emit('getJoinData', fallbackData => finish({ok: true, data: fallbackData || data || {}}));
    });
    return;
  }
  let operation;
  if (input.action === 'create') operation = {data: input.data};
  else if (input.action === 'update') operation = {updates: input.updates};
  else if (input.action === 'delete') operation = {ids: input.ids};
  else return fail(`Unsupported user action: ${input.action}`);
  socket.emit('modifyDocument', {type: 'User', action: input.action, operation}, response => finish({ok: !response.error, response}));
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
            raise UserManagementError(f"Foundry user socket command failed: {exc}") from exc
        stdout = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise UserManagementError(f"Foundry user socket response was not JSON: {completed.stderr.strip()}") from exc
        if not result.get("ok"):
            message = result.get("error") or result.get("response", {}).get("error", {}).get("message") or "socket request failed"
            raise UserManagementError(str(message))
        return result

    def get_world_data(self, instance: FoundryInstance) -> dict[str, Any]:
        return self._run(instance, {"action": "get"})["data"]

    def modify_user(
        self,
        instance: FoundryInstance,
        *,
        action: str,
        data: list[dict[str, Any]] | None = None,
        updates: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._run(instance, {"action": action, "data": data, "updates": updates, "ids": ids})["response"]


def _default_transport() -> SocketWorldUserTransport:
    return SocketWorldUserTransport()


def normalize_user_role(role: str) -> tuple[str, str, int]:
    key = _ROLE_ALIASES.get(role.strip().lower())
    if key is None:
        raise UserManagementError(f"unknown role: {role}")
    return _ROLE_BY_KEY[key]


def _role_from_value(value: Any) -> tuple[str, str, int]:
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise UserManagementError(f"invalid Foundry user role value: {value}") from exc
    for row in _ROLE_BY_KEY.values():
        if row[2] == numeric:
            return row
    raise UserManagementError(f"invalid Foundry user role value: {value}")


def _load_state(instance: FoundryInstance, world_id: str, transport: Any | None = None) -> tuple[Any, list[dict[str, Any]]]:
    instance.require_local("game user management")
    active_transport = transport or _default_transport()
    data = active_transport.get_world_data(instance)
    active_world = data.get("world", {}).get("id")
    if active_world != world_id:
        raise UserManagementError(f"running world is {active_world}; expected {world_id}")
    users = data.get("users") or []
    if not isinstance(users, list):
        raise UserManagementError("Foundry world data users payload must be a list")
    return active_transport, [u for u in users if isinstance(u, dict)]


def _user_id(user: dict[str, Any]) -> str | None:
    value = user.get("_id") or user.get("id")
    return value if isinstance(value, str) and value else None


def _find_user(users: list[dict[str, Any]], user_id: str) -> dict[str, Any]:
    matches = [user for user in users if _user_id(user) == user_id or user.get("name") == user_id]
    if not matches:
        raise UserManagementError(f"user not found: {user_id}")
    if len(matches) > 1:
        raise UserManagementError(f"ambiguous user: {user_id}")
    return matches[0]


def _role_value(user: dict[str, Any]) -> int:
    return _role_from_value(user.get("role"))[2]


def _gm_count(users: list[dict[str, Any]]) -> int:
    return sum(1 for user in users if _role_value(user) == 4)


def _format_user(user: dict[str, Any]) -> dict[str, Any]:
    role_label, role_key, role_value = _role_from_value(user.get("role"))
    return {
        "id": _user_id(user),
        "name": user.get("name"),
        "role": role_label,
        "role_key": role_key,
        "role_value": role_value,
        "active": role_value != 0 if "active" not in user else bool(user.get("active")),
    }


def _response_user(response: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return _format_user({**fallback, **result[0]})
    return _format_user(fallback)


def list_game_users(instance: FoundryInstance, world_id: str, *, transport: Any | None = None) -> dict[str, Any]:
    _, users = _load_state(instance, world_id, transport)
    return {"version": instance.version, "world": world_id, "users": [_format_user(user) for user in users]}


def create_game_user(
    instance: FoundryInstance,
    world_id: str,
    *,
    name: str,
    role: str,
    password: str | None = None,
    transport: Any | None = None,
) -> dict[str, Any]:
    if not name.strip():
        raise UserManagementError("user name cannot be empty")
    role_label, role_key, role_value = normalize_user_role(role)
    active_transport, users = _load_state(instance, world_id, transport)
    if any(user.get("name") == name for user in users):
        raise UserManagementError(f"user already exists: {name}")
    data: dict[str, Any] = {"name": name, "role": role_value}
    if password is not None:
        data["password"] = password
    response = active_transport.modify_user(instance, action="create", data=[data])
    return {
        "version": instance.version,
        "world": world_id,
        "created": True,
        "user": _response_user(response, {"name": name, "role": role_value}),
        "role": role_label,
        "role_key": role_key,
    }


def set_game_user_role(instance: FoundryInstance, world_id: str, user_id: str, role: str, *, transport: Any | None = None) -> dict[str, Any]:
    _, _, role_value = normalize_user_role(role)
    active_transport, users = _load_state(instance, world_id, transport)
    user = _find_user(users, user_id)
    if _role_value(user) == 4 and role_value != 4 and _gm_count(users) <= 1:
        raise UserManagementError("world must have at least one Gamemaster")
    actual_id = _user_id(user)
    response = active_transport.modify_user(instance, action="update", updates=[{"_id": actual_id, "role": role_value}])
    return {"version": instance.version, "world": world_id, "updated": True, "user": _response_user(response, {**user, "role": role_value})}


def set_game_user_password(
    instance: FoundryInstance,
    world_id: str,
    user_id: str,
    password: str,
    *,
    transport: Any | None = None,
) -> dict[str, Any]:
    if not password:
        raise UserManagementError("password cannot be empty")
    active_transport, users = _load_state(instance, world_id, transport)
    user = _find_user(users, user_id)
    actual_id = _user_id(user)
    response = active_transport.modify_user(instance, action="update", updates=[{"_id": actual_id, "password": password}])
    return {
        "version": instance.version,
        "world": world_id,
        "password_changed": True,
        "user": _response_user(response, user),
    }


def disable_game_user(instance: FoundryInstance, world_id: str, user_id: str, *, transport: Any | None = None) -> dict[str, Any]:
    return set_game_user_role(instance, world_id, user_id, "none", transport=transport)


def delete_game_user(
    instance: FoundryInstance,
    world_id: str,
    user_id: str,
    *,
    force: bool = False,
    transport: Any | None = None,
) -> dict[str, Any]:
    if not force:
        raise UserManagementError("user delete requires --force")
    active_transport, users = _load_state(instance, world_id, transport)
    user = _find_user(users, user_id)
    if _role_value(user) == 4 and _gm_count(users) <= 1:
        raise UserManagementError("world must have at least one Gamemaster")
    actual_id = _user_id(user)
    active_transport.modify_user(instance, action="delete", ids=[actual_id])
    return {"version": instance.version, "world": world_id, "deleted": True, "user": actual_id}
