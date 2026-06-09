# Foundry v13 Game Settings Research

Date: 2026-06-09

Scope: research for future `fvtt --version v13 game settings ...` commands. This is source-based research against the local Foundry v13 install, Black Flag system, and installed modules. It intentionally does not rely on MCP Bridge because configuring MCP Bridge is a bootstrap use case.

## Conclusions

Settings belong under `game settings`, not `world settings`.

- Foundry settings are registered after a world/game is running through `game.settings.register(namespace, key, data)`.
- World/user-scoped settings are persisted as `Setting` documents in the world database; client-scoped settings live in browser local storage and should normally be read-only from this CLI.
- The authoritative registry is the running game object: `game.settings.settings`, a `Map<string, SettingConfig>` keyed as `<namespace>.<key>`.
- Ad-hoc discovery should query that runtime registry whenever possible instead of statically parsing source files. Static source parsing is useful for planning and fallback documentation, but it misses dynamic settings, computed keys, menus, and module-specific branches.

## Foundry v13 settings mechanics

Source: `/home/jon/foundry/client/helpers/client-settings.mjs`

`ClientSettings` stores:

- `game.settings.settings`: registered setting metadata map.
- `game.settings.menus`: registered settings-menu metadata map.
- `game.settings.storage`: `client`, `world`, and `user` storage backends.

Important source behavior:

- `register(namespace, key, data)` creates `data.id = `${namespace}.${key}`` and stores it in `game.settings.settings`.
- `scope` defaults to `client` if not one of Foundry's known setting scopes.
- `client` scope reads/writes `window.localStorage`.
- `world` scope reads/writes world `Setting` documents.
- `user` scope also uses world `Setting` documents, keyed by current user id.
- `get(namespace, key, {document})` returns either value or a `Setting` document.
- `set(namespace, key, value, options)` validates against the registered setting config and writes via either local storage or `Setting.implementation.create/update`.
- World/user values are JSON-stringified through the registered setting type before persistence.

CLI implications:

- Initial mutation support should target `scope: "world"` only.
- `scope: "user"` needs an explicit target user design before mutation.
- `scope: "client"` is browser-local and should be reported as client-only / not remotely mutable by the CLI.
- Registered metadata should be returned with each row: namespace, key, id, category, scope, type, default, current value, config, choices, range, requiresReload.
- `game.settings.set(...)` should be preferred over raw `modifyDocument` when possible because it runs Foundry type cleaning and validation.
- If using the socket protocol directly, the CLI must either invoke a world-side script/helper or faithfully mirror Foundry's setting validation; raw `Setting` document writes are riskier.

## Runtime polling design

Best discovery path for `game settings list`:

```js
Array.from(game.settings.settings.entries()).map(([id, setting]) => ({
  id,
  namespace: setting.namespace,
  key: setting.key,
  scope: setting.scope,
  name: game.i18n.localize(setting.name ?? setting.label ?? id),
  hint: setting.hint ? game.i18n.localize(setting.hint) : "",
  config: setting.config ?? false,
  requires_reload: setting.requiresReload ?? false,
  default: setting.default,
  type: describeSettingType(setting.type),
  choices: typeof setting.choices === "function" ? setting.choices() : setting.choices,
  range: setting.range ?? extractRangeFromDataField(setting.type),
  value: safeGet(setting.namespace, setting.key),
  category: categorize(namespace)
}))
```

Category rules:

- `namespace === "core"` -> `core`.
- `namespace === game.system.id` -> `system`.
- `game.modules.has(namespace)` -> `module`.
- otherwise `unknown`.

Filtering:

- `--namespace foundry-mcp-bridge` should filter by namespace.
- `--category core|system|module|unknown` is useful once implemented.
- `--config-only` should show only settings visible in Foundry's Configure Settings UI.
- `--world-only` should show only settings that the CLI can safely mutate.

Mutation design:

