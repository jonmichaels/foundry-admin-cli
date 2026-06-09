# Foundry Admin CLI

Agent-facing CLI for Foundry VTT setup/admin control.

Initial implementation target: Foundry VTT v13. Runtime paths, hosts, process names, executable paths, cache dirs, and backup dirs are loaded from config/env instead of source constants.

## Development

```bash
uv run pytest
uv run fvtt --help
uv run fvtt --version v13 status --json
```

## Configuration

Copy `.env.example` to `.env` for local non-secret runtime settings, or create `foundry-admin-cli.toml`. Local `.env` files are gitignored.

Required v13 values:

```bash
FOUNDRY_V13_INSTALL_DIR=/path/to/foundry-v13
FOUNDRY_V13_DATA_DIR=/path/to/foundryuserdata-v13
FOUNDRY_V13_URL=http://foundry.example.test:30000/
FOUNDRY_V13_PM2_NAME=foundry-v13
```

Optional shared values:

```bash
FOUNDRY_ADMIN_PM2_BIN=pm2
FOUNDRY_ADMIN_RUN_HOME=/path/to/user-home
FOUNDRY_ADMIN_PROJECTS_DIR=/path/to/projects
FOUNDRY_ADMIN_CACHE_DIR=/path/to/cache/foundry-admin-cli
FOUNDRY_ADMIN_BACKUP_DIR=/path/to/backups/foundry-admin-cli
FOUNDRY_ADMIN_NODE_BIN=node
```

See `docs/configuration.md` for precedence, TOML examples, local-vs-remote capability rules, and integration-test settings.

## Runtime assumptions

- No Foundry core patches by default.
- Destructive operations archive by default and require explicit force for permanent deletion.
- PM2/process commands require a `local` instance configuration.
- Remote/http-only instances fail fast for commands that need local filesystem, PM2, or Node/socket-helper access.
- Secrets are read only from environment or local `.env` via `--password-env`; plaintext password CLI args are not supported.
