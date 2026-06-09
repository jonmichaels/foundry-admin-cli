# Foundry Admin CLI v13 Test Matrix

Task 11 adds an opt-in live integration matrix for Foundry v13. The default unit test suite does not mutate live Foundry data.

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
uv run fvtt --version v13 world login fvtt-cli-smoke \
  --user Gamemaster \
  --allow-empty-password \
  --json
```

Passwordless login is explicit; normal world login still requires `--password-env` unless `--allow-empty-password` is provided.

## Commands

Default suite, integration skipped:

```bash
uv run pytest -q
```

Live v13 integration matrix:

```bash
uv run pytest tests/integration/test_v13_lifecycle.py -q --run-foundry-integration
```

## Last verified

- Default suite: `uv run pytest -q` passed with the integration test skipped by default.
- Live matrix: `uv run pytest tests/integration/test_v13_lifecycle.py -q --run-foundry-integration` passed and restored `module-test-black-flag`.