- Resolve `<namespace.key>` against `game.settings.settings`; fail if unregistered unless an explicit unsafe/raw flag is ever added.
- Reject client settings for mutation.
- Reject user settings until user-target semantics are designed.
- Parse `--value-json` as JSON, not strings.
- `--value-env` reads the whole env value; if JSON parsing is needed, add `--value-env-json` or document string-only env usage.
- Call `game.settings.set(namespace, key, value)` in the running game context when possible.
- Report `changed`, `old_value`, `new_value`, `requires_reload`, and redact values sourced from env.

## MCP Bridge settings map

Source: `/home/jon/foundryuserdata/Data/modules/foundry-mcp-bridge/dist/settings.js`

Module id / namespace: `foundry-mcp-bridge`.

Registered menus:

| Menu key | Label | Notes |
|---|---|---|
| `enhancedIndexMenu` | Configure Enhanced Index | Submenu writes `enableEnhancedCreatureIndex`, `autoRebuildIndex`. |
| `mapGenerationSettings` | Configure Map Generation | Submenu writes `mapGenAutoStart`, `mapGenQuality`; includes service controls. |

Registered settings:

| Qualified key | Scope | Config | Type | Default | Notes |
|---|---:|---:|---|---|---|
| `foundry-mcp-bridge.enabled` | world | true | Boolean | `true` | **Critical.** Label: Enable MCP Bridge. On change starts/stops bridge. |
| `foundry-mcp-bridge.connectionType` | world | true | String | `auto` | Choices: `auto`, `webrtc`, `websocket`. On change restarts bridge if enabled. |
| `foundry-mcp-bridge.serverHost` | world | true | String | `DEFAULT_CONFIG.MCP_HOST` | **Critical.** Label: Websocket Server Host. Set from env/config for bootstrap. |
| `foundry-mcp-bridge.serverPort` | world | false | Number | `DEFAULT_CONFIG.MCP_PORT` | Hidden. Validation expects 1024-65535. |
| `foundry-mcp-bridge.allowWriteOperations` | world | true | Boolean | `true` | Allows create/modify operations. |
| `foundry-mcp-bridge.maxActorsPerRequest` | world | true | Number | `10` | UI range 1-50, but module `validateSettings()` currently enforces 1-10. Treat 10 as safe. |
| `foundry-mcp-bridge.enableEnhancedCreatureIndex` | world | false | Boolean | `true` | Submenu-only. |
| `foundry-mcp-bridge.autoRebuildIndex` | world | false | Boolean | `true` | Submenu-only. |
| `foundry-mcp-bridge.mapGenAutoStart` | world | false | Boolean | `true` | **Critical for Jon's workflow: set false initially** to avoid failed map-generation startup flooding logs. |
| `foundry-mcp-bridge.mapGenQuality` | world | false | String | `low` | Choices: `low`, `medium`, `high`. |
| `foundry-mcp-bridge.enableNotifications` | world | true | Boolean | `true` | Connection notifications. |
| `foundry-mcp-bridge.autoReconnectEnabled` | world | true | Boolean | `true` | Auto reconnect. |
| `foundry-mcp-bridge.heartbeatInterval` | world | true | Number | `30` | Range 10-120, step 5. |
| `foundry-mcp-bridge.lastConnectionState` | world | false | String | `disconnected` | Internal state; do not set in bootstrap. |
| `foundry-mcp-bridge.lastActivity` | world | false | String | empty | Internal state; do not set in bootstrap. |
| `foundry-mcp-bridge.lastMCPServerNotification` | world | false | String | empty | Internal anti-spam state; do not set in bootstrap. |
| `foundry-mcp-bridge.rollStates` | world | false | Object | `{}` | Internal roll button state. |
| `foundry-mcp-bridge.buttonMessageMap` | world | false | Object | `{}` | Internal chat message mapping. |

Critical MCP Bridge bootstrap settings:

```bash
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.enabled --value-json true
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.serverHost --value-env FOUNDRY_MCP_BRIDGE_HOST
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.mapGenAutoStart --value-json false
```

Optional safe settings:

