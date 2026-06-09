# Foundry Admin CLI Future Functionality

This document tracks functionality that is important for reliable agent access to Foundry but is not part of `foundry-admin-cli` v0.3.0.

## Critical priorities

### 1. Configure settings

**Why it matters:** The agent must configure Foundry MCP Bridge and related modules without browser clicking. Enabling the module is not enough; the bridge needs settings to connect and function reliably.

Needed commands:

```bash
fvtt --version v13 world settings list --world <world-id> [--namespace <namespace>]
fvtt --version v13 world settings get --world <world-id> <namespace.key>
fvtt --version v13 world settings set --world <world-id> <namespace.key> --value-json '<json>'
fvtt --version v13 world settings set --world <world-id> <namespace.key> --value-env ENV
fvtt --version v13 world settings unset --world <world-id> <namespace.key> --force
```

Critical first target:

- Foundry MCP Bridge settings needed for agent connectivity.

Implementation notes:

- Research v13 `Setting` document schema and module setting registration behavior.
- Validate setting namespace/key names before mutation.
- Preserve type fidelity: booleans, numbers, strings, arrays, and objects.
- Support secret values through `--value-env`; never print secret values in logs or JSON output.
- Report whether a world reload is required after a setting change.
- Include dry-run or diff output for setting updates.

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
