# Foundry v13 Backup/Restore Research

Date: 2026-06-09

## Question

Can the Foundry Admin CLI rely on Foundry's built-in setup backup/restore functionality, or do we need a separate backup process?

## Sources

- Official docs: <https://foundryvtt.com/article/backups>
- Official manual backup docs: <https://foundryvtt.com/article/user-data-backup/>
- Release notes introducing built-in backups: <https://foundryvtt.com/releases/11.311>
- Local Foundry v13.351 source:
  - `/home/jon/foundry/dist/server/views/setup.mjs`
  - `/home/jon/foundry/dist/packages/views.mjs`
  - `/home/jon/foundry/dist/packages/package-backups.mjs`
  - `/home/jon/foundry/common/constants.mjs`

## Built-in Foundry behavior

Foundry supports setup-level backup actions introduced in v11.311 and still present in v13:

- Package backups for individual `world`, `system`, and `module` packages.
- Snapshots that back up every installed world, system, and module package at once.
- Listing, restoring, and deleting package backups and snapshots through setup actions.

The setup POST action switch in v13 includes:

- `createBackup`
- `createSnapshot`
- `deleteBackup`
- `deleteSnapshot`
- `restoreBackup`
- `restoreSnapshot`
- `listBackups`
- `checkCreateSnapshotDiskSpace`
- `checkRestoreSnapshotDiskSpace`

The progress protocol constants are in `CONST.SETUP_PACKAGE_PROGRESS.ACTIONS`:

- `CREATE_BACKUP = "createBackup"`
- `RESTORE_BACKUP = "restoreBackup"`
- `DELETE_BACKUP = "deleteBackup"`
- `CREATE_SNAPSHOT = "createSnapshot"`
- `RESTORE_SNAPSHOT = "restoreSnapshot"`
- `DELETE_SNAPSHOT = "deleteSnapshot"`

## On-disk layout and data model

`PackageBackups` writes backups under Foundry's configured backup root (`global.paths.backups`), not under the CLI's own `FOUNDRY_ADMIN_BACKUP_DIR`.

Package backup layout:

```text
<foundry-backups>/<package-collection>/<package-id>/<backup-id>.bak
<foundry-backups>/<package-collection>/<package-id>/<backup-id>.json
```

For example, package backup ids are shaped like:

```text
world.my-world.2026-06-09.1781000000000
module.some-module.2026-06-09.1781000000000
system.dnd5e.2026-06-09.1781000000000
```

The `.bak` file is a zip archive of the package installation directory. The `.json` manifest contains package metadata and backup metadata, including:

- `id`
- `type`
- `packageId`
- `title`
- `description`
- `version`
- `compatibility`
- `relationships`
- `system`
- `createdAt`
- `size`
- `originalSize`
- `note`
- nullable `snapshotId`

Snapshot layout:

```text
<foundry-backups>/snapshots/<snapshot-id>.json
```

Snapshot ids are shaped like:

```text
snapshot.2026-06-09.1781000000000
```

Snapshot manifests include:

- `id`
- `type = "snapshot"`
- `generation`
- `build`
- `createdAt`
- `size`
- `originalSize`
- `note`
- `backups` set of included package backup ids

## Restore semantics

Package restore extracts the backup archive to a temp directory, removes the current package install directory, copies the extracted content into place, and refreshes package caches.

Snapshot restore extracts all referenced package backups, then installs them. For existing packages, it first renames the current installation into a temporary `tmp.original` directory. If a later package restore fails, it rolls back already-restored packages from `tmp.original`.

Important implementation details:

- `restoreBackup` and `restoreSnapshot` are asynchronous setup actions that report progress over the setup progress channel.
- The HTTP response from `POST /setup` is `{}`; completion/failure is reported asynchronously via progress events.
- `restoreSnapshot` has rollback for packages already touched during the same snapshot restore.
- Package restore is destructive to the target package directory.

## Official limitation

Foundry's own docs state that setup backups and snapshots only include package folders:

- `Data/worlds`
- `Data/systems`
- `Data/modules`

They do **not** include data outside package directories, including image/sound/assets stored elsewhere in User Data.

The manual backup docs state that the most complete backup is the whole User Data `Data` folder, and that `Config` contains important server settings and secured information. Manual Linux backup guidance is to stop Foundry, then archive at least `Data` and `Config`.

## Setup-mode boundary

The setup route only permits most setup actions when no world is active and the admin session is authenticated. The v13 setup source guards setup operations with the same boundary already documented for package and world lifecycle work.

Implication: CLI commands that use Foundry-native backup actions should require setup mode, or safely return to setup first with an explicit restore plan.

## Sufficiency assessment

Foundry-native backup/restore is sufficient for first-class CLI support of package-level operations:

- Backup/restore a specific world before risky CLI mutations.
- Backup/restore modules and systems before package updates/removals.
- Create/list/restore snapshots before major core/system/package upgrades.
- Reuse Foundry's metadata format and compatibility checks where possible.
- Avoid inventing a competing package-backup archive format.

