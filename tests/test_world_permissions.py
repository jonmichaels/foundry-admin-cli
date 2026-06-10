import pytest

from foundry_admin_cli.config import FoundryInstance
from foundry_admin_cli.world_permissions import (
    PermissionManagementError,
    audit_permissions,
    export_permissions,
    normalize_ownership_level,
    set_document_permission,
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
    def __init__(self, *, world="module-test", users=None, actors=None, journals=None, scenes=None, response=None):
        self.world = world
        self.users = users if users is not None else [
            {"_id": "gm-id", "name": "Gamemaster", "role": 4},
            {"_id": "player-id", "name": "Player One", "role": 1},
        ]
        self.actors = actors if actors is not None else [
            {"_id": "actor-id", "name": "Hero", "ownership": {"default": 0, "player-id": 3}},
        ]
        self.journals = journals if journals is not None else [
            {"_id": "journal-id", "name": "Quest Log", "ownership": {"default": 0}},
        ]
        self.scenes = scenes if scenes is not None else [
            {"_id": "scene-id", "name": "Dungeon", "ownership": {"default": 0}},
        ]
        self.response = response or {"result": [{"_id": "journal-id", "ownership": {"default": 0, "player-id": 2}}]}
        self.requests = []

    def get_world_data(self, instance):
        return {
            "world": {"id": self.world},
            "users": self.users,
            "actors": self.actors,
            "journal": self.journals,
            "scenes": self.scenes,
        }

    def modify_document(self, instance, *, document_type, updates):
        self.requests.append({"document_type": document_type, "updates": updates})
        return self.response


def test_normalize_ownership_level_accepts_labels_aliases_and_numbers():
    assert normalize_ownership_level("none") == ("None", "NONE", 0)
    assert normalize_ownership_level("limited") == ("Limited", "LIMITED", 1)
    assert normalize_ownership_level("observer") == ("Observer", "OBSERVER", 2)
    assert normalize_ownership_level("owner") == ("Owner", "OWNER", 3)
    assert normalize_ownership_level("3") == ("Owner", "OWNER", 3)


def test_normalize_ownership_level_rejects_unknown_level():
    with pytest.raises(PermissionManagementError, match="unknown ownership level"):
        normalize_ownership_level("gm")


def test_audit_permissions_resolves_user_names_and_document_ownership(tmp_path):
    result = audit_permissions(instance(tmp_path), "module-test", transport=FakeTransport())

    assert result["world"] == "module-test"
    assert result["documents"]["actor"] == [
        {
            "id": "actor-id",
            "name": "Hero",
            "type": "actor",
            "ownership": {
                "default": {"level": "None", "level_key": "NONE", "level_value": 0},
                "player-id": {"user": "Player One", "level": "Owner", "level_key": "OWNER", "level_value": 3},
            },
        }
    ]


def test_export_permissions_matches_audit_shape_and_can_filter_type(tmp_path):
    result = export_permissions(instance(tmp_path), "module-test", document_type="journal", transport=FakeTransport())

    assert result["export_version"] == 1
    assert list(result["documents"].keys()) == ["journal"]
    assert result["documents"]["journal"][0]["name"] == "Quest Log"


def test_set_document_permission_updates_ownership_for_resolved_user_and_document(tmp_path):
    transport = FakeTransport()

    result = set_document_permission(
        instance(tmp_path),
        "module-test",
        document_type="journal",
        document="Quest Log",
        user="Player One",
        level="observer",
        transport=transport,
    )

    assert result["changed"] is True
    assert result["document"]["id"] == "journal-id"
    assert result["user"] == {"id": "player-id", "name": "Player One"}
    assert transport.requests == [
        {
            "document_type": "JournalEntry",
            "updates": [{"_id": "journal-id", "ownership": {"default": 0, "player-id": 2}}],
        }
    ]


def test_set_document_permission_supports_default_ownership(tmp_path):
    transport = FakeTransport()

    result = set_document_permission(
        instance(tmp_path),
        "module-test",
        document_type="scene",
        document="scene-id",
        user="default",
        level="limited",
        transport=transport,
    )

    assert result["user"] == {"id": "default", "name": "default"}
    assert transport.requests[0]["updates"] == [{"_id": "scene-id", "ownership": {"default": 1}}]


def test_set_document_permission_noops_when_level_is_already_set(tmp_path):
    transport = FakeTransport()

    result = set_document_permission(
        instance(tmp_path),
        "module-test",
        document_type="actor",
        document="Hero",
        user="Player One",
        level="owner",
        transport=transport,
    )

    assert result["changed"] is False
    assert transport.requests == []


def test_set_document_permission_rejects_ambiguous_document_name(tmp_path):
    transport = FakeTransport(journals=[
        {"_id": "one", "name": "Quest Log", "ownership": {}},
        {"_id": "two", "name": "Quest Log", "ownership": {}},
    ])

    with pytest.raises(PermissionManagementError, match="ambiguous journal"):
        set_document_permission(
            instance(tmp_path),
            "module-test",
            document_type="journal",
            document="Quest Log",
            user="Player One",
            level="observer",
            transport=transport,
        )


def test_permission_commands_require_local_instance(tmp_path):
    with pytest.raises(Exception, match="requires local"):
        audit_permissions(instance(tmp_path, mode="http-only"), "module-test", transport=FakeTransport())
