from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def default_foundry_config_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Give unit tests portable non-secret Foundry config unless a test overrides it."""

    defaults = {
        "FOUNDRY_V13_INSTALL_DIR": str(tmp_path / "foundry"),
        "FOUNDRY_V13_DATA_DIR": str(tmp_path / "data"),
        "FOUNDRY_V13_URL": "http://foundry.test/",
        "FOUNDRY_V13_PM2_NAME": "foundry-test",
    }
    for key, value in defaults.items():
        if key not in os.environ:
            monkeypatch.setenv(key, value)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-foundry-integration",
        action="store_true",
        default=False,
        help="Run live Foundry v13 integration tests that mutate fvtt-cli-* throwaway data.",
    )


@pytest.fixture
def run_foundry_integration(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--run-foundry-integration"))
