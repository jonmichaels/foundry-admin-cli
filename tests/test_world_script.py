import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.world_script import ScriptExecutionError, execute_world_script


def instance(tmp_path, *, mode="local"):
    return FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://foundry.test/",
        pm2_name="foundry-v13",
        mode=mode,
    )


class FakeTransport:
    def __init__(self, *, world="module-test", result=None):
        self.world = world
        self.result = result if result is not None else {"ok": True, "value": 42}
        self.requests = []

    def execute_script(self, instance, *, script, timeout_seconds):
        self.requests.append({"script": script, "timeout_seconds": timeout_seconds})
        return {"world": {"id": self.world}, "result": self.result}


def test_execute_world_script_requires_explicit_danger_acknowledgement(tmp_path):
    with pytest.raises(ScriptExecutionError, match="--dangerously-allow-script is required"):
        execute_world_script(
            instance(tmp_path),
            "module-test",
            script="return game.world.id;",
            dangerously_allow_script=False,
            transport=FakeTransport(),
        )


def test_execute_world_script_runs_script_and_wraps_result(tmp_path):
    transport = FakeTransport(result={"id": "module-test", "system": "dnd5e"})

    result = execute_world_script(
        instance(tmp_path),
        "module-test",
        script="return {id: game.world.id, system: game.system.id};",
        dangerously_allow_script=True,
        transport=transport,
    )

    assert result == {
        "version": "v13",
        "world": "module-test",
        "ok": True,
        "result": {"id": "module-test", "system": "dnd5e"},
    }
    assert transport.requests == [
        {
            "script": "return {id: game.world.id, system: game.system.id};",
            "timeout_seconds": 20,
        }
    ]


def test_execute_world_script_rejects_wrong_running_world(tmp_path):
    with pytest.raises(ScriptExecutionError, match="running world is other-world; expected module-test"):
        execute_world_script(
            instance(tmp_path),
            "module-test",
            script="return game.world.id;",
            dangerously_allow_script=True,
            transport=FakeTransport(world="other-world"),
        )


def test_execute_world_script_requires_local_instance(tmp_path):
    with pytest.raises(Exception, match="requires local"):
        execute_world_script(
            instance(tmp_path, mode="http-only"),
            "module-test",
            script="return game.world.id;",
            dangerously_allow_script=True,
            transport=FakeTransport(),
        )


def test_execute_world_script_file_reads_script_from_path(tmp_path):
    script_path = tmp_path / "probe.js"
    script_path.write_text("return game.modules.size;", encoding="utf-8")
    transport = FakeTransport(result=7)

    result = execute_world_script(
        instance(tmp_path),
        "module-test",
        script_file=script_path,
        dangerously_allow_script=True,
        transport=transport,
    )

    assert result["result"] == 7
    assert transport.requests[0]["script"] == "return game.modules.size;"


def test_execute_world_script_requires_exactly_one_script_source(tmp_path):
    script_path = tmp_path / "probe.js"
    script_path.write_text("return 1;", encoding="utf-8")

    with pytest.raises(ScriptExecutionError, match="exactly one"):
        execute_world_script(
            instance(tmp_path),
            "module-test",
            script="return 2;",
            script_file=script_path,
            dangerously_allow_script=True,
            transport=FakeTransport(),
        )

    with pytest.raises(ScriptExecutionError, match="exactly one"):
        execute_world_script(
            instance(tmp_path),
            "module-test",
            dangerously_allow_script=True,
            transport=FakeTransport(),
        )
