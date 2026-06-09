# Foundry v13 Setup/Admin Protocol Research

Date: 2026-06-09

## Scope

Initial source inspection for implementing `foundry-admin-cli` without modifying Foundry core and without relying on Foundry MCP Bridge for bootstrap operations.

Target install inspected: `/home/jon/foundry`.

## Source files inspected

- `/home/jon/foundry/dist/server/views/setup.mjs`
- `/home/jon/foundry/dist/server/views/auth.mjs`
- `/home/jon/foundry/dist/server/views/join.mjs`
- `/home/jon/foundry/dist/server/sockets.mjs`
- `/home/jon/foundry/dist/server/express.mjs`
- `/home/jon/foundry/dist/packages/views.mjs`
- `/home/jon/foundry/dist/packages/installer.mjs`
- `/home/jon/foundry/dist/packages/world.mjs`
- `/home/jon/foundry/dist/database/documents/setting.mjs`

## Confirmed setup/admin actions

`SetupView` is the main setup/admin endpoint.

Important source facts from `dist/server/views/setup.mjs`:

- `SetupView.route = "/setup"`
- `SetupView.socket = "getSetupData"`
- `SetupView._methods = ["get", "post"]`
- `handlePost()` dispatches by `body.action`.

Confirmed `POST /setup` action values:

| action | Server call |
|---|---|
| `adminLogout` | `sessions.logoutAdmin(req, res)` |
| `adminConfigure` | `this.updateServerConfiguration(req)` |
| `adminPassword` | private admin password test helper |
| `checkPackage` | `packages.checkPackage(body)` |
| `getPackageFromRemoteManifest` | `packages.getPackageFromRemoteManifest(body)` |
| `getPackages` | `packages.getPackages(body)` |
| `installPackage` | `packages.installPackage(body)` |
| `resetPackages` | `packages.resetPackages(body)` |
| `uninstallPackage` | `packages.uninstallPackage(body)` |
| `lockPackage` | `packages.lockPackage(body)` |
| `migratePackageManifest` | `packages.migratePackageManifest(body)` |
| `manageModule` | `Module.createOrUpdate(body)` |
| `createWorld` | `World.create(body)` |
| `editWorld` | `World.update(body)` |
| `launchWorld` | `World.launch(body.world)` |
| backup/snapshot actions | `packages.handle*` helpers |

This strongly suggests most setup-level package/world management can be reproduced through authenticated HTTP POSTs to `/setup` rather than browser clicking.

## Admin authentication

`AuthView` handles setup/admin authentication:

- Source: `/home/jon/foundry/dist/server/views/auth.mjs`
- `AuthView.route = "/auth"`
- `AuthView._methods = ["get", "post"]`
- `handlePost()` calls `sessions.authenticateAdmin(req, res)`.
- On success when no world is active, it redirects to `/setup`.

`SetupView.handleGet()` checks `sessions.authenticateAdmin(req, res).success` and redirects unauthenticated users to `/auth`.

Implication: CLI should maintain cookies/session and authenticate via `/auth` before setup-level POST operations.

## World login

`JoinView` handles world login:

- Source: `/home/jon/foundry/dist/server/views/join.mjs`
- `JoinView.route = "/join"`
- `JoinView._methods = ["get", "post"]`
- `handlePost()` action `join` calls `sessions.authenticateUser(req, res)`.
- `handlePost()` action `shutdown` requires admin auth and deactivates the active world.

`dist/sessions.mjs` confirms:

- `authenticateUser()` expects body fields `userid` and `password`.
- Successful login stores `session.worlds[game.world.id] = user.id`.

Implication: CLI can likely log into a running world via authenticated `POST /join` with `action=join`, `userid`, and `password`, using a cookie jar.

## Package install/update/remove

`dist/packages/views.mjs` exposes setup package functions used by `SetupView`:

- `getPackages({ type = "system" })`
- `getPackageFromRemoteManifest({ type = "module", manifest = "" })`
- `checkPackage({ type, id, manifest, forceSidegrade = false, strict = true })`
- `installPackage({ type, id, manifest, force = false })`
- `resetPackages()`
- `uninstallPackage({ type, id })`
- `lockPackage({ type, id, shouldLock })`

