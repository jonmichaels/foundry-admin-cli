import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.world_users import (
    UserManagementError,
    create_game_user,
    delete_game_user,
    disable_game_user,
    list_game_users,
    normalize_user_role,
    set_game_user_password,
    set_game_user_role,
)


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
    def __init__(self, *, world="module-test", users=None, response=None):
        self.world = world
        self.users = users if users is not None else [
            {"_id": "gm-id", "name": "Gamemaster", "role": 4, "active": True},
            {"_id": "player-id", "name": "Player One", "role": 1, "active": True},
        ]
        self.response = response or {"result": [{"_id": "new-id", "name": "Scout", "role": 1}]}
        self.requests = []

    def get_world_data(self, instance):
        return {"world": {"id": self.world}, "users": self.users}

    def modify_user(self, instance, *, action, data=None, updates=None, ids=None):
        self.requests.append({"action": action, "data": data, "updates": updates, "ids": ids})
        return self.response


def test_normalize_user_roles_accepts_foundry_labels_and_aliases():
    assert normalize_user_role("None") == ("None", "NONE", 0)
    assert normalize_user_role("Player") == ("Player", "PLAYER", 1)
    assert normalize_user_role("Trusted Player") == ("Trusted Player", "TRUSTED", 2)
    assert normalize_user_role("assistant-gm") == ("Assistant Gamemaster", "ASSISTANT", 3)
    assert normalize_user_role("gm") == ("Gamemaster", "GAMEMASTER", 4)


def test_normalize_user_role_rejects_unknown_role():
    with pytest.raises(UserManagementError, match="unknown role"):
        normalize_user_role("owner")


def test_list_game_users_reports_roles(tmp_path):
    result = list_game_users(instance(tmp_path), "module-test", transport=FakeTransport())

    assert result["world"] == "module-test"
    assert result["users"] == [
        {"id": "gm-id", "name": "Gamemaster", "role": "Gamemaster", "role_key": "GAMEMASTER", "role_value": 4, "active": True},
        {"id": "player-id", "name": "Player One", "role": "Player", "role_key": "PLAYER", "role_value": 1, "active": True},
    ]


def test_create_game_user_rejects_duplicate_name(tmp_path):
    with pytest.raises(UserManagementError, match="already exists"):
        create_game_user(instance(tmp_path), "module-test", name="Gamemaster", role="Player", transport=FakeTransport())


def test_create_game_user_sends_role_and_optional_password(tmp_path):
    transport = FakeTransport(response={"result": [{"_id": "new-id", "name": "Scout", "role": 2}]})

    result = create_game_user(instance(tmp_path), "module-test", name="Scout", role="Trusted Player", password="pw", transport=transport)

    assert result["created"] is True
    assert result["user"]["role_key"] == "TRUSTED"
    assert transport.requests == [{"action": "create", "data": [{"name": "Scout", "role": 2, "password": "pw"}], "updates": None, "ids": None}]


def test_set_game_user_role_keeps_at_least_one_gamemaster(tmp_path):
    with pytest.raises(UserManagementError, match="at least one Gamemaster"):
        set_game_user_role(instance(tmp_path), "module-test", "gm-id", "Player", transport=FakeTransport(users=[{"_id": "gm-id", "name": "Gamemaster", "role": 4}]))


def test_set_game_user_role_updates_user(tmp_path):
    transport = FakeTransport(response={"result": [{"_id": "player-id", "role": 3}]})

    result = set_game_user_role(instance(tmp_path), "module-test", "player-id", "Assistant Gamemaster", transport=transport)

    assert result["updated"] is True
    assert result["user"]["name"] == "Player One"
    assert result["user"]["role_key"] == "ASSISTANT"
    assert transport.requests == [{"action": "update", "data": None, "updates": [{"_id": "player-id", "role": 3}], "ids": None}]


def test_set_game_user_role_rejects_ambiguous_user_name(tmp_path):
    users = [
        {"_id": "gm-id", "name": "Gamemaster", "role": 4},
        {"_id": "one", "name": "Alex", "role": 1},
        {"_id": "two", "name": "Alex", "role": 1},
    ]

    with pytest.raises(UserManagementError, match="ambiguous user"):
        set_game_user_role(instance(tmp_path), "module-test", "Alex", "Trusted Player", transport=FakeTransport(users=users))


def test_set_game_user_role_reports_malformed_role_payload(tmp_path):
    users = [
        {"_id": "gm-id", "name": "Gamemaster", "role": 4},
        {"_id": "player-id", "name": "Player One", "role": "bad"},
    ]

    with pytest.raises(UserManagementError, match="invalid Foundry user role value"):
        set_game_user_role(instance(tmp_path), "module-test", "player-id", "Trusted Player", transport=FakeTransport(users=users))


def test_set_game_user_password_reads_secret_outside_result(tmp_path):
    transport = FakeTransport(response={"result": [{"_id": "player-id", "name": "Player One", "role": 1}]})

    result = set_game_user_password(instance(tmp_path), "module-test", "player-id", "secret-value", transport=transport)

    assert result["password_changed"] is True
    assert "secret-value" not in str(result)
    assert transport.requests == [{"action": "update", "data": None, "updates": [{"_id": "player-id", "password": "secret-value"}], "ids": None}]


def test_disable_game_user_sets_none_role(tmp_path):
    transport = FakeTransport(response={"result": [{"_id": "player-id", "name": "Player One", "role": 0}]})

    result = disable_game_user(instance(tmp_path), "module-test", "player-id", transport=transport)

    assert result["user"]["role_key"] == "NONE"
    assert transport.requests == [{"action": "update", "data": None, "updates": [{"_id": "player-id", "role": 0}], "ids": None}]


def test_delete_game_user_requires_force(tmp_path):
    with pytest.raises(UserManagementError, match="requires --force"):
        delete_game_user(instance(tmp_path), "module-test", "player-id", force=False, transport=FakeTransport())


def test_delete_game_user_refuses_last_gamemaster(tmp_path):
    with pytest.raises(UserManagementError, match="at least one Gamemaster"):
        delete_game_user(instance(tmp_path), "module-test", "gm-id", force=True, transport=FakeTransport(users=[{"_id": "gm-id", "name": "Gamemaster", "role": 4}]))


def test_delete_game_user_deletes_by_id(tmp_path):
    transport = FakeTransport(response={"result": ["player-id"]})

    result = delete_game_user(instance(tmp_path), "module-test", "player-id", force=True, transport=transport)

    assert result["deleted"] is True
    assert result["user"] == "player-id"
    assert transport.requests == [{"action": "delete", "data": None, "updates": None, "ids": ["player-id"]}]


def test_game_user_commands_require_local_instance(tmp_path):
    with pytest.raises(Exception, match="requires local"):
        list_game_users(instance(tmp_path, mode="http-only"), "module-test", transport=FakeTransport())
