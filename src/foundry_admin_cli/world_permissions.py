"""Active-game document permission/ownership management through Foundry v13 sockets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import FoundryInstance
from .world_client import _default_cookie_path


class PermissionManagementError(RuntimeError):
    """Raised when active-game permissions cannot be managed safely."""


_LEVEL_BY_KEY: dict[str, tuple[str, str, int]] = {
    "NONE": ("None", "NONE", 0),
    "LIMITED": ("Limited", "LIMITED", 1),
    "OBSERVER": ("Observer", "OBSERVER", 2),
    "OWNER": ("Owner", "OWNER", 3),
}
_LEVEL_ALIASES = {
    "0": "NONE",
    "none": "NONE",
    "no-access": "NONE",
    "no access": "NONE",
    "1": "LIMITED",
    "limited": "LIMITED",
    "limit": "LIMITED",
    "2": "OBSERVER",
    "observer": "OBSERVER",
    "observe": "OBSERVER",
    "3": "OWNER",
    "owner": "OWNER",
    "own": "OWNER",
}
_DOCUMENT_TYPES: dict[str, tuple[str, str]] = {
    "actor": ("Actor", "actors"),
    "journal": ("JournalEntry", "journal"),
    "journalentry": ("JournalEntry", "journal"),
    "journal-entry": ("JournalEntry", "journal"),
    "scene": ("Scene", "scenes"),
}
_DOCUMENT_LABELS = {
    "actor": "actor",
    "journal": "journal",
    "journalentry": "journal",
    "journal-entry": "journal",
    "scene": "scene",
}


class SocketWorldPermissionTransport:
    """Node/socket.io transport for Foundry document ownership operations."""

    def __init__(self, *, cookie_path: Path | None = None, timeout_seconds: int = 20) -> None:
        self.cookie_path = cookie_path
        self.timeout_seconds = timeout_seconds

    def _run(self, instance: FoundryInstance, payload: dict[str, Any]) -> dict[str, Any]:
        instance.require_local("game permission socket")
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
  if (input.action !== 'update') return fail(`Unsupported permission action: ${input.action}`);
  socket.emit('modifyDocument', {
    type: input.documentType,
    action: 'update',
    operation: {updates: input.updates}
  }, response => finish({ok: !response.error, response}));
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
            raise PermissionManagementError(f"Foundry permission socket command failed: {exc}") from exc
        stdout = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise PermissionManagementError(f"Foundry permission socket response was not JSON: {completed.stderr.strip()}") from exc
        if not result.get("ok"):
            message = result.get("error") or result.get("response", {}).get("error", {}).get("message") or "socket request failed"
            raise PermissionManagementError(str(message))
        return result

    def get_world_data(self, instance: FoundryInstance) -> dict[str, Any]:
        return self._run(instance, {"action": "get"})["data"]

    def modify_document(self, instance: FoundryInstance, *, document_type: str, updates: list[dict[str, Any]]) -> dict[str, Any]:
        return self._run(instance, {"action": "update", "documentType": document_type, "updates": updates})["response"]


def _default_transport() -> SocketWorldPermissionTransport:
    return SocketWorldPermissionTransport()


def normalize_ownership_level(level: str) -> tuple[str, str, int]:
    key = _LEVEL_ALIASES.get(level.strip().lower())
    if key is None:
        raise PermissionManagementError(f"unknown ownership level: {level}")
    return _LEVEL_BY_KEY[key]


def _level_from_value(value: Any) -> tuple[str, str, int]:
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise PermissionManagementError(f"invalid Foundry ownership level value: {value}") from exc
    for row in _LEVEL_BY_KEY.values():
        if row[2] == numeric:
            return row
    raise PermissionManagementError(f"invalid Foundry ownership level value: {value}")


def _document_type_info(document_type: str) -> tuple[str, str, str]:
    key = document_type.strip().lower()
    if key not in _DOCUMENT_TYPES:
        raise PermissionManagementError(f"unknown document type: {document_type}")
    foundry_type, collection_key = _DOCUMENT_TYPES[key]
    return _DOCUMENT_LABELS[key], foundry_type, collection_key


def _load_state(instance: FoundryInstance, world_id: str, transport: Any | None = None) -> tuple[Any, dict[str, Any], list[dict[str, Any]]]:
    instance.require_local("game permission management")
    active_transport = transport or _default_transport()
    data = active_transport.get_world_data(instance)
    active_world = data.get("world", {}).get("id")
    if active_world != world_id:
        raise PermissionManagementError(f"running world is {active_world}; expected {world_id}")
    users = data.get("users") or []
    if not isinstance(users, list):
        raise PermissionManagementError("Foundry world data users payload must be a list")
    return active_transport, data, [u for u in users if isinstance(u, dict)]


def _entity_id(entity: dict[str, Any]) -> str | None:
    value = entity.get("_id") or entity.get("id")
    return value if isinstance(value, str) and value else None


def _find_user(users: list[dict[str, Any]], user: str) -> dict[str, str]:
    if user.strip().lower() == "default":
        return {"id": "default", "name": "default"}
    matches = [row for row in users if _entity_id(row) == user or row.get("name") == user]
    if not matches:
        raise PermissionManagementError(f"user not found: {user}")
    if len(matches) > 1:
        raise PermissionManagementError(f"ambiguous user: {user}")
    return {"id": str(_entity_id(matches[0])), "name": str(matches[0].get("name"))}


def _documents(data: dict[str, Any], collection_key: str) -> list[dict[str, Any]]:
    documents = data.get(collection_key) or []
    if not isinstance(documents, list):
        raise PermissionManagementError(f"Foundry world data {collection_key} payload must be a list")
    return [document for document in documents if isinstance(document, dict)]


def _find_document(documents: list[dict[str, Any]], document: str, *, label: str) -> dict[str, Any]:
    matches = [row for row in documents if _entity_id(row) == document or row.get("name") == document]
    if not matches:
        raise PermissionManagementError(f"{label} not found: {document}")
    if len(matches) > 1:
        raise PermissionManagementError(f"ambiguous {label}: {document}")
    return matches[0]


def _format_ownership(ownership: Any, users: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if ownership is None:
        ownership = {}
    if not isinstance(ownership, dict):
        raise PermissionManagementError("document ownership must be an object")
    user_names = {_entity_id(user): user.get("name") for user in users if _entity_id(user)}
    formatted: dict[str, dict[str, Any]] = {}
    for subject, raw_level in sorted(ownership.items(), key=lambda item: str(item[0])):
        if not isinstance(subject, str):
            raise PermissionManagementError("document ownership keys must be strings")
        level, level_key, level_value = _level_from_value(raw_level)
        row: dict[str, Any] = {"level": level, "level_key": level_key, "level_value": level_value}
        if subject != "default":
            row["user"] = user_names.get(subject)
        formatted[subject] = row
    return formatted


def _format_document(document: dict[str, Any], *, label: str, users: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": _entity_id(document),
        "name": document.get("name"),
        "type": label,
        "ownership": _format_ownership(document.get("ownership", {}), users),
    }


def audit_permissions(
    instance: FoundryInstance,
    world_id: str,
    *,
    document_type: str | None = None,
    transport: Any | None = None,
) -> dict[str, Any]:
    _, data, users = _load_state(instance, world_id, transport)
    requested = [document_type] if document_type else ["actor", "journal", "scene"]
    result: dict[str, list[dict[str, Any]]] = {}
    for requested_type in requested:
        label, _, collection_key = _document_type_info(requested_type)
        result[label] = [
            _format_document(document, label=label, users=users)
            for document in _documents(data, collection_key)
        ]
    return {"version": instance.version, "world": world_id, "documents": result}


def export_permissions(
    instance: FoundryInstance,
    world_id: str,
    *,
    document_type: str | None = None,
    transport: Any | None = None,
) -> dict[str, Any]:
    result = audit_permissions(instance, world_id, document_type=document_type, transport=transport)
    result["export_version"] = 1
    return result


def set_document_permission(
    instance: FoundryInstance,
    world_id: str,
    *,
    document_type: str,
    document: str,
    user: str,
    level: str,
    transport: Any | None = None,
) -> dict[str, Any]:
    label, foundry_type, collection_key = _document_type_info(document_type)
    level_label, level_key, level_value = normalize_ownership_level(level)
    active_transport, data, users = _load_state(instance, world_id, transport)
    target_user = _find_user(users, user)
    target_document = _find_document(_documents(data, collection_key), document, label=label)
    actual_document_id = _entity_id(target_document)
    if actual_document_id is None:
        raise PermissionManagementError(f"{label} has no id: {document}")
    ownership = target_document.get("ownership") or {}
    if not isinstance(ownership, dict):
        raise PermissionManagementError("document ownership must be an object")
    new_ownership = {str(key): int(value) for key, value in ownership.items()}
    old_value = new_ownership.get(target_user["id"], 0)
    changed = old_value != level_value
    response = None
    if changed:
        new_ownership[target_user["id"]] = level_value
        response = active_transport.modify_document(
            instance,
            document_type=foundry_type,
            updates=[{"_id": actual_document_id, "ownership": new_ownership}],
        )
    return {
        "version": instance.version,
        "world": world_id,
        "changed": changed,
        "reload_required": False,
        "document": {"id": actual_document_id, "name": target_document.get("name"), "type": label},
        "user": target_user,
        "level": level_label,
        "level_key": level_key,
        "level_value": level_value,
        "previous_level_value": old_value,
        "socket_response": response,
    }
