# foundry-admin-cli — Development Notes

## Purpose

CLI/control layer for Foundry VTT setup/admin operations before Foundry MCP Bridge is available. The CLI must be able to bootstrap a world and enable modules, including MCP Bridge, without using MCP.

## Runtime Targets

Initial target is Foundry VTT v13 on noisy:

- Install: `/home/jon/foundry`
- Data: `/home/jon/foundryuserdata`
- URL: `http://noisy.humung.us:30000/`
- PM2 process: `foundry-v13`

v14 paths are kept only as future adapter data until v13 is proven:

- Install: `/home/jon/foundry14`
- Data: `/home/jon/foundryuserdata14`
- URL: `http://noisy.humung.us:30001/`
- PM2 process: `foundry-v14`

## Build / Test Commands

```bash
uv run pytest
uv run fvtt --help
uv run fvtt --version v13 status --json
uv run fvtt --version v13 wait --json
uv run fvtt --version v13 admin status --json
uv run fvtt --version v13 systems list --json
uv run fvtt --version v13 modules list --json
uv run fvtt --version v13 world ping --json
uv run fvtt --version v13 world modules list --world module-test-black-flag --json
```

Use `HOME=/home/jon` for PM2, gh, and other user-authenticated commands from Hermes.

## Architecture

- `src/foundry_admin_cli/cli.py` — argparse command surface.
- `src/foundry_admin_cli/config.py` — versioned Foundry instance definitions.
- `src/foundry_admin_cli/process.py` — PM2/status/restart/log/readiness helpers.
- `src/foundry_admin_cli/admin_client.py` — v13 setup/admin login/session/status client.
- `src/foundry_admin_cli/worlds.py` — world lifecycle.
- `src/foundry_admin_cli/packages.py` — shared setup package install helper.
- `src/foundry_admin_cli/systems.py` — system package lifecycle.
- `src/foundry_admin_cli/modules.py` — module package lifecycle and scaffold helpers.
- `src/foundry_admin_cli/world_client.py` — v13 in-world GM login/session client.
- `src/foundry_admin_cli/world_modules.py` — active-world module management via v13 world socket.

Future adapters:

- None currently.

## Hard Rules

1. Do not modify Foundry core by default.
2. If a core patch is ever required, stop and create a reproducible patch workflow first: exact Foundry build, patch files, apply/verify/rollback commands, and fresh-install smoke test.
3. Active-world module management must not depend on MCP Bridge. Enabling MCP Bridge is a primary CLI bootstrap use case.
4. Never ask Jon to paste credentials in chat. Use local env vars/config only.
5. Destructive operations archive by default and require `--force` for permanent deletion.
6. Write tests before implementation for behavior changes.
7. Commit and push every meaningful change.

## References

- Plan: `/home/jon/.hermes/profiles/hephaestus/plans/2026-06-09_054044-foundry-admin-cli.md`
- Research: `/home/jon/Documents/jon_vault/Projects/software/foundry-admin-cli-research.md`
- MCP integration: `/home/jon/Documents/jon_vault/Projects/software/foundry-mcp-integration.md`