```bash
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.connectionType --value-json '"auto"'
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.allowWriteOperations --value-json true
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.maxActorsPerRequest --value-json 10
```

Notes:

- `serverHost` should be a hostname or IP for the Foundry/MCP server. Public docs must use placeholders such as `foundry.example.com`.
- `serverPort` is hidden and defaults from module constants. Do not change for initial bootstrap unless a real need appears.
- `mapGenAutoStart` is hidden behind the map-generation submenu; generic `config: true` filtering would miss it. MCP Bridge bootstrap must target it explicitly.

## Foundry Core settings structure

Primary source: `/home/jon/foundry/client/game.mjs` `registerSettings()` plus helper classes invoked from it.

Observed from source:

- `game.mjs` directly registers roughly 41 core settings and 6 core menus.
- Additional core settings are registered by helper classes invoked from `registerSettings()` such as AV, combat, prototype token overrides, token ring config, dice config, default sheets, and package warnings.
- Core uses all three scopes: `world`, `client`, and hidden/internal settings.
- Core settings include a mix of primitive constructors (`Object`) and v13 DataField instances (`BooleanField`, `StringField`, `NumberField`, `TypedObjectField`, `SchemaField`).

Representative world-scoped core settings:

| Key | Scope | Config | Notes |
|---|---:|---:|---|
| `core.permissions` | world | false | User role permissions map; should not be treated as actor ownership. |
| `core.fontConfig` | world | false | Stored object for font configuration menu. |
| `core.compendiumArt` | world | false | Compendium art configuration. |
| `core.time` | world | false | World time number. |
| `core.moduleConfiguration` | world | false | Module active-state map; already handled by `game module ...`; requires reload. |
| `core.compendiumConfiguration` | world | false | Compendium visibility/configuration. |
| `core.scrollingStatusText` | world | true | Boolean display setting. |
| `core.tokenAutoRotate` | world | true | Boolean token setting. |
| `core.tokenDragPreview` | world | true | Boolean token setting. |
| `core.editorAutosaveSecs` | world | true | Number 30-300, step 10. |
| `core.pmHighlightDocumentMatches` | world | false | ProseMirror link highlighting. |

Representative client-scoped settings:

- `core.noCanvas`
- `core.language`
- `core.chatBubbles`
- `core.chatBubblesPan`
- `core.performanceMode`
- `core.maxFPS`
- `core.uiConfig`
- `core.photosensitiveMode`
- `core.keybindings`

CLI implications:

- `game settings list --namespace core` should include both world and client settings, but mutation should default to world scope only.
- `core.moduleConfiguration` is special: keep using `game module ...` for active module changes instead of exposing it as a casual generic setting mutation.
- Core menu-backed object settings should be listed, but mutation should require explicit JSON and ideally a dry-run diff because schema objects can be large.

## Black Flag settings structure

Source: `/home/jon/foundryuserdata/Data/systems/black-flag/black-flag.mjs` around `registerSettings()`.

Namespace: `black-flag` via `game.system.id`.

Observed from source:

- 19 registered system settings.
- 3 registered settings menus: combat, localization, optional rules.
- Most settings are `scope: "world"`; one visible client setting exists (`collapseChatTrays`).
- Some important settings are hidden from the main settings UI and exposed only through custom menus.
- Black Flag uses custom DataModel/DataField-like setting types for structured settings:
  - `LocalizationSetting`
  - `RulesSetting`

Representative settings:

