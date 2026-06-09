from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

WORLD_ID = "fvtt-cli-smoke"
MODULE_ID = "fvtt-cli-smoke-module"
SYSTEM_ID = "dnd5e"
ROOT = Path(__file__).resolve().parents[2]


def _local_env_value(name: str) -> str | None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
                continue
            key, raw_value = raw.split("=", 1)
            if key.strip() == name:
                return raw_value.strip().strip('"\'')
    return os.environ.get(name)


INTEGRATION_VERSION = _local_env_value("FOUNDRY_INTEGRATION_VERSION") or "v13"
DATA_DIR_RAW = _local_env_value("FOUNDRY_INTEGRATION_DATA_DIR") or _local_env_value("FOUNDRY_V13_DATA_DIR")
PROJECTS_DIR_RAW = _local_env_value("FOUNDRY_INTEGRATION_PROJECTS_DIR") or _local_env_value("FOUNDRY_ADMIN_PROJECTS_DIR")
DATA_DIR = Path(DATA_DIR_RAW) if DATA_DIR_RAW else Path(".")
OPTIONS_PATH = DATA_DIR / "Config" / "options.json"
PROJECTS_DIR = Path(PROJECTS_DIR_RAW) if PROJECTS_DIR_RAW else Path(".")
PROJECT_MODULE_DIR = PROJECTS_DIR / MODULE_ID
FOUNDRY_MODULE_LINK = DATA_DIR / "Data" / "modules" / MODULE_ID
WORLD_DIR = DATA_DIR / "Data" / "worlds" / WORLD_ID
MODULE_SENTINEL = PROJECT_MODULE_DIR / ".fvtt-cli-integration-test"


def _assert_safe_targets() -> None:
    for value in (WORLD_ID, MODULE_ID):
        assert value.startswith("fvtt-cli-")
        assert "/" not in value
        assert ".." not in value


