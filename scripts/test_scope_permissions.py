import json
import tempfile
import unittest
from pathlib import Path

import sqlite_store
from web_authz import (
    SCOPE_PERMISSION_KEYS,
    get_scope_permission_preset,
    get_user_scope_grants,
    user_can_assign_scope_grant,
    user_can_manage_scoped_user_lifecycle,
    user_has_scope_permission,
    user_is_scope_admin,
)


SCOPE_A = "深圳::deep-league"
SCOPE_B = "北京::master-series"


def user_payload(username: str, **overrides):
    payload = {
        "username": username,
        "display_name": username,
        "password_salt": "salt",
        "password_hash": "hash",
        "active": True,
        "player_id": None,
        "linked_player_ids": [],
        "manager_scope_keys": [],
        "permissions": [],
        "role": "member",
        "account_create": True,
    }
    payload.update(overrides)
    return payload


class ScopePermissionAuthTests(unittest.TestCase):
    def test_legacy_match_permission_expands_for_each_manager_scope(self):
        user = user_payload(
            "legacy",
            manager_scope_keys=[SCOPE_A],
            permissions=["match_manage", "guild_manage"],
            role="event_manager",
        )

        grants = get_user_scope_grants(user)

        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["scope_key"], SCOPE_A)
        self.assertEqual(
            set(grants[0]["permissions"]),
            {
                "match_schedule_manage",
                "match_result_manage",
                "match_import_manage",
                "dimension_data_manage",
                "season_asset_manage",
                "prediction_manage",
                "scope_audit_view",
            },
        )
        self.assertTrue(user_has_scope_permission(user, SCOPE_A, "match_result_manage"))
        self.assertFalse(user_has_scope_permission(user, SCOPE_B, "match_result_manage"))

    def test_authoritative_empty_grants_do_not_fall_back_to_legacy_fields(self):
        user = user_payload(
            "revoked",
            role="event_manager",
            manager_scope_keys=[SCOPE_A],
            permissions=["match_manage"],
            scope_grants=[],
            scope_grants_authoritative=True,
        )

        self.assertEqual(get_user_scope_grants(user), [])
        self.assertFalse(user_has_scope_permission(user, SCOPE_A, "match_result_manage"))

    def test_non_event_manager_cannot_use_stale_explicit_grants(self):
        stale_member = user_payload(
            "stale-member",
            role="member",
            scope_grants=[
                {
                    "scope_key": SCOPE_A,
                    "permissions": ["match_result_manage"],
                    "is_scope_admin": True,
                }
            ],
            scope_grants_authoritative=True,
        )

        self.assertFalse(user_is_scope_admin(stale_member, SCOPE_A))
        self.assertFalse(
            user_has_scope_permission(
                stale_member,
                SCOPE_A,
                "match_result_manage",
            )
        )

    def test_scope_admin_and_platform_admin_are_distinct(self):
        scope_admin = user_payload(
            "scope-admin",
            role="event_manager",
            scope_grants=[
                {"scope_key": SCOPE_A, "permissions": [], "is_scope_admin": True}
            ],
            scope_grants_authoritative=True,
        )
        platform_admin = user_payload("admin", role="admin")

        self.assertTrue(user_is_scope_admin(scope_admin, SCOPE_A))
        self.assertTrue(
            user_has_scope_permission(scope_admin, SCOPE_A, "season_asset_manage")
        )
        self.assertFalse(user_is_scope_admin(scope_admin, SCOPE_B))
        self.assertTrue(user_is_scope_admin(platform_admin, SCOPE_B))

    def test_presets_cover_only_known_scope_permissions(self):
        self.assertEqual(set(get_scope_permission_preset("scope_admin")), set(SCOPE_PERMISSION_KEYS))
        self.assertEqual(
            get_scope_permission_preset("audit_viewer"),
            ["scope_audit_view"],
        )
        self.assertEqual(get_scope_permission_preset("unknown"), [])

    def test_scope_admin_can_delegate_permissions_but_not_admin_status(self):
        actor = user_payload(
            "owner",
            role="event_manager",
            scope_grants=[
                {"scope_key": SCOPE_A, "permissions": [], "is_scope_admin": True}
            ],
            scope_grants_authoritative=True,
        )

        self.assertTrue(
            user_can_assign_scope_grant(actor, SCOPE_A, ["match_result_manage"])
        )
        self.assertFalse(
            user_can_assign_scope_grant(
                actor,
                SCOPE_A,
                ["match_result_manage"],
                is_scope_admin=True,
            )
        )
        self.assertFalse(
            user_can_assign_scope_grant(actor, SCOPE_B, ["match_result_manage"])
        )

    def test_scope_admin_lifecycle_control_rejects_shared_accounts(self):
        actor = user_payload(
            "owner",
            role="event_manager",
            scope_grants=[
                {"scope_key": SCOPE_A, "permissions": [], "is_scope_admin": True}
            ],
            scope_grants_authoritative=True,
        )
        child = user_payload(
            "child",
            role="event_manager",
            created_by_username="owner",
            scope_grants=[
                {
                    "scope_key": SCOPE_A,
                    "permissions": ["match_result_manage"],
                    "is_scope_admin": False,
                }
            ],
            scope_grants_authoritative=True,
        )
        shared_child = {
            **child,
            "scope_grants": [
                *child["scope_grants"],
                {
                    "scope_key": SCOPE_B,
                    "permissions": ["scope_audit_view"],
                    "is_scope_admin": False,
                },
            ],
        }
        promoted_child = {
            **child,
            "scope_grants": [
                {"scope_key": SCOPE_A, "permissions": [], "is_scope_admin": True}
            ],
        }

        self.assertTrue(user_can_manage_scoped_user_lifecycle(actor, child))
        self.assertFalse(user_can_manage_scoped_user_lifecycle(actor, shared_child))
        self.assertFalse(user_can_manage_scoped_user_lifecycle(actor, promoted_child))


class ScopePermissionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = sqlite_store.DB_PATH
        sqlite_store.DB_PATH = Path(self.temp_dir.name) / "scope-permissions.db"
        sqlite_store.ensure_database()
        with sqlite_store.connect_db() as connection:
            connection.execute(
                """
                INSERT INTO app_meta(meta_key, meta_value)
                VALUES ('initialized', '1')
                ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                """
            )

    def tearDown(self):
        sqlite_store.DB_PATH = self.previous_db_path
        self.temp_dir.cleanup()

    def test_schema_migration_backfills_legacy_grants_and_keeps_global_permissions(self):
        with sqlite_store.connect_db() as connection:
            connection.execute(
                "UPDATE app_meta SET meta_value = '6' WHERE meta_key = ?",
                (sqlite_store.SCHEMA_VERSION_META_KEY,),
            )
            connection.execute(
                """
                INSERT INTO users (
                    username, display_name, password_salt, password_hash, active,
                    manager_scope_keys_json, permissions_json, role, created_by_username
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy",
                    "Legacy",
                    "salt",
                    "hash",
                    1,
                    json.dumps([SCOPE_A], ensure_ascii=False),
                    json.dumps(["match_manage", "guild_manage"], ensure_ascii=False),
                    "event_manager",
                    "admin",
                ),
            )

        sqlite_store.ensure_database()
        loaded = sqlite_store.load_users()[0]

        self.assertEqual(loaded["created_by_username"], "admin")
        self.assertEqual(loaded["permissions"], ["match_manage", "guild_manage"])
        self.assertTrue(loaded["scope_grants_authoritative"])
        self.assertTrue(
            user_has_scope_permission(loaded, SCOPE_A, "dimension_data_manage")
        )
        self.assertEqual(
            loaded["scope_grants"][0]["updated_by_username"],
            "system:legacy-migration",
        )

    def test_replace_grants_tracks_updater_and_revocation_survives_schema_ensure(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "operator",
                    role="event_manager",
                    created_by_username="admin",
                )
            ]
        )

        saved = sqlite_store.save_user_scope_grants(
            "operator",
            [
                {
                    "scope_key": SCOPE_A,
                    "permissions": ["match_result_manage", "scope_audit_view"],
                    "is_scope_admin": False,
                }
            ],
            updated_by_username="admin",
        )

        self.assertEqual(saved[0]["updated_by_username"], "admin")
        self.assertTrue(saved[0]["created_at"])
        self.assertTrue(saved[0]["updated_at"])
        loaded = sqlite_store.load_users()[0]
        self.assertEqual(loaded["manager_scope_keys"], [SCOPE_A])
        self.assertTrue(user_has_scope_permission(loaded, SCOPE_A, "scope_audit_view"))

        sqlite_store.save_user_scope_grants(
            "operator", [], updated_by_username="admin"
        )
        sqlite_store.ensure_database()
        revoked = sqlite_store.load_users()[0]
        self.assertEqual(revoked["manager_scope_keys"], [])
        self.assertEqual(revoked["scope_grants"], [])

    def test_invalid_grant_is_rejected_without_partial_write(self):
        sqlite_store.save_users([user_payload("operator")])

        with self.assertRaises(ValueError):
            sqlite_store.save_user_scope_grants(
                "operator",
                [
                    {
                        "scope_key": SCOPE_A,
                        "permissions": ["not-a-real-permission"],
                        "is_scope_admin": False,
                    }
                ],
                updated_by_username="admin",
            )

        self.assertEqual(sqlite_store.load_user_scope_grants(username="operator"), [])

    def test_scoped_child_does_not_receive_legacy_global_defaults(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "scoped-child",
                    role="event_manager",
                    permissions=[],
                    manager_scope_keys=[SCOPE_A],
                    scope_grants=[
                        {
                            "scope_key": SCOPE_A,
                            "permissions": ["match_result_manage"],
                            "is_scope_admin": False,
                        }
                    ],
                    scope_grants_authoritative=True,
                    scope_grants_updated_by_username="admin",
                )
            ]
        )

        sqlite_store.ensure_database()
        loaded = sqlite_store.load_users()[0]

        self.assertEqual(loaded["permissions"], [])
        self.assertTrue(
            user_has_scope_permission(loaded, SCOPE_A, "match_result_manage")
        )

    def test_targeted_user_delete_also_removes_scope_grants(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "to-delete",
                    role="event_manager",
                    scope_grants=[
                        {
                            "scope_key": SCOPE_A,
                            "permissions": ["scope_audit_view"],
                            "is_scope_admin": False,
                        }
                    ],
                    scope_grants_authoritative=True,
                    scope_grants_updated_by_username="admin",
                )
            ]
        )
        self.assertTrue(
            sqlite_store.load_user_scope_grants(username="to-delete")
        )

        self.assertTrue(sqlite_store.delete_user_account("to-delete"))

        self.assertEqual(
            sqlite_store.load_user_scope_grants(username="to-delete"),
            [],
        )

    def test_deleted_username_cannot_be_reused(self):
        sqlite_store.save_users([user_payload("retired-user")])
        self.assertTrue(sqlite_store.delete_user_account("retired-user"))

        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_users([user_payload("retired-user")])

        self.assertNotIn(
            "retired-user",
            {user["username"] for user in sqlite_store.load_users()},
        )

    def test_user_delete_is_blocked_while_guild_identity_exists(self):
        sqlite_store.save_users([user_payload("guild-leader")])
        with sqlite_store.connect_db() as connection:
            connection.execute(
                """
                INSERT INTO guilds (
                    guild_id, name, short_name, logo, active, founded_on,
                    leader_username, manager_usernames_json, honors_json, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "guild-one",
                    "测试俱乐部",
                    "测试",
                    "assets/guilds/default.svg",
                    1,
                    "2026-08-20",
                    "guild-leader",
                    "[]",
                    "[]",
                    "",
                ),
            )

        with self.assertRaisesRegex(
            sqlite_store.RepositoryConflictError,
            "请先移交",
        ):
            sqlite_store.delete_user_account("guild-leader")

        self.assertIn(
            "guild-leader",
            {user["username"] for user in sqlite_store.load_users()},
        )

    def test_revoked_actor_cannot_finish_stale_account_delete(self):
        sqlite_store.save_users(
            [
                user_payload("operator", role="admin"),
                user_payload("delete-target"),
            ]
        )
        users = sqlite_store.load_users()
        actor = next(user for user in users if user["username"] == "operator")
        target = next(
            user for user in users if user["username"] == "delete-target"
        )
        stale_actor_etag = sqlite_store.build_user_authorization_etag(actor)
        target_etag = sqlite_store.build_user_authorization_etag(target)

        actor.update(
            {
                "role": "member",
                "account_role_write": True,
            }
        )
        sqlite_store.save_users([actor])

        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.delete_user_account(
                "delete-target",
                authorization_actor_username="operator",
                authorization_actor_etag=stale_actor_etag,
                expected_user_authorization_etag=target_etag,
            )

        self.assertIn(
            "delete-target",
            {user["username"] for user in sqlite_store.load_users()},
        )

    def test_promoted_target_cannot_be_deleted_by_stale_request(self):
        sqlite_store.save_users(
            [
                user_payload("operator", role="admin"),
                user_payload("delete-target"),
            ]
        )
        users = sqlite_store.load_users()
        actor = next(user for user in users if user["username"] == "operator")
        target = next(
            user for user in users if user["username"] == "delete-target"
        )
        actor_etag = sqlite_store.build_user_authorization_etag(actor)
        stale_target_etag = sqlite_store.build_user_authorization_etag(target)

        target.update(
            {
                "role": "admin",
                "account_role_write": True,
            }
        )
        sqlite_store.save_users([target])

        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.delete_user_account(
                "delete-target",
                authorization_actor_username="operator",
                authorization_actor_etag=actor_etag,
                expected_user_authorization_etag=stale_target_etag,
            )

        loaded_target = next(
            user
            for user in sqlite_store.load_users()
            if user["username"] == "delete-target"
        )
        self.assertEqual(loaded_target["role"], "admin")

    def test_stale_profile_save_cannot_restore_revoked_scope_grants(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "operator",
                    role="event_manager",
                    scope_grants=[
                        {
                            "scope_key": SCOPE_A,
                            "permissions": ["match_result_manage"],
                            "is_scope_admin": False,
                        }
                    ],
                    scope_grants_authoritative=True,
                    scope_grants_updated_by_username="admin",
                )
            ]
        )
        stale_users = sqlite_store.load_users()

        sqlite_store.save_user_scope_grants(
            "operator", [], updated_by_username="admin"
        )
        stale_users[0]["display_name"] = "并发更新后的显示名"
        stale_users[0]["user_profile_write"] = True
        sqlite_store.save_users(stale_users)

        loaded = sqlite_store.load_users()[0]
        self.assertEqual(loaded["display_name"], "并发更新后的显示名")
        self.assertEqual(loaded["manager_scope_keys"], [])
        self.assertEqual(loaded["scope_grants"], [])

    def test_initial_v7_import_preserves_explicit_scoped_account_without_legacy_defaults(self):
        initial_db_path = Path(self.temp_dir.name) / "initial-v7.db"
        sqlite_store.DB_PATH = initial_db_path
        with sqlite_store.connect_db() as connection:
            sqlite_store.create_schema(connection)
            sqlite_store.replace_repository_data(
                connection,
                teams=[],
                players=[],
                matches=[],
                guilds=[],
                users=[
                    user_payload(
                        "scoped-import",
                        role="event_manager",
                        manager_scope_keys=[SCOPE_A],
                        permissions=[],
                        scope_grants=[
                            {
                                "scope_key": SCOPE_A,
                                "permissions": ["match_result_manage"],
                                "is_scope_admin": False,
                            }
                        ],
                        scope_grants_authoritative=True,
                    )
                ],
            )

        loaded = sqlite_store.load_users()[0]
        self.assertEqual(loaded["permissions"], [])
        self.assertEqual(loaded["manager_scope_keys"], [SCOPE_A])
        self.assertEqual(
            loaded["scope_grants"][0]["permissions"],
            ["match_result_manage"],
        )

    def test_v7_runtime_does_not_auto_expand_new_empty_event_manager(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "empty-manager",
                    role="event_manager",
                    manager_scope_keys=[SCOPE_A],
                    permissions=[],
                )
            ]
        )

        sqlite_store.ensure_database()
        loaded = sqlite_store.load_users()[0]
        self.assertEqual(loaded["permissions"], [])
        self.assertEqual(loaded["manager_scope_keys"], [])
        self.assertEqual(loaded["scope_grants"], [])

    def test_stale_profile_save_cannot_restore_deactivated_role_or_credentials(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "operator",
                    role="event_manager",
                    permissions=["player_binding_manage"],
                    password_salt="old-salt",
                    password_hash="old-hash",
                )
            ]
        )
        stale_users = sqlite_store.load_users()
        secured_user = {
            **stale_users[0],
            "active": False,
            "role": "member",
            "permissions": [],
            "password_salt": "new-salt",
            "password_hash": "new-hash",
            "account_auth_updated_by_username": "admin",
        }
        sqlite_store.save_users([secured_user])

        stale_users[0]["display_name"] = "迟到的资料更新"
        stale_users[0]["user_profile_write"] = True
        sqlite_store.save_users(stale_users)

        loaded = sqlite_store.load_users()[0]
        self.assertEqual(loaded["display_name"], "迟到的资料更新")
        self.assertFalse(loaded["active"])
        self.assertEqual(loaded["role"], "member")
        self.assertEqual(loaded["permissions"], [])
        self.assertEqual(loaded["password_salt"], "new-salt")
        self.assertEqual(loaded["password_hash"], "new-hash")

    def test_stale_password_reset_cannot_restore_role_active_or_permissions(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "operator",
                    role="event_manager",
                    permissions=["player_binding_manage"],
                )
            ]
        )
        stale_user = sqlite_store.load_users()[0]
        secured_user = {
            **stale_user,
            "active": False,
            "role": "member",
            "permissions": [],
            "account_active_write": True,
            "account_role_write": True,
            "account_permissions_write": True,
        }
        sqlite_store.save_users([secured_user])

        stale_user["password_salt"] = "reset-salt"
        stale_user["password_hash"] = "reset-hash"
        stale_user["account_password_write"] = True
        sqlite_store.save_users([stale_user])

        loaded = sqlite_store.load_users()[0]
        self.assertFalse(loaded["active"])
        self.assertEqual(loaded["role"], "member")
        self.assertEqual(loaded["permissions"], [])
        self.assertEqual(loaded["password_salt"], "reset-salt")
        self.assertEqual(loaded["password_hash"], "reset-hash")

    def test_stale_profile_save_cannot_restore_bindings_or_wechat_identity(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "operator",
                    player_id="player-old",
                    linked_player_ids=["player-linked"],
                    wechat_unionid="union-old",
                )
            ]
        )
        stale_user = sqlite_store.load_users()[0]
        secured_user = {
            **stale_user,
            "player_id": None,
            "linked_player_ids": [],
            "wechat_unionid": "union-new",
            "user_player_bindings_write": True,
            "user_wechat_identity_write": True,
        }
        sqlite_store.save_users([secured_user])

        stale_user["display_name"] = "迟到的资料更新"
        stale_user["user_profile_write"] = True
        sqlite_store.save_users([stale_user])

        loaded = sqlite_store.load_users()[0]
        self.assertEqual(loaded["display_name"], "迟到的资料更新")
        self.assertIsNone(loaded["player_id"])
        self.assertEqual(loaded["linked_player_ids"], [])
        self.assertEqual(loaded["wechat_unionid"], "union-new")

    def test_stale_user_snapshot_cannot_reinsert_deleted_or_remove_new_account(self):
        sqlite_store.save_users(
            [user_payload("admin", role="admin"), user_payload("victim")]
        )
        stale_users = sqlite_store.load_users()

        self.assertTrue(sqlite_store.delete_user_account("victim"))
        sqlite_store.save_users([*sqlite_store.load_users(), user_payload("new-user")])

        stale_victim = next(user for user in stale_users if user["username"] == "victim")
        stale_victim["display_name"] = "不应复活"
        stale_victim["user_profile_write"] = True
        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_users(stale_users)

        usernames = {user["username"] for user in sqlite_store.load_users()}
        self.assertNotIn("victim", usernames)
        self.assertIn("new-user", usernames)

    def test_scope_grant_etag_rejects_stale_permission_restore(self):
        sqlite_store.save_users([user_payload("operator", role="event_manager")])
        sqlite_store.save_user_scope_grants(
            "operator",
            [
                {
                    "scope_key": SCOPE_A,
                    "permissions": ["match_result_manage"],
                    "is_scope_admin": False,
                }
            ],
            updated_by_username="admin",
        )
        stale_etag = sqlite_store.get_user_scope_grants_etag("operator")

        sqlite_store.save_user_scope_grants(
            "operator", [], updated_by_username="admin"
        )
        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_user_scope_grants(
                "operator",
                [
                    {
                        "scope_key": SCOPE_A,
                        "permissions": ["match_result_manage"],
                        "is_scope_admin": False,
                    }
                ],
                updated_by_username="other-admin",
                expected_etag=stale_etag,
            )

        self.assertEqual(
            sqlite_store.load_user_scope_grants(username="operator"), []
        )

    def test_revoked_actor_cannot_finish_stale_scoped_account_write(self):
        sqlite_store.save_users(
            [
                user_payload("owner", role="event_manager"),
                user_payload(
                    "child",
                    role="event_manager",
                    created_by_username="owner",
                ),
            ]
        )
        sqlite_store.save_user_scope_grants(
            "owner",
            [
                {
                    "scope_key": SCOPE_A,
                    "permissions": [],
                    "is_scope_admin": True,
                }
            ],
            updated_by_username="admin",
        )
        owner = next(
            user for user in sqlite_store.load_users()
            if user["username"] == "owner"
        )
        stale_actor_etag = sqlite_store.build_user_authorization_etag(owner)

        sqlite_store.save_user_scope_grants(
            "owner",
            [],
            updated_by_username="admin",
        )
        child = next(
            user for user in sqlite_store.load_users()
            if user["username"] == "child"
        )
        child.update(
            {
                "active": False,
                "account_active_write": True,
                "authorization_actor_username": "owner",
                "authorization_actor_etag": stale_actor_etag,
            }
        )

        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_users([child])

        loaded_child = next(
            user for user in sqlite_store.load_users()
            if user["username"] == "child"
        )
        self.assertTrue(loaded_child["active"])

    def test_target_authorization_etag_rejects_stale_global_permission_write(self):
        sqlite_store.save_users(
            [
                user_payload(
                    "operator",
                    role="event_manager",
                    permissions=["player_binding_manage"],
                )
            ]
        )
        stale_user = sqlite_store.load_users()[0]
        stale_etag = sqlite_store.build_user_authorization_etag(stale_user)
        downgraded_user = {
            **stale_user,
            "role": "member",
            "permissions": [],
            "account_role_write": True,
            "account_permissions_write": True,
        }
        sqlite_store.save_users([downgraded_user])

        stale_user["permissions"] = ["player_binding_manage"]
        stale_user["account_permissions_write"] = True
        stale_user["expected_user_authorization_etag"] = stale_etag
        with self.assertRaises(sqlite_store.RepositoryConflictError):
            sqlite_store.save_users([stale_user])

        loaded = sqlite_store.load_users()[0]
        self.assertEqual(loaded["role"], "member")
        self.assertEqual(loaded["permissions"], [])

    def test_scope_admin_flag_rejects_string_values(self):
        sqlite_store.save_users([user_payload("operator", role="event_manager")])

        with self.assertRaises(ValueError):
            sqlite_store.save_user_scope_grants(
                "operator",
                [
                    {
                        "scope_key": SCOPE_A,
                        "permissions": [],
                        "is_scope_admin": "0",
                    }
                ],
                updated_by_username="admin",
            )


if __name__ == "__main__":
    unittest.main()