Foundry-native backup/restore is **not** sufficient as the only CLI backup strategy:

- It omits assets outside `Data/worlds`, `Data/modules`, and `Data/systems`.
- It omits `Config`, including `options.json`, license/configuration, and server settings.
- It does not cover the CLI's existing targeted pre-write backups under `FOUNDRY_ADMIN_BACKUP_DIR`.
- It requires setup/admin protocol availability and generally no active world.
- The CLI cannot treat the immediate HTTP response as completion; it must follow progress or verify resulting backup files/list output.

## Recommendation

Use a two-tier design.

### Tier 1: Foundry-native package backup commands

Add a `backup` namespace that drives Foundry setup actions:

```bash
fvtt --version v13 backup list [--type world|system|module|snapshot] [--package-id ID] [--json]
fvtt --version v13 backup create --type world --package-id my-world [--note TEXT] [--json]
fvtt --version v13 backup snapshot [--note TEXT] [--json]
fvtt --version v13 backup restore <backup-id> --force [--json]
fvtt --version v13 backup restore-snapshot <snapshot-id> --force [--json]
fvtt --version v13 backup delete <backup-id> --force [--json]
fvtt --version v13 backup delete-snapshot <snapshot-id> --force [--json]
```

Implementation should:

1. Authenticate setup admin using the existing `AdminClient` cookie/session flow.
2. Require setup mode, or fail with a clear `active_world` message.
3. Use `POST /setup` actions above.
4. For create/restore/delete, handle async completion by either:
   - connecting to the setup progress socket and waiting for final `complete/error`, or
   - polling `listBackups` and verifying expected file/manifest state when socket progress is not yet implemented.
5. Return Foundry backup ids and sanitized manifest summaries.
6. Never echo private paths, raw cookie/session data, or secret config.

### Tier 2: CLI-native full user-data archive commands

A separate full-data archive path is implemented for operator-grade disaster recovery:

```bash
fvtt --version v13 backup data-create --include-config --output /safe/path/foundry-user-data.tar.gz
fvtt --version v13 backup data-restore /safe/path/foundry-user-data.tar.gz --force
```

Implementation behavior:

1. Requires local mode and filesystem access.
2. Requires Foundry stopped by default; `--allow-running` is an explicit unsafe override.
3. Archives top-level `Data/` and optionally sensitive `Config/`.
4. Rejects archive output paths inside User Data to avoid self-inclusion.
5. Creates output directories as `0700` and archive files as `0600`.
6. Writes a pre-restore archive before replacing directories.
7. Validates restore archives before extraction and rejects absolute paths, path traversal, unsupported roots, symlinks, hardlinks, special files, and non-directory top-level `Data`/`Config` entries.
8. Treats archives as sensitive because `Config` can contain license and server secrets.
9. Never commit or place these archives in repo or chat-visible locations.

### Existing CLI targeted backups remain separate

The existing CLI backup root remains appropriate for pre-write rollback of individual files and archived deletes:

- `Config/options.json` before `world run/stop`.
- `Data/worlds/<id>/world.json` before manifest edits.
- package manifests before CLI metadata edits.
- archived deleted worlds/systems/modules.

Those backups are local CLI safety artifacts, not replacements for Foundry package backups or full disaster-recovery archives.

## Implemented CLI surface

The implementation exposes both tiers:

1. `backup list [--type world|system|module|snapshot] [--package-id ID] --json`
2. `backup create --type world|system|module --package-id <id> [--note <text>] --json`
3. `backup snapshot [--note <text>] --json`
4. `backup restore <backup-id> --force --json`
5. `backup restore-snapshot <snapshot-id> --force --json`
6. `backup delete <backup-id> --force --json`
7. `backup delete-snapshot <snapshot-id> --force --json`
8. `backup data-create [--include-config] [--output path.tar.gz] [--allow-running] --json`
9. `backup data-restore path.tar.gz --force [--allow-running] --json`

## Test/verification plan

Unit tests:

- CLI parser exposes `backup` namespace and subcommands.
- Setup payloads match Foundry v13 action shapes.
- Active-world setup boundary returns structured error.
- Backup id parsing handles world/system/module/snapshot ids and rejects malformed ids.
- Restore/delete require `--force`.
- Output redacts private paths and secrets.

Integration smoke on isolated/temp Foundry v13:

1. Create throwaway world.
2. Return to setup.
3. `backup create --type world --package-id fvtt-cli-backup-smoke --json`.
4. Verify `backup list --json` includes the new backup id.
5. Mutate the world manifest title.
6. `backup restore <backup-id> --force --json`.
7. Verify the manifest title is restored.
8. Create snapshot.
9. Verify snapshot appears in list.
10. Clean up throwaway world and backup artifacts.

## Bottom line

Do not build a competing package backup implementation. Foundry's package backup/snapshot functionality is the right primitive for worlds/modules/systems and should be surfaced by the CLI.

Do build an extra CLI-native full user-data archive process for `Data`/`Config` disaster recovery, because Foundry's setup backups explicitly do not cover those paths.
