"""Dangerous active-game script execution for Foundry module development."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import FoundryInstance
from .world_client import _default_cookie_path


class ScriptExecutionError(RuntimeError):
    """Raised when active-game script execution is unsafe or fails."""


class SocketWorldScriptTransport:
    """Node transport for GM-scoped Foundry client script execution via MCP Bridge."""

    def __init__(self, *, cookie_path: Path | None = None, timeout_seconds: int = 20) -> None:
        self.cookie_path = cookie_path
        self.timeout_seconds = timeout_seconds

    def _run(self, instance: FoundryInstance, payload: dict[str, Any]) -> dict[str, Any]:
        instance.require_local("game script execution")
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
const timer = setTimeout(() => fail('Timed out waiting for Foundry script response'), input.timeoutMs);
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
function getWorldData() {
  return new Promise(resolve => {
    socket.emit('world', data => {
      if (data && data.world) return resolve(data);
      socket.emit('getJoinData', fallbackData => resolve(fallbackData || data || {}));
    });
  });
}
function callBridge(scriptText) {
  return new Promise((resolve, reject) => {
    const WebSocketImpl = globalThis.WebSocket;
    if (!WebSocketImpl) {
      reject(new Error('Node WebSocket global is unavailable; use Node.js 20+'));
      return;
    }
    const requestId = `fvtt-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const ws = new WebSocketImpl(input.bridgeUrl);
    const bridgeTimer = setTimeout(() => {
      try { ws.close(); } catch {}
      reject(new Error('Timed out waiting for MCP Bridge script response'));
    }, input.timeoutMs);
    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({
        type: 'mcp-query',
        id: requestId,
        data: {
          method: 'foundry-mcp-bridge.executeScript',
          data: {script: scriptText}
        }
      }));
    });
    ws.addEventListener('message', event => {
      let message;
      try { message = JSON.parse(event.data); }
      catch { return; }
      if (message.type !== 'mcp-response' || message.id !== requestId) return;
      clearTimeout(bridgeTimer);
      try { ws.close(); } catch {}
      resolve(message.data);
    });
    ws.addEventListener('error', () => {
      clearTimeout(bridgeTimer);
      reject(new Error('Could not connect to MCP Bridge websocket server'));
    });
  });
}
socket.on('session', async () => {
  try {
    const worldData = await getWorldData();
    const response = await callBridge(input.script);
    finish({ok: true, world: worldData.world || null, response});
  } catch (error) {
    fail(error.message || String(error));
  }
});
socket.on('connect_error', err => fail(err.message));
'''
        bridge_host = payload.get("bridge_host") or "127.0.0.1"
        bridge_port = int(payload.get("bridge_port") or 31415)
        bridge_namespace = payload.get("bridge_namespace") or "/foundry-mcp"
        timeout_ms = int(payload.get("timeoutMs") or self.timeout_seconds * 1000)
        run_payload = {
            **payload,
            "url": instance.url,
            "cookiePath": str(cookie_path),
            "timeoutMs": timeout_ms,
            "bridgeUrl": f"ws://{bridge_host}:{bridge_port}{bridge_namespace}",
        }
        try:
            completed = subprocess.run(
                [instance.node_bin, "-e", script],
                input=json.dumps(run_payload),
                text=True,
                capture_output=True,
                timeout=(timeout_ms / 1000) + 5,
                cwd=instance.install_dir,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ScriptExecutionError(f"Foundry script command failed: {exc}") from exc
        stdout = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ScriptExecutionError(f"Foundry script response was not JSON: {completed.stderr.strip()}") from exc
        if not result.get("ok"):
            raise ScriptExecutionError(str(result.get("error") or "script execution failed"))
        response = result.get("response") or {}
        if isinstance(response, dict) and not response.get("success", False):
            raise ScriptExecutionError(str(response.get("error") or "MCP Bridge script execution failed"))
        return result

    def execute_script(self, instance: FoundryInstance, *, script: str, timeout_seconds: int) -> dict[str, Any]:
        return self._run(instance, {"script": script, "timeoutMs": timeout_seconds * 1000})


def _default_transport() -> SocketWorldScriptTransport:
    return SocketWorldScriptTransport()


def _read_script_source(script: str | None, script_file: Path | None) -> str:
    sources = [source is not None for source in (script, script_file)]
    if sum(sources) != 1:
        raise ScriptExecutionError("exactly one of --script or --script-file is required")
    if script is not None:
        if not script.strip():
            raise ScriptExecutionError("script cannot be empty")
        return script
    assert script_file is not None
    try:
        text = script_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScriptExecutionError(f"could not read script file: {script_file}") from exc
    if not text.strip():
        raise ScriptExecutionError("script file cannot be empty")
    return text


def _extract_result(raw: dict[str, Any]) -> Any:
    if "result" in raw:
        return raw["result"]
    response = raw.get("response")
    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        if "result" in response:
            return response["result"]
    return raw


def execute_world_script(
    instance: FoundryInstance,
    world_id: str,
    *,
    script: str | None = None,
    script_file: Path | None = None,
    dangerously_allow_script: bool = False,
    timeout_seconds: int = 20,
    transport: Any | None = None,
) -> dict[str, Any]:
    """Execute GM-scoped JavaScript in a running Foundry world."""

    instance.require_local("game script execution")
    if not dangerously_allow_script:
        raise ScriptExecutionError("--dangerously-allow-script is required for GM-scoped script execution")
    if timeout_seconds <= 0:
        raise ScriptExecutionError("timeout must be positive")
    script_text = _read_script_source(script, script_file)
    active_transport = transport or _default_transport()
    raw = active_transport.execute_script(instance, script=script_text, timeout_seconds=timeout_seconds)
    active_world = raw.get("world", {}).get("id")
    if active_world != world_id:
        raise ScriptExecutionError(f"running world is {active_world}; expected {world_id}")
    return {
        "version": instance.version,
        "world": world_id,
        "ok": True,
        "result": _extract_result(raw),
    }