`installPackage` requires a manifest URL. ID-only package registry lookup may need a separate registry call or Foundry repository helper; do not assume ID-only install until researched.

`dist/packages/installer.mjs` confirms extracted packages are installed into the package type directory and replaced safely by Foundry's installer logic.

Implication: CLI should use Foundry's own `/setup` actions for package install/update/remove where possible instead of manually unpacking packages.

## World create/edit/run

`SetupView.handlePost()` calls:

- `World.create(body)` for `createWorld`
- `World.update(body)` for `editWorld`
- `World.launch(body.world)` for `launchWorld`

Implication: CLI should prefer `/setup` POST actions for world create/edit/run over direct `world.json` creation.

## Active-world module management: key finding

`dist/database/documents/setting.mjs` handles module configuration:

- Setting key: `core.moduleConfiguration`
- On create/update, if key is `core.moduleConfiguration` and `updateWorld !== false`, Foundry calls `game.world?.onUpdateModuleConfiguration(this.value)`.
- Validation/coercion logic adjusts required/incompatible modules:
  - required system/world relationships are forced enabled when compatible
  - incompatible world modules are forced disabled

Relevant source snippets after formatting:

```js
"core.moduleConfiguration" === this.key && !1 !== options.updateWorld && game.world?.onUpdateModuleConfiguration(this.value)
```

```js
static async set(key, value, options) {
  value = typeof value == "string" ? value : JSON.stringify(value);
  let setting = await this.find({ key });
  return setting.length ? setting.shift().update({ value }, options) : this.create({ key, value }, options);
}
```

Implications:

1. Active-world module state is stored as world Setting document `core.moduleConfiguration`.
2. Correct module enable/disable likely requires authenticated world access and `db.Setting.set("core.moduleConfiguration", value)` or the client/UI equivalent.
3. Direct LevelDB edits may be possible but should be a fallback only after identifying the exact LevelDB key/value shape and reload semantics.
4. MCP must not be used for this feature. The CLI must bootstrap MCP Bridge by changing `core.moduleConfiguration` independently.

## Socket.IO facts

`dist/server/sockets.mjs` registers view socket handlers:

- On connection, `sockets.activate(socket, views)` emits a `session` event.
- For each registered View with a `socket` property, it registers `socket.on(view.socket, request => view.handleSocket(session, request))`.

Setup has `socket = "getSetupData"`, auth has `socket = "getAuthData"`, join has `socket = "getJoinData"`.

However, setup mutations discovered so far are HTTP POST actions through `/setup`, not necessarily Socket.IO events. Prefer HTTP POST for setup mutations unless further client-source research proves Socket.IO is required.

## Active-world module management client flow

Source: `/home/jon/foundry/client/applications/sidebar/apps/module-management.mjs`.

Key findings:

- The UI setting name is `ModuleManagement.SETTING = "moduleConfiguration"`.
- The submitted form data is a flat object mapping module IDs to booleans.
- On submit, the UI validates installed module IDs and dependency relationships, then calls:

```js
const oldSettings = game.settings.get("core", ModuleManagement.SETTING);
const requiresReload = !foundry.utils.isEmpty(foundry.utils.diffObject(oldSettings, newSettings));
if ( requiresReload ) foundry.applications.settings.SettingsConfig.reloadConfirm({world: true});
await game.settings.set("core", ModuleManagement.SETTING, newSettings);
```

Implications:

1. The canonical client-side write path is `game.settings.set("core", "moduleConfiguration", newSettings)`.
2. The persisted server-side Setting key is `core.moduleConfiguration`.
3. A changed module set requires a world reload/restart prompt in the UI.
4. CLI implementation should mirror the dependency-validation behavior before writing; if using direct settings storage as fallback, it must update the setting value to a JSON string and then reload/restart the world.
5. Since `game.settings.set` requires an authenticated running world client, a non-browser CLI path probably needs either a world-authenticated socket/document operation or a source-verified direct LevelDB setting update plus world reload.

Read-only LevelDB inspection of `/home/jon/foundryuserdata/Data/worlds/module-test-dnd5e/data/settings` found the record key shape:

