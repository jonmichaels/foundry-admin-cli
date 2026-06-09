# Foundry v13 Setup/Admin Protocol Research

Date: 2026-06-09

## Scope

Initial source inspection for implementing `foundry-admin-cli` without modifying Foundry core and without relying on Foundry MCP Bridge for bootstrap operations.

Target install inspected through the configured v13 `install_dir`.

## Source files inspected

- `<install_dir>/dist/server/views/setup.mjs`
- `<install_dir>/dist/server/views/auth.mjs`
- `<install_dir>/dist/server/views/join.mjs`
- `<install_dir>/dist/server/sockets.mjs`
- `<install_dir>/dist/server/express.mjs`
- `<install_dir>/dist/packages/views.mjs`
- `<install_dir>/dist/packages/installer.mjs`
- `<install_dir>/dist/packages/world.mjs`
- `<install_dir>/dist/database/documents/setting.mjs`

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

- Source: `<install_dir>/dist/server/views/auth.mjs`
- `AuthView.route = "/auth"`
- `AuthView._methods = ["get", "post"]`
- `handlePost()` calls `sessions.authenticateAdmin(req, res)`.
- On success when no world is active, it redirects to `/setup`.

`SetupView.handleGet()` checks `sessions.authenticateAdmin(req, res).success` and redirects unauthenticated users to `/auth`.

Implication: CLI should maintain cookies/session and authenticate via `/auth` before setup-level POST operations.

## World login

`JoinView` handles world login:

- Source: `<install_dir>/dist/server/views/join.mjs`
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

Source: `<install_dir>/client/applications/sidebar/apps/module-management.mjs`.

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

Read-only LevelDB inspection of `<data_dir>/Data/worlds/module-test-dnd5e/data/settings` found the record key shape:

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

- `world run <id>` validates that `Data/worlds/<id>/world.json` exists, backs up `Config/options.json`, then sets `options.world = <id>`.
- `world create <id> --title ... --system ...` mirrors Foundry `World.create` filesystem shape by creating `world.json`, `data/`, and `scenes/` after validating the target system exists.
- `world stop` backs up `Config/options.json`, then sets `options.world = null` so Foundry starts in setup mode after restart.
- `world edit <id> --title ... --system ...` validates `Data/worlds/<id>/world.json`, backs it up, then updates supported manifest fields atomically.
- `world delete <id>` archives `Data/worlds/<id>` under the configured backup/archive root by default; `--permanent` requires `--force`.
- Both run/stop commands report `restart_required: true` when they change `options.json`; they do not restart Foundry yet.
- Top-level process helpers now include `restart`, `logs`, and `wait`: restart calls PM2 with configured `FOUNDRY_ADMIN_RUN_HOME`/current `HOME` and waits for unauthenticated HTTP readiness; logs tails today's `debug.YYYY-MM-DD.log` and `error.YYYY-MM-DD.log` with optional filtering.
- Admin session helpers now include `admin status` and `admin whoami`, both using the read-only setup probe to report persisted session usability without throwing on unauthenticated state.
- Admin password lookup accepts the named environment variable first and a local data-dir `.env` fallback; secrets are never accepted as plaintext CLI arguments.
- System package commands now include:
  - `system list`: reads `Data/systems/*/system.json`, reports id/title/version/compatibility/manifest/path/validity and world dependencies.
  - `system install <manifest-url>` validates manifest URLs as `http`/`https`, then calls verified setup `installPackage` action with `type=system` and manifest URL. ID-only install remains intentionally unsupported until registry lookup is researched.
  - `system update <id>`: reads installed `system.json`, fetches its recorded manifest URL, compares version/compatibility, and calls setup `installPackage` with `force=true` only when remote metadata differs.
  - `system remove <id>`: archives by default under `${HERMES_HOME:-~/.hermes}/backups/foundry-admin-cli/<version>/systems/`, refuses world dependencies unless `--force`, and requires `--force` for `--permanent`.