| Qualified key | Scope | Config | Type | Default / choices | Notes |
|---|---:|---:|---|---|---|
| `black-flag.initiativeTiebreaker` | world | false | Boolean | false | Combat submenu. |
| `black-flag.criticalMaximizeDamage` | world | false | Boolean | false | Combat submenu. |
| `black-flag.criticalMultiplyDice` | world | false | Boolean | false | Combat submenu. |
| `black-flag.criticalMultiplyNumeric` | world | false | Boolean | false | Combat submenu. |
| `black-flag.localization` | world | false | `LocalizationSetting` | model default | Requires reload. |
| `black-flag.rulesConfiguration` | world | false | `RulesSetting` | `{firearms: false}` | Requires reload. |
| `black-flag.criticalChecksAndThrows` | world | false | Boolean | false | Optional rule. |
| `black-flag.attackVisibility` | world | true | String | `hideAC`; choices `all`, `hideAC`, `none` | Visible config setting. |
| `black-flag.challengeVisibility` | world | true | String | `player`; choices `all`, `player`, `none` | Visible config setting. |
| `black-flag.collapseChatTrays` | client | true | String | `older`; choices `never`, `older`, `always` | Client-only. |
| `black-flag.encumbrance` | world | true | String | `none`; choices `none`, `normal`, `variant` | Visible config setting. |
| `black-flag.levelingMode` | world | true | String | `xp`; choices `xp`, `milestone` | Visible config setting. |
| `black-flag.proficiencyMode` | world | false | String | `bonus`; choices `bonus`, `dice` | Hidden. |
| `black-flag.abilitySelectionManual` | world | true | Boolean | false | Visible. |
| `black-flag.abilitySelectionReroll` | world | true | Boolean | false | Visible. |
| `black-flag.allowMulticlassing` | world | true | Boolean | true | Visible. |
| `black-flag.allowSummoning` | world | true | Boolean | true | Visible. |
| `black-flag.tokenMeasurementAutomation` | world | true | Boolean | true | Visible. |
| `black-flag._firstRun` | world | false | Boolean | true | Hidden/internal. |

CLI implications:

- `config: false` does not mean unimportant. Many system settings are submenu-backed and should still be discoverable.
- `requiresReload` matters for `black-flag.localization` and `black-flag.rulesConfiguration`.
- DataModel-backed settings should be mutation-conservative: list/get first, set only through `game.settings.set` so system validation runs.

## Other module settings explored

### Simple Fog

Source: `/home/jon/foundryuserdata/Data/modules/simplefog/module/simplefog.js`

Observed:

- 7 settings and 1 menu.
- Has one large object-style configuration setting plus simple user-tunable settings.
- Mix of visible and hidden config settings.

Representative keys:

| Qualified key | Notes |
|---|---|
| `simplefog.config` | Main configuration object/menu-backed setting. |
| `simplefog.brushSize` | Numeric brush setting. |
| `simplefog.brushOpacity` | Numeric opacity setting. |
| `simplefog.confirmFogDisable` | Boolean safety prompt setting. |
| `simplefog.autoEnableSceneFog` | Boolean automation setting. |
| `simplefog.toolHotKeys` | Hotkey/config object. |
| `simplefog.zIndex` | Numeric layer ordering setting. |

Takeaway: modules may store a primary object config plus several convenience settings. Listing must not assume all meaningful settings are visible `config: true` rows.

### Monk's Little Details

Source: `/home/jon/foundryuserdata/Data/modules/monks-little-details/settings.js`

Observed:

- 29 settings and 2 menus from a dedicated settings file.
- Uses hyphenated keys heavily.
- Mostly boolean/string UI behavior toggles.
- Good example for ad-hoc search by label/key because keys are human-readable but numerous.

Representative keys:

- `monks-little-details.alter-hud`
- `monks-little-details.clear-all`
- `monks-little-details.sort-by-columns`
- `monks-little-details.sort-statuses`
- `monks-little-details.alter-hud-colour`
- `monks-little-details.add-extra-statuses`
- `monks-little-details.core-css-changes`
- `monks-little-details.window-css-changes`
- `monks-little-details.chat-css-changes`
- `monks-little-details.scene-palette`
- `monks-little-details.find-my-token`
- `monks-little-details.module-management-changes`

Takeaway: ad-hoc setting search needs substring matching across namespace, key, localized name, and hint, not only exact key matching.

### Item Piles

Source: `/home/jon/foundryuserdata/Data/modules/item-piles/dist/item-piles.js`

Observed:

