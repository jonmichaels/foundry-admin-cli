# foundry-admin-cli Configuration

`foundry-admin-cli` must be configured for the Foundry installation it controls. Runtime paths, hostnames, process names, and executable paths are intentionally not hardcoded in source.

## Precedence

Configuration is merged in this order, with later sources winning:

1. safe built-in structural defaults
2. `foundry-admin-cli.toml` from the current directory or XDG config, or an explicit `--config PATH`
3. project/local `.env`
4. process environment
5. explicit CLI overrides such as `--data-dir` or `--pm2-bin`

Secrets are still read only from environment or local `.env` by the specific `--password-env` name. Do not place secrets in committed files.

## Environment keys

Instance-specific keys:

```bash
FOUNDRY_V13_INSTALL_DIR=/path/to/foundry-v13
FOUNDRY_V13_DATA_DIR=/path/to/foundryuserdata-v13
FOUNDRY_V13_URL=http://foundry.example.test:30000/
FOUNDRY_V13_PM2_NAME=foundry-v13
FOUNDRY_V13_MODE=local
```

Equivalent `FOUNDRY_V14_*` keys are supported.

Shared keys:

```bash
FOUNDRY_ADMIN_PM2_BIN=pm2
FOUNDRY_ADMIN_RUN_HOME=/path/to/user-home
FOUNDRY_ADMIN_PROJECTS_DIR=/path/to/projects
FOUNDRY_ADMIN_CACHE_DIR=/path/to/cache/foundry-admin-cli
FOUNDRY_ADMIN_BACKUP_DIR=/path/to/backups/foundry-admin-cli
FOUNDRY_ADMIN_NODE_BIN=node
```

Live integration-test keys:

```bash
FOUNDRY_INTEGRATION_VERSION=v13
FOUNDRY_INTEGRATION_DATA_DIR=/path/to/foundryuserdata-v13
FOUNDRY_INTEGRATION_PROJECTS_DIR=/path/to/projects
FOUNDRY_INTEGRATION_HOME=/path/to/user-home
```

## TOML example

```toml
[shared]
pm2_bin = "pm2"
run_home = "/path/to/user-home"
projects_dir = "/path/to/projects"
cache_dir = "/path/to/cache/foundry-admin-cli"
backup_dir = "/path/to/backups/foundry-admin-cli"
node_bin = "node"

[instances.v13]
install_dir = "/path/to/foundry-v13"
data_dir = "/path/to/foundryuserdata-v13"
url = "http://foundry.example.test:30000/"
pm2_name = "foundry-v13"
mode = "local"
```

## Local vs remote instances

`mode = "local"` means the CLI may read/write the Foundry data directory, call PM2, and run Node/socket helpers from the Foundry install directory on the machine where `fvtt` is running.

For an SSH-only remote server, install `foundry-admin-cli` on that server, SSH in, and run `fvtt` there. In that scenario the instance should still be `mode = "local"` because the CLI process is local to the Foundry filesystem and PM2 process.

`mode = "remote"` or `mode = "http-only"` means local-only commands fail fast with an actionable error. A remote URL alone is not enough for package/world filesystem mutations or PM2 lifecycle commands, and v0.3.0 does not include an SSH orchestration wrapper.

## CLI overrides

Global overrides are available before the subcommand:

```bash
fvtt --version v13 \
  --config ./foundry-admin-cli.toml \
  --data-dir /path/to/data \
  --install-dir /path/to/foundry \
  --url http://foundry.example.test:30000/ \
  --pm2-name foundry-v13 \
  --pm2-bin pm2 \
  --run-home /path/to/user-home \
  status --json
```

`modules create` also supports `--projects-dir PATH` for one-off scaffold location overrides.
