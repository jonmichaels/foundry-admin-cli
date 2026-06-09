# Foundry Admin CLI

`foundry-admin-cli` provides the `fvtt` command for Foundry VTT setup/admin operations before Foundry MCP Bridge is available.

Current release: **v0.3.0**. This is pre-1.0 software: it has been validated against Jon's local Foundry v13 setup and a live v13 integration matrix, but it is not a general-purpose, exhaustively tested Foundry administration suite yet.

## What it controls

Implemented for Foundry VTT v13:

- process/status helpers: `status`, `restart`, `wait`, `logs`
- setup/admin session helpers: `admin login`, `admin logout`, `admin status`, `admin whoami`, `admin probe`
- world lifecycle: `world list`, `create`, `edit`, `delete`, `run`, `stop`
- system lifecycle: `system list`, `install`, `update`, `remove`
- module lifecycle: `module list`, `install`, `update`, `create`, `edit`, `remove`
- running-game session helpers: `game login`, `game ping`
- active-game module controls: `game module list`, `enable`, `disable`, `set`
- active-game user management: `game user list/create/set-password/set-role/disable/delete`

The CLI is designed to run **on the machine that hosts Foundry**. For a remote Foundry server, SSH into that server and run `fvtt` there. It is not currently an SSH orchestration wrapper that runs on one machine while controlling another.

## Requirements

- Python 3.12+
- `uv` for development/editable installation
- Foundry VTT v13 installed on the target host
- PM2 for process lifecycle commands
- Node.js for socket helper commands such as active-world module controls
- Local filesystem access to Foundry's install and user-data directories

## Install

From the repository root:

```bash
uv tool install -e .
```

If replacing an older local script, back it up first:

```bash
mkdir -p backups/foundry-admin-cli
cp ~/.local/bin/fvtt backups/foundry-admin-cli/legacy-fvtt.py
uv tool install -e . --force
```

Confirm the installed command:

```bash
fvtt --cli-version
fvtt --help
```

Expected version:

```text
fvtt 0.3.0
```

## Configuration

Runtime paths, hosts, PM2 names, executable paths, cache dirs, and backup dirs are config-driven. Do not edit source for local machine settings.

Configuration precedence, from lowest to highest:

1. structural defaults
2. `foundry-admin-cli.toml`
3. local `.env`
4. process environment
5. explicit CLI overrides

Copy `.env.example` to `.env` on the Foundry host, or create `foundry-admin-cli.toml`.

Minimum v13 `.env`:

```bash
FOUNDRY_V13_INSTALL_DIR=/path/to/foundry-v13
FOUNDRY_V13_DATA_DIR=/path/to/foundryuserdata-v13
FOUNDRY_V13_URL=https://foundry.example.test/
FOUNDRY_V13_PM2_NAME=foundry-v13
FOUNDRY_V13_MODE=local
```

Optional shared settings:

```bash
FOUNDRY_ADMIN_PM2_BIN=pm2
FOUNDRY_ADMIN_RUN_HOME=/path/to/user-home
FOUNDRY_ADMIN_PROJECTS_DIR=/path/to/projects
FOUNDRY_ADMIN_CACHE_DIR=/path/to/cache/foundry-admin-cli
FOUNDRY_ADMIN_BACKUP_DIR=/path/to/backups/foundry-admin-cli
FOUNDRY_ADMIN_NODE_BIN=node
```

For a remote server reached by SSH, use the remote server's paths and keep `FOUNDRY_V13_MODE=local` because the CLI is running locally on that remote host.

Example for a host where Foundry runs as `ubuntu`:

```bash
FOUNDRY_V13_INSTALL_DIR=/home/ubuntu/foundry
FOUNDRY_V13_DATA_DIR=/home/ubuntu/foundryuserdata
FOUNDRY_V13_URL=https://myexamplefoundryserver.com/
FOUNDRY_V13_PM2_NAME=foundry-v13
FOUNDRY_V13_MODE=local
FOUNDRY_ADMIN_RUN_HOME=/home/ubuntu
FOUNDRY_ADMIN_PROJECTS_DIR=/home/ubuntu/projects
```

