# Foundry Admin CLI v13/v14 Test Matrix

The default unit test suite does not mutate live Foundry data. The repository has an opt-in live integration matrix for configured Foundry v13 and a manual isolated fresh-install smoke for Foundry v14 bootstrap compatibility.

## Safety gates

- Live integration tests run only with `--run-foundry-integration`.
- Throwaway world and module ids must start with `fvtt-cli-`.
- The matrix snapshots the originally configured world and restores it in `finally` cleanup.
- Throwaway cleanup removes only:
  - world `fvtt-cli-smoke`
  - module `fvtt-cli-smoke-module`
- The test uses permanent deletion only for those fixed throwaway ids.

## Matrix sequence

`tests/integration/test_v13_lifecycle.py` exercises:

1. Read current `Config/options.json` configured world.
2. Remove stale `fvtt-cli-*` artifacts from prior failed runs.
3. Create world `fvtt-cli-smoke` with installed system `dnd5e`.
4. Configure it as the running world.
5. Restart Foundry v13 and wait for readiness.
6. Log in as the fresh default `Gamemaster` user with an explicit passwordless login flag.
7. Create and symlink module `fvtt-cli-smoke-module`.
8. List world modules and verify the test module is visible.
9. Enable the module in the running world.
10. Verify active state from the world socket context.
11. Disable the module and verify inactive state.
12. Restore the previously configured world or setup mode.
13. Delete throwaway world/module artifacts.
14. Restart Foundry v13 and wait for readiness.

## Fresh-world user behavior

Foundry v13 creates a new world with one user named `Gamemaster` and no password. `/join` authenticates with the user's internal id, not the display name, so the CLI resolves a local display name to the generated id before posting to `/join`. The integration matrix intentionally exercises this bootstrap case with:

```bash
uv run fvtt --version v13 game login fvtt-cli-smoke \
  --user Gamemaster \
  --allow-empty-password \
  --json
```

Passwordless login is explicit; normal game login still requires `--password-env` unless `--allow-empty-password` is provided.

## Return-to-setup flow

The CLI mirrors the in-game sidebar action with:

```bash
uv run fvtt --version v13 game return-to-setup --world fvtt-cli-smoke --admin-password-env FOUNDRY_ADMIN_PASSWORD --json
uv run fvtt --version v13 world run fvtt-cli-smoke --json
uv run fvtt --version v13 restart --json
```

`--admin-password-env` is optional and is used only when Foundry redirects back to admin authentication after shutting down the active world.

## Commands

Default suite, integration skipped:

```bash
uv run pytest -q
```

Live v13 integration matrix:

```bash
uv run pytest tests/integration/test_v13_lifecycle.py -q --run-foundry-integration
```

## v14 bootstrap smoke

The v14 bootstrap smoke uses a throwaway Foundry v14 install copy, isolated User Data root, isolated port, and unique PM2 process name. The sequence is:

1. Start the temp v14 process with `--dataPath`, `--port`, and an admin password override.
2. `fvtt --version v14 wait`.
3. Activate/sign the Foundry license first if the server redirects to `/license`.
4. `admin login`, `system install dnd5e`, and `world create` for a throwaway world.
5. Run `bootstrap-agent` against the throwaway world with passwordless fresh `Gamemaster`, license env, admin password env, and MCP Bridge host env.
6. Verify `verified: true`, required bootstrap steps, no license/admin/MCP host leaks, then delete the temp PM2 process and temp install/data root.

Do not run this against the configured production v14 data directory.

## Last verified

- Default suite: `uv run pytest --tb=no` passed with `264 passed, 1 skipped` after backup/restore documentation cleanup (integration test skipped by default).
- Bootstrap E2E smoke: isolated fresh Foundry v13.351 temp install/data on port `30002` started at `/license`, then `bootstrap-agent` activated license/EULA, installed MCP Bridge, launched a fresh throwaway world, logged in as passwordless `Gamemaster`, enabled/configured MCP Bridge `0.8.3`, verified bridge state, reported no license/admin/user/MCP host leaks, and cleaned up the temp PM2 process/data.
- v14 bootstrap E2E smoke: isolated fresh Foundry v14.363 temp install/data on port `30002`; license-first activation, admin login, `dnd5e` install, throwaway world create, `bootstrap-agent`, active-game module enablement, MCP Bridge settings, final `verified: true`, secret/host redaction checks, and temp PM2/install/data cleanup all passed.
- Game-settings coverage: unit/CLI tests cover `game settings list/get/set/apply-mcp-bridge`, namespace/category/query/config/world filters, JSON/env value handling with redaction, client-scope rejection, active-world guard, and MCP Bridge active-module prerequisite.
- Return-to-setup live smoke: created throwaway `fvtt-cli-return`, launched it, logged in with explicit passwordless `Gamemaster`, ran `game return-to-setup`, verified active world cleared while configured world remained set, deleted the throwaway world, restored `module-test-black-flag`, and restarted successfully.
- User-management live smoke: created throwaway `fvtt-cli-users`, launched it, logged in with explicit passwordless `Gamemaster`, listed users, created `CLI Scout`, changed role, disabled it, deleted it, returned to setup, deleted the throwaway world, restored `module-test-black-flag`, and restarted successfully. A second smoke covered `game user create --password-env` and `game user set-password --password-env` without echoing secret values.
- Live matrix: `uv run pytest tests/integration/test_v13_lifecycle.py -q --run-foundry-integration` passed and restored `module-test-black-flag`.
