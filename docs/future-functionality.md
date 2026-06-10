# Foundry Admin CLI Potential Updates

This file tracks only functionality not already present in `fvtt` v0.4. The current CLI already covers v13/v14 process control, setup/admin sessions, world/system/module lifecycle, official package library access, active-game login/modules/users/settings/permissions, backup/restore, and agent bootstrap.

## Backup and rollback polish

- Add setup progress socket integration for backup, restore, snapshot, install, and update operations so async setup actions can report exact completion instead of relying only on postcondition checks.
- Add disk-space preflight output before large snapshots, restores, package installs, and full User Data archive operations.
- Add restore dry-run/preview commands that show the package/archive contents, target paths, estimated size, and required downtime before requiring `--force`.
- Add an inventory command for CLI-owned rollback artifacts under `FOUNDRY_ADMIN_BACKUP_DIR`, separate from Foundry-native package backups and full User Data archives.

## Permission coverage

- Design compendium permission management only if repeatable agent setup needs it. Actor, journal, and scene ownership are already implemented through `game permission audit/set/export`.

## Remote orchestration

- Keep the core CLI host-local. If remote execution becomes useful, add a thin SSH wrapper that runs `fvtt` on the Foundry host instead of adding remote filesystem/process behavior to the core command layer.

## Output consistency

- Continue tightening human-readable output into concise tables/lists while keeping `--json` stable and machine-readable.
- Keep command namespaces singular (`world`, `system`, `module`, `game`) unless a compatibility reason justifies an alias.
