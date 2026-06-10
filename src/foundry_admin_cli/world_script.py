"""Dangerous active-game script execution for Foundry module development."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from .config import ConfigurationError, FoundryInstance
from .world_client import _default_cookie_path, resolve_world_user_id


class ScriptExecutionError(RuntimeError):
    """Raised when active-game script execution is unsafe or fails."""


class BrowserWorldScriptTransport:
    """Headless Chromium/CDP transport for GM-scoped Foundry client script execution."""

    def __init__(
        self,
        *,
        cookie_path: Path | None = None,
        chromium_bin: str | None = None,
    ) -> None:
        self.cookie_path = cookie_path
        self.chromium_bin = chromium_bin

    def _resolve_chromium(self) -> str:
        if self.chromium_bin:
            return self.chromium_bin
        for candidate in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
            found = shutil.which(candidate)
            if found:
                return found
        raise ScriptExecutionError(
            "Chromium is required for standalone script execution; install chromium or set a browser binary"
        )

    def execute_script(self, instance: FoundryInstance, *, script: str, timeout_seconds: int) -> dict[str, Any]:
        instance.require_local("game script execution")
        cookie_path = self.cookie_path or _default_cookie_path(instance)
        chromium_bin = self._resolve_chromium()
        node_script = r'''
const fs = require('fs');
const http = require('http');
const {spawn} = require('child_process');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const cookieText = fs.readFileSync(input.cookiePath, 'utf8');
const parsedBase = new URL(input.baseUrl);
const cookieRows = cookieText.split(/\r?\n/)
  .filter(line => line && !line.startsWith('#'))
  .map(line => line.split('\t'))
  .filter(parts => parts.length >= 7 && parts[5] === 'session');
const matchingRows = cookieRows.filter(parts => {
  const domain = parts[0].replace(/^\./, '');
  return parsedBase.hostname === domain || parsedBase.hostname.endsWith(`.${domain}`);
});
const selected = (matchingRows.length ? matchingRows : cookieRows).at(-1);
if (!selected) throw new Error('No persisted world session cookie found; run game login first');
const session = selected[6];
const timeoutMs = input.timeoutMs;
let chromium;
let ws;
let nextId = 1;
const pending = new Map();
function requestJson(url, method = 'GET') {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = http.request({hostname: parsed.hostname, port: parsed.port, path: parsed.pathname + parsed.search, method}, res => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(body)); }
        catch (error) { reject(error); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}
async function waitForVersion(port, deadline) {
  let lastError;
  while (Date.now() < deadline) {
    try { return await requestJson(`http://127.0.0.1:${port}/json/version`); }
    catch (error) { lastError = error; await new Promise(r => setTimeout(r, 100)); }
  }
  throw lastError || new Error('Timed out waiting for Chromium remote debugging');
}
function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({id, method, params}));
  return new Promise((resolve, reject) => pending.set(id, {resolve, reject}));
}
function cleanup() {
  try { if (ws) ws.close(); } catch {}
  try { if (chromium) chromium.kill('SIGTERM'); } catch {}
}
async function evaluateWithNavigationRetry(params, deadline) {
  let lastError;
  while (Date.now() < deadline) {
    try { return await send('Runtime.evaluate', params); }
    catch (error) {
      lastError = error;
      if (!String(error.message || error).includes('navigated')) throw error;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  }
  throw lastError || new Error('Timed out waiting for stable Foundry page');
}
async function main() {
  const deadline = Date.now() + timeoutMs;
  chromium = spawn(input.chromiumBin, [
    '--headless=new',
    '--disable-gpu',
    '--use-gl=swiftshader',
    '--enable-unsafe-swiftshader',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-dev-shm-usage',
    '--no-sandbox',
    `--user-data-dir=${input.userDataDir}`,
    `--remote-debugging-port=${input.debugPort}`,
    'about:blank'
  ], {stdio: ['ignore', 'pipe', 'pipe']});
  chromium.on('exit', code => {
    for (const {reject} of pending.values()) reject(new Error(`Chromium exited with code ${code}`));
    pending.clear();
  });
  await waitForVersion(input.debugPort, deadline);
  const tab = await requestJson(`http://127.0.0.1:${input.debugPort}/json/new?about:blank`, 'PUT');
  if (!tab?.webSocketDebuggerUrl) throw new Error('No Chromium page websocket available');
  ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, {once: true});
    ws.addEventListener('error', reject, {once: true});
  });
  ws.addEventListener('message', event => {
    let message;
    try { message = JSON.parse(event.data); }
    catch { return; }
    if (!message.id || !pending.has(message.id)) return;
    const {resolve, reject} = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message || JSON.stringify(message.error)));
    else resolve(message.result || {});
  });
  await send('Network.enable');
  const parsed = new URL(input.baseUrl);
  if (!input.loginBody) {
    await send('Network.setCookie', {
      name: 'session',
      value: session,
      url: input.baseUrl,
      path: '/',
      httpOnly: true,
      secure: parsed.protocol === 'https:'
    });
  }
  await send('Runtime.enable');
  await send('Page.enable');
  if (input.loginBody) {
    await send('Page.navigate', {url: new URL('/join', input.baseUrl).toString()});
    await new Promise(resolve => setTimeout(resolve, 500));
    const loginExpression = `fetch('/join', {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: ${JSON.stringify(input.loginBody)}}).then(r => r.json())`;
    const login = await evaluateWithNavigationRetry({
      expression: loginExpression,
      awaitPromise: true,
      returnByValue: true,
      timeout: timeoutMs
    }, deadline);
    if (login.exceptionDetails) throw new Error(login.exceptionDetails.text || 'browser login failed');
    if (login.result.value?.status !== 'success') throw new Error('browser login failed');
  }
  await send('Page.navigate', {url: new URL('/game', input.baseUrl).toString()});
  await new Promise(resolve => setTimeout(resolve, 1500));
  const readyExpression = `new Promise((resolve, reject) => {
    const deadline = Date.now() + ${timeoutMs};
    const check = () => {
      if (globalThis.game?.ready) return resolve({ready: true, world: game.world?.id ?? null});
      if (location.pathname.includes('/join')) return reject(new Error('game session redirected to /join; run game login first'));
      if (Date.now() > deadline) return reject(new Error('Timed out waiting for Foundry game readiness'));
      setTimeout(check, 100);
    };
    check();
  })`;
  const ready = await evaluateWithNavigationRetry({expression: readyExpression, awaitPromise: true, returnByValue: true}, deadline);
  if (ready.exceptionDetails) throw new Error(ready.exceptionDetails.text || 'Foundry readiness check failed');
  const wrappedScript = `Promise.resolve().then(async () => { return await (async () => { ${input.script}\n })(); })`;
  const result = await evaluateWithNavigationRetry({
    expression: wrappedScript,
    awaitPromise: true,
    returnByValue: true,
    timeout: timeoutMs
  }, deadline);
  if (result.exceptionDetails) {
    const details = result.exceptionDetails.exception?.description || result.exceptionDetails.text || 'script execution failed';
    throw new Error(details);
  }
  console.log(JSON.stringify({ok: true, world: ready.result.value.world, result: result.result.value}));
}
main().catch(error => {
  console.log(JSON.stringify({ok: false, error: error.message || String(error)}));
  process.exitCode = 1;
}).finally(cleanup);
'''
        timeout_ms = timeout_seconds * 1000
        with tempfile.TemporaryDirectory(prefix="fvtt-script-chrome-") as user_data_dir:
            login_body = None
            if os.environ.get("FOUNDRY_USER_NAME") and os.environ.get("FOUNDRY_USER_PASSWORD"):
                login_body = urllib.parse.urlencode(
                    {
                        "action": "join",
                        "userid": resolve_world_user_id(
                            instance,
                            getattr(self, "world_id", ""),
                            os.environ["FOUNDRY_USER_NAME"],
                        ),
                        "password": os.environ["FOUNDRY_USER_PASSWORD"],
                    }
                )
            run_payload = {
                "baseUrl": instance.url,
                "cookiePath": str(cookie_path),
                "chromiumBin": chromium_bin,
                "debugPort": _pick_debug_port(instance.version),
                "script": script,
                "loginBody": login_body,
                "timeoutMs": timeout_ms,
                "userDataDir": user_data_dir,
            }
            try:
                completed = subprocess.run(
                    [instance.node_bin, "-e", node_script],
                    input=json.dumps(run_payload),
                    text=True,
                    capture_output=True,
                    timeout=timeout_seconds + 10,
                    cwd=instance.install_dir,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ScriptExecutionError(f"Foundry script command failed: {exc}") from exc
        stdout = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            stderr = completed.stderr.strip()
            raise ScriptExecutionError(f"Foundry script response was not JSON: {stderr}") from exc
        if not result.get("ok"):
            raise ScriptExecutionError(str(result.get("error") or "script execution failed"))
        return result


def _pick_debug_port(version: str) -> int:
    digits = "".join(ch for ch in version if ch.isdigit())
    suffix = int(digits or "13")
    return 9222 + suffix


def _default_transport() -> BrowserWorldScriptTransport:
    return BrowserWorldScriptTransport()


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
    """Execute GM-scoped JavaScript in a running Foundry world through headless Chromium."""

    try:
        instance.require_local("game script execution")
    except ConfigurationError as exc:
        raise ScriptExecutionError(str(exc)) from exc
    if not dangerously_allow_script:
        raise ScriptExecutionError("--dangerously-allow-script is required for GM-scoped script execution")
    if timeout_seconds <= 0:
        raise ScriptExecutionError("timeout must be positive")
    script_text = _read_script_source(script, script_file)
    active_transport = transport or _default_transport()
    setattr(active_transport, "world_id", world_id)
    raw = active_transport.execute_script(instance, script=script_text, timeout_seconds=timeout_seconds)
    active_world = raw.get("world")
    if active_world != world_id:
        raise ScriptExecutionError(f"running world is {active_world}; expected {world_id}")
    return {
        "version": instance.version,
        "world": world_id,
        "ok": True,
        "result": raw.get("result"),
    }