Use `mode=remote` or `mode=http-only` only to describe an instance that this CLI cannot manage through local filesystem/PM2/Node access. Local-only commands then fail fast with clean errors.

More details: [`docs/configuration.md`](docs/configuration.md).

## Common commands

```bash
fvtt --version v13 status --json
fvtt --version v13 wait --json
fvtt --version v13 logs --lines 50
fvtt --version v13 restart
```

Worlds:

```bash
fvtt --version v13 world list
fvtt --version v13 world create my-world --title "My World" --system dnd5e
fvtt --version v13 world run my-world
fvtt --version v13 world stop
fvtt --version v13 world edit my-world --title "New Title"
fvtt --version v13 world delete my-world --force
```

Systems:

```bash
fvtt --version v13 system list
fvtt --version v13 system install https://example.test/system.json
fvtt --version v13 system update dnd5e
fvtt --version v13 system remove old-system --force
```

Modules:

```bash
fvtt --version v13 module list
fvtt --version v13 module install https://example.test/module.json
fvtt --version v13 module update my-module
fvtt --version v13 module create my-module --title "My Module" --projects-dir /path/to/projects --symlink
fvtt --version v13 module edit my-module --title "New Title"
fvtt --version v13 module remove my-module --force
```

Admin/session:

```bash
export FOUNDRY_ADMIN_PASSWORD='...'
fvtt --version v13 admin login --password-env FOUNDRY_ADMIN_PASSWORD
fvtt --version v13 admin status --json
fvtt --version v13 admin logout
```

World login, return-to-setup, and active-game module controls:

```bash
export FOUNDRY_GM_PASSWORD='...'
export FOUNDRY_ADMIN_PASSWORD='...'
fvtt --version v13 game login my-world --user Gamemaster --password-env FOUNDRY_GM_PASSWORD
fvtt --version v13 game ping --json
fvtt --version v13 game return-to-setup --world my-world --admin-password-env FOUNDRY_ADMIN_PASSWORD
fvtt --version v13 world run my-world
fvtt --version v13 game user list --world my-world
fvtt --version v13 game user create --world my-world --name "Assistant" --role "Assistant Gamemaster" --password-env FOUNDRY_GM_PASSWORD
fvtt --version v13 game user set-role --world my-world --user Assistant --role Player
fvtt --version v13 game user disable --world my-world --user Assistant
fvtt --version v13 game module list --world my-world
fvtt --version v13 game module enable foundry-mcp-bridge --world my-world
fvtt --version v13 game module disable some-module --world my-world
fvtt --version v13 game module set --world my-world --modules foundry-mcp-bridge,lib-wrapper
```

Secrets are accepted only through environment variable names with `--password-env`; plaintext password CLI arguments are intentionally unsupported.

## Safety model

- No Foundry core patches by default.
- Destructive operations archive by default where supported.
- Permanent deletes require `--force`.
- Manifest and package IDs are validated before filesystem writes.
- Backups are written under the configured backup root.
- Local-only operations fail fast for `remote`/`http-only` instances.
- `.env` and `.env.*` are gitignored; `.env.example` is safe to commit.

## Development and verification

```bash
uv run pytest -q
uv run pytest tests/integration/test_v13_lifecycle.py -q --run-foundry-integration
uv run fvtt --version v13 status --json
```

The live integration test is opt-in and uses configured paths. Run it only on a prepared Foundry v13 host.

## Current limitations

- v13 is the implementation and validation target.
- v14 config shape exists, but v14 behavior is not validated.
- The CLI must be installed/run on the Foundry host; remote SSH orchestration is outside v0.3.0.
- Some setup-level operations require Foundry setup mode when an active world blocks setup actions.
- This tool controls Foundry setup/server/module state; in-world entity management remains the job of Foundry MCP Bridge once a world is running and the bridge is enabled.