```text
!settings!qV40ctYPpWQbhxuC
{"key":"core.moduleConfiguration","value":"{...module boolean map...}"}
```

The exact Setting document `_id` is not derived from the setting key; direct updates should therefore locate the record by JSON `key == "core.moduleConfiguration"`, not hardcode an ID.

## Implemented admin-session probe findings

`foundry-admin-cli` now has a source-driven urllib cookie-jar client in `src/foundry_admin_cli/admin_client.py`.

Confirmed client payloads from v13 source:

| CLI operation | HTTP request | Payload | Mutates state? |
|---|---|---|---|
| `admin login --password-env FOUNDRY_ADMIN_PASSWORD` | `POST /auth` | `adminPassword=<secret>` | session cookie only |
| `admin logout` | `POST /setup` | `action=adminLogout` | current admin session only |
| `admin probe --type module` | `POST /setup` | `action=getPackages&type=module` | no |
| `admin probe --type system` | `POST /setup` | `action=getPackages&type=system` | no |
| `admin probe --type world` | `POST /setup` | `action=getPackages&type=world` | no |

Security/credential rules implemented:

- Admin password is accepted only from an env var named by `--password-env`; no plaintext password argument exists.
- Session cookies are stored in a profile-local cache path and chmodded `0600`.
- Errors report missing env var names or auth failure, never secret values.

## World configuration commands

Implemented read/write options helpers in `src/foundry_admin_cli/worlds.py`:

- `worlds run <id>` validates that `Data/worlds/<id>/world.json` exists, backs up `Config/options.json`, then sets `options.world = <id>`.
- `worlds stop` backs up `Config/options.json`, then sets `options.world = null` so Foundry starts in setup mode after restart.
- `worlds edit <id> --title ... --system ...` validates `Data/worlds/<id>/world.json`, backs it up, then updates supported manifest fields atomically.
- `worlds delete <id>` archives `Data/worlds/<id>` under `${HERMES_HOME:-~/.hermes}/backups/foundry-admin-cli/<version>/worlds/` by default; `--permanent` requires `--force`.
- Both run/stop commands report `restart_required: true` when they change `options.json`; they do not restart Foundry yet.
- Backups are written under `${HERMES_HOME:-~/.hermes}/backups/foundry-admin-cli/<version>/options.json/`.

Runtime validation on 2026-06-09:

- Unit tests: `uv run pytest -q` -> `58 passed`.
- `HOME=/home/jon uv run fvtt --version v13 status --json` reports active running world `module-test-dnd5e` and configured autoload world `module-test-black-flag`.
- `HOME=/home/jon uv run fvtt --version v13 admin probe --type module --json` currently returns `Foundry admin authentication failed or is unavailable` without a prior local admin login/session. This is expected for an unauthenticated probe and also confirms the command is not mutating Foundry state.
- Important limitation from `SetupView.handlePost`: when a world is active, most setup actions are blocked because the admin success path is `!game.world && authenticateAdmin.success`. Setup-level probes and package/world mutations require setup mode (no active world) or a separately researched active-world path.

## Next research steps

1. Inspect setup UI client code/templates to confirm exact POST payload shapes for:
   - `adminPassword`
   - `createWorld`
   - `editWorld`
   - `launchWorld`
   - `installPackage`
   - `uninstallPackage`
   - `manageModule`
2. Inspect world/module management client code to find the exact UI call that writes `core.moduleConfiguration`.
3. Inspect active world LevelDB setting storage for `core.moduleConfiguration` using a read-only dump from `/home/jon/foundryuserdata/Data/worlds/<world>/data/settings`.
4. For setup-level integration, temporarily stop/deactivate the active world through a safe restore flow, then run authenticated non-mutating `getPackages` probe with a local `FOUNDRY_ADMIN_PASSWORD` env var if available.

## Current conclusion

No Foundry core modification appears necessary from initial source inspection. Foundry v13 already exposes setup/admin HTTP POST actions for world/package/module management. The active-world module-management problem appears solvable by controlling the `core.moduleConfiguration` world setting through an authenticated world/session path or, as a fallback, source-verified direct settings storage update followed by reload/restart.
