# foundry-admin-cli — Development Notes

## Purpose

CLI/control layer for Foundry VTT setup/admin operations before Foundry MCP Bridge is available. The CLI must be able to bootstrap a world and enable modules, including MCP Bridge, without using MCP.

## Runtime Configuration

Runtime targets are config-driven. Do not put local machine paths, hostnames, PM2 binary paths, user HOME values, cache dirs, or backup dirs in source.

Local non-secret configuration belongs in `.env` or `foundry-admin-cli.toml`; `.env` is gitignored and `.env.example` documents the supported keys. See `docs/configuration.md`.

Required per-version keys for live/local use (`FOUNDRY_V13_*` or `FOUNDRY_V14_*`):

- `FOUNDRY_<VERSION>_INSTALL_DIR`
- `FOUNDRY_<VERSION>_DATA_DIR`
- `FOUNDRY_<VERSION>_URL`
- `FOUNDRY_<VERSION>_PM2_NAME`

Shared optional keys:

- `FOUNDRY_ADMIN_PM2_BIN`
- `FOUNDRY_ADMIN_RUN_HOME`
- `FOUNDRY_ADMIN_PROJECTS_DIR`
- `FOUNDRY_ADMIN_CACHE_DIR`
- `FOUNDRY_ADMIN_BACKUP_DIR`
- `FOUNDRY_ADMIN_NODE_BIN`

## Build / Test Commands

```bash
uv run pytest
uv run fvtt --help
uv run fvtt --version v13 status --json
uv run fvtt --version v14 status --json
uv run fvtt --version v13 wait --json
uv run fvtt --version v13 admin status --json
uv run fvtt --version v13 system list --json
uv run fvtt --version v13 module list --json
uv run fvtt --version v13 game ping --json
uv run fvtt --version v13 game module list --world module-test-black-flag --json
uv run fvtt --version v13 game settings list --world module-test-black-flag --namespace foundry-mcp-bridge --json
uv run pytest tests/integration/test_v13_lifecycle.py -q --run-foundry-integration
```

Use configured `FOUNDRY_ADMIN_RUN_HOME` for PM2/process context instead of hardcoded source HOME.

## Architecture

- `src/foundry_admin_cli/cli.py` — argparse command surface.
- `src/foundry_admin_cli/config.py` — config/env/TOML loading and versioned Foundry instance definitions.
- `src/foundry_admin_cli/process.py` — PM2/status/restart/log/readiness helpers.
- `src/foundry_admin_cli/admin_client.py` — v13/v14 setup/admin login/session/status client.
- `src/foundry_admin_cli/worlds.py` — world lifecycle.
- `src/foundry_admin_cli/packages.py` — shared setup package install helper.
- `src/foundry_admin_cli/systems.py` — system package lifecycle.
- `src/foundry_admin_cli/modules.py` — module package lifecycle and scaffold helpers.
- `src/foundry_admin_cli/world_client.py` — v13/v14 in-world GM login/session client.
- `src/foundry_admin_cli/world_users.py` — active-game user management via v13/v14 world socket.
- `src/foundry_admin_cli/world_settings.py` — active-game settings inspection and MCP Bridge bootstrap settings via v13/v14 world socket.
- `src/foundry_admin_cli/world_modules.py` — active-world module management via v13/v14 world socket.
- `src/foundry_admin_cli/license_client.py` — fresh-install `/license` activation and EULA signing.
- `src/foundry_admin_cli/bootstrap_agent.py` — high-level agent bootstrap orchestration without MCP.

Future adapters:

- Remote/http-only adapter support is not implemented; those modes fail fast for local-only commands.

## Hard Rules

1. Do not modify Foundry core by default.
2. If a core patch is ever required, stop and create a reproducible patch workflow first: exact Foundry build, patch files, apply/verify/rollback commands, and fresh-install smoke test.
3. Active-world module management must not depend on MCP Bridge. Enabling MCP Bridge is a primary CLI bootstrap use case.
4. Never ask Jon to paste credentials in chat. Use local env vars/config only.
5. Destructive operations archive by default and require `--force` for permanent deletion.
6. Write tests before implementation for behavior changes.
7. Commit and push every meaningful change.
8. Before install/finalization, run the source hardcode audit and keep local runtime values out of `src/`.

## References

- Plan: `/home/jon/.hermes/profiles/hephaestus/plans/2026-06-09_054044-foundry-admin-cli.md`
- Research: `/home/jon/Documents/jon_vault/Projects/software/foundry-admin-cli-research.md`
- MCP integration: `/home/jon/Documents/jon_vault/Projects/software/foundry-mcp-integration.md`
- Future functionality backlog: `docs/future-functionality.md`
