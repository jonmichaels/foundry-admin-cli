# Foundry Admin CLI Future Functionality

This document tracks functionality that remains important for reliable agent access to Foundry after `foundry-admin-cli` v0.3.0.

## Implemented bootstrap baseline

`fvtt bootstrap-agent` now provides the first agent-bootstrap baseline for Foundry v13:

```bash
fvtt --version v13 bootstrap-agent --world <world-id> \
  --gm-user <name-or-id> \
  --gm-password-env ENV \
  --admin-password-env ENV \
  --license-env ENV \
  --mcp-server-host-env ENV
```

It can also use `--allow-empty-password` for a fresh default v13 `Gamemaster` user. The command verifies process readiness, handles fresh-install license/EULA activation when `/license` is required, authenticates setup, installs Foundry MCP Bridge from the GitHub release manifest, launches the target world, logs in as a GM-capable user, waits through transient world-socket readiness after first launch, enables MCP Bridge, applies the bridge settings, reloads/re-authenticates when required, and verifies the resulting active bridge state.

Remaining future items below extend the bootstrap baseline rather than replacing it.

## Critical priorities

### 1. Permission and ownership management

**Why it matters:** Creating users is insufficient if players/agents cannot access assigned actors, journals, scenes, or compendia.

Needed capabilities:

- assign actor ownership to users
- grant observer/owner permissions for journals or scenes
- audit user permissions for a world
- export permission state for repeatable setup

This may remain MCP-side if Foundry MCP Bridge is already available, but the CLI should document the boundary clearly.

### 2. Backup, restore, and rollback polish

**Status:** First-class backup/restore commands are implemented. See `README.md` and `docs/research/foundry-v13-backup-restore.md`.

Implemented commands:

```bash
fvtt --version v13 backup list
fvtt --version v13 backup create --type world --package-id my-world --note "before migration"
fvtt --version v13 backup snapshot --note "before v13 update"
fvtt --version v13 backup restore <backup-id> --force
fvtt --version v13 backup restore-snapshot <snapshot-id> --force
fvtt --version v13 backup delete <backup-id> --force
fvtt --version v13 backup delete-snapshot <snapshot-id> --force
fvtt --version v13 backup data-create --include-config
fvtt --version v13 backup data-restore <archive> --force
```

Remaining polish:

- setup progress socket integration for exact async completion instead of postcondition-based verification
- disk-space preflight commands for large snapshots/restores
- restore dry-run/preview output
- inventory command for CLI targeted rollback artifacts under `FOUNDRY_ADMIN_BACKUP_DIR`

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

The CLI should be considered ready for broader agent-access workflows when it can, from a clean Foundry v13 host/world:

1. create or configure a GM-capable agent account
2. set required world/module settings for Foundry MCP Bridge
3. enable Foundry MCP Bridge without relying on MCP itself
4. restart/reload the world when required
5. verify agent connectivity through the bridge
6. leave a documented rollback path for every mutation
7. assign the agent the required world document ownership/permissions