- Registers a settings menu plus a dynamic settings object returned by `SETTINGS.GET_DEFAULT()`.
- Source parsing found only the loop call site, not every concrete registration from the first pass.
- Defaults are large and partly system-specific; settings are grouped by comments/categories inside module constants.
- Supports import/export of settings as JSON.
- Has system-specific defaults/migrations and writes settings when a supported system is detected.

Representative setting groups from source constants:

- Client settings: output/chat/debug/preload behavior.
- Module settings: dropping/trading/giving items, delete empty piles, inspect trade items, price presets.
- Style settings: CSS variables, vault styles.
- System settings: currencies, item filters, item/actor class types, quantity/price attributes, pile defaults, token flag defaults.
- Hidden settings: default actor id, system-found flags, system version, custom item categories.

Takeaway: runtime registry polling is mandatory. Static grep can miss dynamically generated keys and system-specific defaults.

## Search / ad-hoc discovery requirements

For agents to quickly find settings in large module stacks, `game settings list` should support:

```bash
fvtt --version v13 game settings list --world <world-id> --namespace foundry-mcp-bridge
fvtt --version v13 game settings list --world <world-id> --category module
fvtt --version v13 game settings list --world <world-id> --query websocket
fvtt --version v13 game settings list --world <world-id> --query "map generation"
fvtt --version v13 game settings list --world <world-id> --config-only
fvtt --version v13 game settings list --world <world-id> --world-only
```

Search should match:

- qualified key (`namespace.key`)
- namespace
- key
- localized display name
- localized hint
- choices labels and values
- menu labels/hints where applicable

Output should include enough metadata to drive follow-up commands:

```json
{
  "world": "<world-id>",
  "active_world": "<world-id>",
  "settings": [
    {
      "qualified_key": "foundry-mcp-bridge.serverHost",
      "namespace": "foundry-mcp-bridge",
      "key": "serverHost",
      "category": "module",
      "scope": "world",
      "config": true,
      "name": "Websocket Server Host",
      "hint": "IP address for local Websocket Server connections to the MCP Server...",
      "type": "String",
      "default": "localhost",
      "value": "foundry.example.com",
      "choices": null,
      "range": null,
      "requires_reload": false,
      "mutable_by_cli": true,
      "source": "registered"
    }
  ]
}
```

## Implemented v0.3 behavior

Implemented commands:

```bash
fvtt --version v13 game settings list --world <world-id> [--namespace <namespace>] [--category core|system|module|unknown] [--query <text>] [--config-only] [--world-only]
fvtt --version v13 game settings get --world <world-id> <namespace.key>
fvtt --version v13 game settings set --world <world-id> <namespace.key> --value-json '<json>'
fvtt --version v13 game settings set --world <world-id> <namespace.key> --value-env ENV
fvtt --version v13 game settings apply-mcp-bridge --world <world-id> --server-host-env ENV
```

Current implementation notes:

- Uses the authenticated v13 world socket and `modifyDocument` for `Setting` documents, matching the existing active-module control transport.
- Lists persisted world settings from the socket `world` payload and augments them with a curated metadata map for known bootstrap-critical settings, especially MCP Bridge.
- Mutates only world-scoped settings; client-scoped known settings such as `core.maxFPS` are rejected.
- Rejects unknown setting keys unless they already exist as persisted world Setting documents.
- `--value-json` preserves JSON type fidelity for booleans, numbers, strings, arrays, and objects.
- `--value-env` treats the env value as a string and redacts old/new values in command output.
- Known sensitive values such as `foundry-mcp-bridge.serverHost` are redacted in settings output to avoid leaking private hostnames.
- `apply-mcp-bridge` explicitly sets `foundry-mcp-bridge.enabled=true`, `foundry-mcp-bridge.serverHost=<env value>`, and `foundry-mcp-bridge.mapGenAutoStart=false`.

Remaining improvement: a future world-side helper that calls `game.settings.set(namespace, key, value)` directly would preserve arbitrary module/system validation and `onChange` callbacks for unknown settings. Until that exists, generic mutation is intentionally conservative and best suited to known world settings or already-persisted settings.