def _run_fvtt(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    home = _local_env_value("FOUNDRY_INTEGRATION_HOME") or _local_env_value("FOUNDRY_ADMIN_RUN_HOME")
    if home:
        full_env.setdefault("HOME", home)
    for key in (
        "FOUNDRY_V13_INSTALL_DIR",
        "FOUNDRY_V13_DATA_DIR",
        "FOUNDRY_V13_URL",
        "FOUNDRY_V13_PM2_NAME",
        "FOUNDRY_ADMIN_PM2_BIN",
        "FOUNDRY_ADMIN_RUN_HOME",
        "FOUNDRY_ADMIN_PROJECTS_DIR",
        "FOUNDRY_ADMIN_NODE_BIN",
    ):
        value = _local_env_value(key)
        if value:
            full_env[key] = value
    if env:
        full_env.update(env)
    return subprocess.run(
        ["uv", "run", "fvtt", "--version", INTEGRATION_VERSION, *args],
        cwd=ROOT,
        env=full_env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _run_json(*args: str, env: dict[str, str] | None = None) -> Any:
    completed = _run_fvtt(*args, "--json", env=env)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    return json.loads(completed.stdout)


def _assert_success(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, completed.stderr + completed.stdout


def _assert_owned_project_module() -> None:
    manifest_path = PROJECT_MODULE_DIR / "module.json"
    assert MODULE_SENTINEL.exists(), f"Refusing to delete unsentinelized module path: {PROJECT_MODULE_DIR}"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("id") == MODULE_ID
    assert data.get("title") == "FVTT CLI Smoke Module"


def _remove_project_module_dir() -> None:
    _assert_owned_project_module()
    shutil.rmtree(PROJECT_MODULE_DIR)


def _run_json_eventually(*args: str, attempts: int = 5) -> Any:
    last = None
    for _ in range(attempts):
        completed = _run_fvtt(*args, "--json")
        if completed.returncode == 0:
            return json.loads(completed.stdout)
        last = completed
        time.sleep(2)
    assert last is not None
    raise AssertionError(last.stderr + last.stdout)


def _restart_and_wait() -> None:
    restarted = _run_json("restart", "--timeout", "90")
    assert restarted["ready"] is True


def _configured_world() -> str | None:
    data = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    world = data.get("world")
    return world if isinstance(world, str) and world else None


def _remove_throwaway_artifacts() -> None:
    if FOUNDRY_MODULE_LINK.is_symlink():
        if PROJECT_MODULE_DIR.exists():
            _assert_owned_project_module()
        FOUNDRY_MODULE_LINK.unlink()
    if WORLD_DIR.exists() or WORLD_DIR.is_symlink():
        completed = _run_fvtt("worlds", "delete", WORLD_ID, "--permanent", "--force", "--json")
        _assert_success(completed)
    if PROJECT_MODULE_DIR.exists() or PROJECT_MODULE_DIR.is_symlink():
        if FOUNDRY_MODULE_LINK.exists() or FOUNDRY_MODULE_LINK.is_symlink():
            completed = _run_fvtt("modules", "remove", MODULE_ID, "--permanent", "--force", "--json")
            _assert_success(completed)
        else:
            _remove_project_module_dir()


def _cleanup_after_test(original_world: str | None, module_created: bool) -> None:
    errors: list[str] = []
    restore = (
        _run_fvtt("worlds", "run", original_world, "--json")
        if original_world
        else _run_fvtt("worlds", "stop", "--json")
    )
    if restore.returncode != 0:
        errors.append(restore.stderr + restore.stdout)
    if module_created:
        removed = _run_fvtt("modules", "remove", MODULE_ID, "--permanent", "--force", "--json")
        if removed.returncode != 0 and (FOUNDRY_MODULE_LINK.exists() or FOUNDRY_MODULE_LINK.is_symlink()):
            errors.append(removed.stderr + removed.stdout)
    if FOUNDRY_MODULE_LINK.exists() or FOUNDRY_MODULE_LINK.is_symlink():
        if PROJECT_MODULE_DIR.exists():
            _assert_owned_project_module()
        FOUNDRY_MODULE_LINK.unlink()
    if PROJECT_MODULE_DIR.exists() or PROJECT_MODULE_DIR.is_symlink():
        _remove_project_module_dir()
    if WORLD_DIR.exists() or WORLD_DIR.is_symlink():
        deleted = _run_fvtt("worlds", "delete", WORLD_ID, "--permanent", "--force", "--json")
        if deleted.returncode != 0:
            errors.append(deleted.stderr + deleted.stdout)
    _restart_and_wait()
    if errors:
        raise AssertionError("\n".join(errors))


@pytest.mark.integration
def test_v13_throwaway_lifecycle_matrix(run_foundry_integration: bool) -> None:
    if not run_foundry_integration:
        pytest.skip("requires --run-foundry-integration")
    _assert_safe_targets()
    if not DATA_DIR_RAW:
        pytest.fail("FOUNDRY_INTEGRATION_DATA_DIR or FOUNDRY_V13_DATA_DIR is required")
    if not PROJECTS_DIR_RAW:
        pytest.fail("FOUNDRY_INTEGRATION_PROJECTS_DIR or FOUNDRY_ADMIN_PROJECTS_DIR is required")

    original_world = _configured_world()
    if original_world and original_world.startswith("fvtt-cli-"):
        original_world = None
    module_created = False
    try:
        _remove_throwaway_artifacts()

        created_world = _run_json(
            "worlds",
            "create",
            WORLD_ID,
            "--title",
            "FVTT CLI Smoke",
            "--system",
            SYSTEM_ID,
        )
        assert created_world["world"] == WORLD_ID

        configured = _run_json("worlds", "run", WORLD_ID)
        assert configured["world"] == WORLD_ID
        _restart_and_wait()

        login = _run_json(
            "world",
            "login",
            WORLD_ID,
            "--user",
            "Gamemaster",
            "--allow-empty-password",
        )
        assert login["authenticated"] is True
        assert login["user"] != "Gamemaster"
        resolved_gamemaster_id = login["user"]

        module = _run_json(
            "modules",
            "create",
            MODULE_ID,
            "--title",
            "FVTT CLI Smoke Module",
            "--projects-dir",
            str(PROJECTS_DIR),
            "--symlink",
        )
        assert module["module"] == MODULE_ID
        module_created = True
        MODULE_SENTINEL.write_text("owned by tests/integration/test_v13_lifecycle.py\n", encoding="utf-8")
        _restart_and_wait()
        login = _run_json(
            "world",
            "login",
            WORLD_ID,
            "--user",
            resolved_gamemaster_id,
            "--allow-empty-password",
        )
        assert login["authenticated"] is True

        modules_before = _run_json_eventually("world", "modules", "list", "--world", WORLD_ID)
        assert any(row["id"] == MODULE_ID for row in modules_before["modules"])

        enabled = _run_json("world", "modules", "enable", MODULE_ID, "--world", WORLD_ID)
        assert enabled["modules"][MODULE_ID] is True
        listed_enabled = _run_json("world", "modules", "list", "--world", WORLD_ID)
        assert next(row for row in listed_enabled["modules"] if row["id"] == MODULE_ID)["active"] is True

        disabled = _run_json("world", "modules", "disable", MODULE_ID, "--world", WORLD_ID)
        assert disabled["modules"][MODULE_ID] is False
        listed_disabled = _run_json("world", "modules", "list", "--world", WORLD_ID)
        assert next(row for row in listed_disabled["modules"] if row["id"] == MODULE_ID)["active"] is False
    finally:
        _cleanup_after_test(original_world, module_created)
