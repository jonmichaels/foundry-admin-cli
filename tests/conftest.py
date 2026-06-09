from __future__ import annotations

import pytest


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
