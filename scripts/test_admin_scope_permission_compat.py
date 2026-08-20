from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import admin


class AdminScopePermissionCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.admin_user = {
            "username": "admin",
            "display_name": "平台管理员",
            "role": "admin",
            "active": True,
            "permissions": [],
            "manager_scope_keys": [],
            "scope_grants": [],
        }
        self.target_user = {
            "username": "operator",
            "display_name": "赛区运营",
            "role": "event_manager",
            "active": True,
            "permissions": ["match_manage", "guild_manage"],
            "manager_scope_keys": ["深圳市::jcds"],
            "scope_grants": [
                {
                    "scope_key": "深圳市::jcds",
                    "permissions": ["prediction_manage", "scope_audit_view"],
                    "is_scope_admin": False,
                }
            ],
            "scope_grants_authoritative": True,
        }
        self.users = [self.admin_user, self.target_user]
        self.data = {"matches": [], "players": [], "teams": []}
        self.catalog = [
            {
                "competition_name": "赛事A",
                "region_name": "深圳市",
                "series_slug": "jcds",
                "series_name": "赛事A",
            }
        ]

    def context(self, *, method="GET", form=None):
        return web_app.RequestContext(
            method=method,
            path="/permissions",
            query={"username": ["operator"]},
            form=form or {},
            files={},
            current_user=self.admin_user,
            now_label="2026-08-20 12:00:00 中国时间",
        )

    def test_legacy_page_shows_granular_grants_and_new_management_link(self):
        ctx = self.context()
        with (
            patch.object(admin, "load_users", return_value=self.users),
            patch.object(admin.legacy, "load_validated_data", return_value=self.data),
            patch.object(admin.legacy, "load_series_catalog", return_value=self.catalog),
            patch.object(admin, "layout", side_effect=lambda _title, body, _ctx, alert="": body),
        ):
            html = admin.get_permission_control_page(ctx)
        self.assertIn("赛区精细权限", html)
        self.assertIn("管理胜率预测", html)
        self.assertIn("查看赛区审计", html)
        self.assertIn("/console/accounts?edit_username=operator", html)
        self.assertNotIn('value="match_manage"', html)
        self.assertIn('value="guild_manage"', html)

    def test_legacy_post_rejects_event_permissions_and_scope_mutation(self):
        ctx = self.context(
            method="POST",
            form={
                "username": ["operator"],
                "permission_key": ["match_manage", "guild_manage"],
                "manager_scope_key": ["深圳市::jcds"],
            },
        )
        responses = []
        with (
            patch.object(admin, "require_admin", return_value=None),
            patch.object(admin, "load_users", return_value=self.users),
            patch.object(admin, "get_permission_control_page", return_value="rejected"),
            patch.object(admin, "save_users") as save_mock,
        ):
            admin.handle_permission_control(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )
        self.assertEqual(responses[0][0], "400 Bad Request")
        save_mock.assert_not_called()

    def test_global_permission_post_preserves_scope_grants(self):
        ctx = self.context(
            method="POST",
            form={
                "username": ["operator"],
                "permission_key": ["guild_manage"],
                "user_authorization_etag": [
                    admin.build_user_authorization_etag(self.target_user)
                ],
            },
        )
        responses = []
        saved_users = []
        with (
            patch.object(admin, "require_admin", return_value=None),
            patch.object(admin, "load_users", return_value=self.users),
            patch.object(admin, "validate_permission_assignment", return_value=""),
            patch.object(admin, "save_users", side_effect=lambda users: saved_users.extend(users)),
            patch.object(admin, "audit_action"),
            patch.object(admin, "get_permission_control_page", return_value="saved"),
        ):
            admin.handle_permission_control(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )
        self.assertEqual(responses[0][0], "200 OK")
        saved_target = next(user for user in saved_users if user["username"] == "operator")
        self.assertEqual(saved_target["permissions"], ["guild_manage"])
        self.assertEqual(saved_target["manager_scope_keys"], ["深圳市::jcds"])
        self.assertEqual(saved_target["scope_grants"], self.target_user["scope_grants"])

    def test_stale_global_permission_form_cannot_restore_downgraded_privilege(self):
        stale_etag = admin.build_user_authorization_etag(self.target_user)
        downgraded_target = {
            **self.target_user,
            "role": "member",
            "permissions": [],
        }
        ctx = self.context(
            method="POST",
            form={
                "username": ["operator"],
                "permission_key": ["player_binding_manage"],
                "user_authorization_etag": [stale_etag],
            },
        )
        responses = []
        with (
            patch.object(
                admin,
                "load_users",
                return_value=[self.admin_user, downgraded_target],
            ),
            patch.object(admin, "validate_permission_assignment", return_value=""),
            patch.object(admin, "save_users") as save_users,
            patch.object(admin, "get_permission_control_page", return_value="stale"),
        ):
            admin.handle_permission_control(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )

        self.assertEqual(responses[0][0], "409 Conflict")
        save_users.assert_not_called()

    def test_role_downgrade_clears_scoped_grants_and_revokes_sessions(self):
        ctx = self.context(
            method="POST",
            form={
                "action": ["update"],
                "editing_username": ["operator"],
                "display_name": ["普通成员"],
                "role": ["member"],
                "province_name": ["广东省"],
                "region_name": ["深圳市"],
                "password": [""],
            },
        )
        saved_users = []
        responses = []
        with (
            patch.object(admin, "load_users", return_value=self.users),
            patch.object(admin, "validate_account_update_form", return_value=""),
            patch.object(admin, "save_users", side_effect=lambda users: saved_users.extend(users)),
            patch.object(admin, "revoke_user_sessions") as revoke_sessions,
            patch.object(admin, "audit_action"),
            patch.object(admin, "get_accounts_page", return_value="saved"),
        ):
            admin.handle_accounts(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )

        self.assertEqual(responses[0][0], "200 OK")
        saved_target = next(user for user in saved_users if user["username"] == "operator")
        self.assertEqual(saved_target["role"], "member")
        self.assertEqual(saved_target["manager_scope_keys"], [])
        self.assertEqual(saved_target["scope_grants"], [])
        self.assertNotIn("player_binding_manage", saved_target["permissions"])
        self.assertEqual(
            saved_target["scope_grants_updated_by_username"],
            "admin",
        )
        revoke_sessions.assert_called_once_with("operator")

    def test_legacy_accounts_page_rejects_new_event_manager(self):
        ctx = self.context(
            method="POST",
            form={
                "action": ["create"],
                "username": ["unsafe-manager"],
                "display_name": ["未授权负责人"],
                "role": ["event_manager"],
                "province_name": ["广东省"],
                "region_name": ["深圳市"],
                "manager_scope_key": ["深圳市::jcds"],
                "password": ["Password123"],
            },
        )
        responses = []
        with (
            patch.object(admin, "load_users", return_value=self.users),
            patch.object(admin, "get_accounts_page", return_value="rejected"),
            patch.object(admin, "save_users") as save_users,
        ):
            admin.handle_accounts(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )

        self.assertEqual(responses[0][0], "400 Bad Request")
        save_users.assert_not_called()

    def test_concurrent_member_account_create_conflict_returns_409(self):
        ctx = self.context(
            method="POST",
            form={
                "action": ["create"],
                "username": ["racing-member"],
                "display_name": ["并发成员"],
                "role": ["member"],
                "province_name": ["广东省"],
                "region_name": ["深圳市"],
                "password": ["Password123"],
            },
        )
        responses = []
        with (
            patch.object(admin, "load_users", return_value=self.users),
            patch.object(admin, "validate_account_form", return_value=""),
            patch.object(admin, "hash_password", return_value=("salt", "hash")),
            patch.object(
                admin,
                "save_users",
                side_effect=admin.RepositoryConflictError(
                    "账号 racing-member 已存在，请刷新后重试。"
                ),
            ),
            patch.object(admin, "get_accounts_page", return_value="conflict"),
        ):
            admin.handle_accounts(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )

        self.assertEqual(responses[0][0], "409 Conflict")

    def test_stale_delete_returns_409_and_passes_actor_and_target_etags(self):
        target_etag = admin.build_user_authorization_etag(self.target_user)
        actor_etag = admin.build_user_authorization_etag(self.admin_user)
        ctx = self.context(
            method="POST",
            form={
                "action": ["delete"],
                "username": ["operator"],
                "delete_confirmation": ["operator"],
                "user_authorization_etag": [target_etag],
            },
        )
        responses = []
        with (
            patch.object(admin, "require_admin", return_value=None),
            patch.object(admin, "load_users", return_value=self.users),
            patch.object(
                admin,
                "delete_user_account",
                side_effect=admin.RepositoryConflictError(
                    "目标账号状态已发生变化，请刷新后重试。"
                ),
            ) as delete_account,
            patch.object(admin, "get_accounts_page", return_value="conflict"),
        ):
            admin.handle_accounts(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )

        self.assertEqual(responses[0][0], "409 Conflict")
        delete_account.assert_called_once_with(
            "operator",
            authorization_actor_username="admin",
            authorization_actor_etag=actor_etag,
            expected_user_authorization_etag=target_etag,
        )

    def test_accounts_page_includes_delete_target_authorization_etag(self):
        ctx = self.context()
        target_etag = admin.build_user_authorization_etag(self.target_user)
        with (
            patch.object(admin, "load_users", return_value=self.users),
            patch.object(admin.legacy, "load_validated_data", return_value=self.data),
            patch.object(admin.legacy, "load_series_catalog", return_value=self.catalog),
            patch.object(
                admin,
                "layout",
                side_effect=lambda _title, body, _ctx, alert="": body,
            ),
        ):
            html = admin.get_accounts_page(ctx)

        self.assertIn(
            f'name="user_authorization_etag" value="{target_etag}"',
            html,
        )


if __name__ == "__main__":
    unittest.main()
