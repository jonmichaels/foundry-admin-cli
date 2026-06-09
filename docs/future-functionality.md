# Foundry Admin CLI Future Functionality

This document tracks functionality that is important for reliable agent access to Foundry but is not part of `foundry-admin-cli` v0.3.0.

## Critical priorities

### 1. Configure game settings

**Why it matters:** The agent must configure Foundry MCP Bridge and related modules without browser clicking. Enabling a module is not enough; the bridge also needs in-world settings to connect and function reliably.

These are settings for the **running game/world**, not setup-level world lifecycle settings. They should live under the `game` namespace and require a logged-in game session, the same as `game module ...` and `game user ...`.

Expected generic command shape:

```bash
fvtt --version v13 game settings list --world <world-id> [--namespace <namespace>]
fvtt --version v13 game settings get --world <world-id> <namespace.key>
fvtt --version v13 game settings set --world <world-id> <namespace.key> --value-json '<json>'
fvtt --version v13 game settings set --world <world-id> <namespace.key> --value-env ENV
```

Do **not** prioritize `unset` initially. Foundry settings often have registered defaults and config metadata; deleting a stored setting is riskier than setting a known value. Add deletion later only after source/lifecycle behavior is verified.

Settings should be categorized because the setting space can be very large, especially in module-heavy worlds:

1. Foundry core settings.
2. Active game system settings.
3. Active module settings.

For JSON output, each setting should include enough metadata for agents and scripts to reason about it without browser context:

```json
{
  "namespace": "foundry-mcp-bridge",
  "key": "serverHost",
  "qualified_key": "foundry-mcp-bridge.serverHost",
  "category": "module",
  "scope": "world",
  "type": "String",
  "value": "foundry.example.com",
  "default": "",
  "config": true,
  "requires_reload": true
}
```

Secret or sensitive values must be redacted in output. Values supplied with `--value-env` must never be echoed in logs, human output, or JSON.

Critical first target:

- Foundry MCP Bridge settings needed for agent connectivity.

Initial implementation should be MCP Bridge-focused rather than trying to solve the entire Foundry settings universe generically. The generic list/get/set shape is still desirable, but the first acceptance target should be a practical bootstrap path for MCP Bridge.

Potential MCP Bridge-focused command:

```bash
fvtt --version v13 game settings apply-mcp-bridge --world <world-id> \
  --server-host-env FOUNDRY_MCP_BRIDGE_HOST
```

The command should apply the narrow set of settings required for agent access:

- Enable MCP Bridge.
- Set the websocket server host from an env/config value, e.g. `FOUNDRY_MCP_BRIDGE_HOST`; public docs and examples must use a placeholder such as `foundry.example.com`, not a real private host.
- Disable automatic map generation startup for now, because failed startup can flood Foundry logs for roughly two minutes and obscure module-development errors.

Equivalent generic setting operations may look like this once exact setting keys are source/live verified from the MCP Bridge module registration:

```bash
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.enabled --value-json true
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.serverHost --value-env FOUNDRY_MCP_BRIDGE_HOST
fvtt --version v13 game settings set --world <world-id> foundry-mcp-bridge.mapGenAutoStart --value-json false
```

MCP Bridge source review verified the critical keys as `foundry-mcp-bridge.enabled`, `foundry-mcp-bridge.serverHost`, and `foundry-mcp-bridge.mapGenAutoStart`. See `docs/research/foundry-v13-game-settings.md` for the full settings map and runtime polling design.

Implementation notes:

- Use the authenticated running-game session/socket path, not setup/world lifecycle commands and not MCP Bridge itself.
- Research v13 `Setting` document schema and module setting registration behavior.
- Read registered setting metadata from the running game when possible so list/get can report category, scope, type, default, config visibility, and reload requirements.
- Validate setting namespace/key names before mutation.
- Preserve type fidelity: booleans, numbers, strings, arrays, and objects.
- Support secret values through `--value-env`; never print secret values in logs or JSON output.
- Report whether a world reload is required after a setting change.
- Include dry-run or diff output for setting updates.
- Keep `--world` as a safety guard until active-world inference is reliable.

MCP Bridge bootstrap acceptance:

1. Verify the target world is running and matches `--world`.
2. Verify a valid GM game session exists.
3. Verify Foundry MCP Bridge is installed and active in the world, or produce the exact `game module enable` command needed.
4. Apply the required MCP Bridge settings.
5. Ensure map generation auto-start is disabled unless explicitly requested.
6. Report whether reload/return-to-setup/relaunch is required.
7. After reload, verify bridge connectivity or produce exact next steps.

### 2. Agent bootstrap command

**Why it matters:** The agent needs a single repeatable bootstrap flow that can take a fresh Foundry host/world to “agent-accessible” state.

Possible command:

```bash
fvtt --version v13 bootstrap-agent --world <world-id> \
  --gm-user <name> \
  --gm-password-env ENV \
  --enable-module foundry-mcp-bridge \
  --settings-file bridge-settings.json
```

Should orchestrate:

1. verify Foundry process health
2. verify/create a GM-capable user
3. login to the world
4. verify/install/enable Foundry MCP Bridge
5. apply required bridge settings
6. restart/reload as needed
7. verify MCP Bridge connectivity or produce exact next steps

### 3. Permission and ownership management

**Why it matters:** Creating users is insufficient if players/agents cannot access assigned actors, journals, scenes, or compendia.

Needed capabilities:

- assign actor ownership to users
- grant observer/owner permissions for journals or scenes
- audit user permissions for a world
- export permission state for repeatable setup

This may remain MCP-side if Foundry MCP Bridge is already available, but the CLI should document the boundary clearly.

### 4. Backup, restore, and rollback commands

**Why it matters:** Mutating world users/settings/modules is risky. The CLI already creates targeted backups for some writes, but operators need first-class restore paths.

Needed commands:

```bash
fvtt --version v13 backups list
fvtt --version v13 backups show <backup-id>
fvtt --version v13 backups restore <backup-id> --force
```

Must include:

- world manifest/options/settings backups
- package archive locations
- restore dry-run
- explicit safety prompts/flags for destructive restores

## High-value follow-ups

### Command output consistency

Human output paths should use concise tables/lists; `--json` should remain machine-readable. Keep the command namespace singular going forward:

- `world` for setup/world lifecycle commands.
- `system` for installed system package commands.
- `module` for installed module package commands.
- `game` for active running-game/session commands, including `game login` and `game module ...`.

Avoid adding plural aliases unless there is a strong compatibility reason; this CLI is still internal/pre-1.0.

### Package registry lookup

Current package install expects manifest URLs. Future work should support Foundry package IDs by resolving official registry metadata safely.

### v14 adapter

v14 configuration shape exists, but behavior is not validated. Add v14 only after source review and a separate integration matrix.

### SSH execution wrapper

Not needed for v0.3.0, but a future wrapper could run `fvtt` over SSH on a remote Foundry host. It should be separate from the core CLI so local-on-host behavior stays simple and testable.

## Acceptance criteria for future agent-access milestone

The CLI should be considered agent-bootstrap complete when it can, from a clean Foundry v13 host/world:

1. create or configure a GM-capable agent account
2. set required world/module settings for Foundry MCP Bridge
3. enable Foundry MCP Bridge without relying on MCP itself
4. restart/reload the world when required
5. verify agent connectivity through the bridge
6. leave a documented rollback path for every mutation