- System remove rejects symlinked package directories and validates ids before filesystem mutation.
- Module package commands now include:
  - `module list`: reads `Data/modules/*/module.json`, reports id/title/version/compatibility/manifest/path/validity and symlink status. Enabled-world discovery is reported as an empty list until Task 10 implements source-verified world module-state reads.
  - `module install <manifest-url>`: validates `http`/`https` manifest URLs and calls verified setup `installPackage` with `type=module`.
  - `module update <id>`: reads installed `module.json`, fetches its recorded manifest URL, compares version/compatibility, and calls setup `installPackage` with `force=true` only when remote metadata differs.
  - `module create <id> --title ... [--projects-dir PATH] [--symlink]`: scaffolds `<projects_dir>/<id>` with `module.json`, `scripts/`, `templates/`, `styles/`, `languages/en.json`, and concise `CLAUDE.md`; symlink into `Data/modules` only when requested.
  - `module edit <id>`: updates allowlisted manifest fields (`title`, `manifest`) with validation, backup, and atomic write.
  - `module remove <id>`: archives regular directories by default; symlinked modules are unlinked only and source directories are never deleted.
- World session commands now include:
  - `game login <world-id> --user <gm-user> --password-env <ENV>`: posts the source-verified v13 `/join` flow (`action=join`, `userid`, `password`) and persists session cookies under the active Hermes profile cache with owner-only permissions.
  - `game ping`: verifies the persisted world session can reach `/game` without redirecting back to `/join`.
- Active-world module commands now include:
  - `game module list --world <id>`: uses authenticated v13 world socket `world` payload to read available modules and the `core.moduleConfiguration` setting.
  - `game module enable <module-id> --world <id>` / `disable`: uses the authenticated world socket `modifyDocument` request for the `Setting` document. MCP is not used.
  - `game module set --world <id> --modules a,b,c`: replaces the active module set, preserving installed module ids as explicit booleans.
- v13 UI source requires a world reload after module configuration changes (`SettingsConfig.reloadConfirm({world: true})` before `game.settings.set`). CLI reports `reload_required: true` for changed module sets; no-op changes report false.
- GM credentials are read only from environment or the Foundry data-dir `.env`; no plaintext password CLI argument is accepted.
- Backups are written under the configured backup root, falling back to an XDG-compatible user state/cache location when not configured.

Runtime validation on 2026-06-09:

- Unit tests: `uv run pytest -q` -> `147 passed`.
- `uv run fvtt --version v13 system list --json` lists installed v13 systems (`a5e`, `black-flag`, `dnd5e`) and dependent worlds.
- `uv run fvtt --version v13 module list --json` lists installed v13 modules; current live v13 data reports 67 modules.
- `uv run fvtt --version v13 game ping --json` works without credentials and currently reports authenticated when a persisted GM cookie exists.
- `uv run fvtt --version v13 game module list --world module-test-black-flag --json` works through the authenticated world socket and reports 55 available modules in the active Black Flag test world.
- `uv run fvtt --version v13 status --json` reports active/configured running world `module-test-black-flag` after final validation restored it.
- `uv run fvtt --version v13 wait --timeout 5 --interval 0.5 --json` returns `ready: true` in 1 attempt.
- `uv run fvtt --version v13 logs --lines 2 --json` reads today's debug/error logs from the configured `Data/Logs/` directory.
- `uv run fvtt --version v13 admin status --json` reports unauthenticated setup access without exposing secrets when no valid admin cookie is present.
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
3. Inspect active world LevelDB setting storage for `core.moduleConfiguration` using a read-only dump from `<data_dir>/Data/worlds/<world>/data/settings`.
4. For setup-level integration, temporarily stop/deactivate the active world through a safe restore flow, then run authenticated non-mutating `getPackages` probe with a local `FOUNDRY_ADMIN_PASSWORD` env var if available.

## Current conclusion

No Foundry core modification appears necessary from initial source inspection. Foundry v13 already exposes setup/admin HTTP POST actions for world/package/module management. The active-world module-management problem appears solvable by controlling the `core.moduleConfiguration` world setting through an authenticated world/session path or, as a fallback, source-verified direct settings storage update followed by reload/restart.
