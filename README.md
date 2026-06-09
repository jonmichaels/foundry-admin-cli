# Foundry Admin CLI

Agent-facing CLI for Foundry VTT setup/admin control.

Initial target: Foundry VTT v13 on noisy.

## Development

```bash
uv run pytest
uv run fvtt --help
uv run fvtt --version v13 status --json
```

## Runtime assumptions

- No Foundry core patches by default.
- v13 install: `/home/jon/foundry`
- v13 data: `/home/jon/foundryuserdata`
- v13 URL: `http://noisy.humung.us:30000/`
- v13 PM2 process: `foundry-v13`
- Commands that touch PM2 must run with `HOME=/home/jon`.
