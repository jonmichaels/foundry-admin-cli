from __future__ import annotations

from pathlib import Path

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.world_client import resolve_world_user_id


def test_resolve_world_user_id_maps_display_name_to_internal_id(tmp_path: Path):
    data_dir = tmp_path / "data"
    users_dir = data_dir / "Data" / "worlds" / "fvtt-cli-smoke" / "data" / "users"
    users_dir.mkdir(parents=True)
    (users_dir / "000003.log").write_text(
        '!users!abc123\n{"name":"Gamemaster","role":4,"_id":"abc123","password":"x"}\n',
        encoding="utf-8",
    )
    instance = FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=data_dir,
        url="http://example.test/",
        pm2_name="foundry-v13",
    )

    assert resolve_world_user_id(instance, "fvtt-cli-smoke", "Gamemaster") == "abc123"


def test_resolve_world_user_id_leaves_existing_internal_id_unchanged(tmp_path: Path):
    instance = FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=tmp_path / "data",
        url="http://example.test/",
        pm2_name="foundry-v13",
    )

    assert resolve_world_user_id(instance, "missing-world", "abc123") == "abc123"


def test_resolve_world_user_id_handles_whitespace_formatted_json(tmp_path: Path):
    data_dir = tmp_path / "data"
    users_dir = data_dir / "Data" / "worlds" / "fvtt-cli-smoke" / "data" / "users"
    users_dir.mkdir(parents=True)
    (users_dir / "000003.log").write_text(
        '!users!abc123\n{ "name" : "Gamemaster", "role" : 4, "_id" : "abc123" }\n',
        encoding="utf-8",
    )
    instance = FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=data_dir,
        url="http://example.test/",
        pm2_name="foundry-v13",
    )

    assert resolve_world_user_id(instance, "fvtt-cli-smoke", "Gamemaster") == "abc123"


def test_resolve_world_user_id_handles_leveldb_binary_record_fragments(tmp_path: Path):
    data_dir = tmp_path / "data"
    users_dir = data_dir / "Data" / "worlds" / "fvtt-cli-smoke" / "data" / "users"
    users_dir.mkdir(parents=True)
    (users_dir / "000005.ldb").write_bytes(
        b"\x88\x05!users!IjwbZWzwIJlbM29V\x01\x01\x00\x05"
        b'{"name":"Gamemaster","role":4,"_id":"\x00$","password":"x"}'
    )
    instance = FoundryInstance(
        version="v13",
        install_dir=tmp_path / "foundry",
        data_dir=data_dir,
        url="http://example.test/",
        pm2_name="foundry-v13",
    )

    assert resolve_world_user_id(instance, "fvtt-cli-smoke", "Gamemaster") == "IjwbZWzwIJlbM29V"
