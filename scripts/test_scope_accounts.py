import unittest
from unittest.mock import patch

from web.features import scope_accounts


SCOPE_A = "深圳::deep-league"
SCOPE_B = "北京::master-series"


def make_user(username: str, **overrides):
    user = {
        "username": username,
        "display_name": username,
        "password_salt": "salt",
        "password_hash": "hash",
        "active": True,
        "player_id": None,
        "linked_player_ids": [],
        "manager_scope_keys": [],
        "permissions": [],
        "role": "event_manager",
        "created_by_username": "",
        "scope_grants": [],
        "scope_grants_authoritative": True,
    }
    user.update(overrides)
    return user


def make_context(actor, *, method="POST", form=None, query=None):
    return scope_accounts.RequestContext(
        method=method,
        path="/console/accounts",
        query=query or {},
        form=form or {},
        files={},
        current_user=actor,
        now_label="now",
        session_token="test-session",
    )


def scope_option(scope_key: str, label: str):
    return {"scope_key": scope_key, "label": label, "competition_name": label}


class ScopeAccountsRouteTests(unittest.TestCase):
    def setUp(self):
        self.scope_options = [
            scope_option(SCOPE_A, "深圳 · 深大联赛"),
            scope_option(SCOPE_B, "北京 · 京城大师赛"),
        ]
        self.owner = make_user(
            "owner",
            created_by_username="admin",
            scope_grants=[
                {"scope_key": SCOPE_A, "permissions": [], "is_scope_admin": True}
            ],
        )
        self.admin = make_user("admin", role="admin")
        self.child = make_user(
            "child",
            created_by_username="owner",
            manager_scope_keys=[SCOPE_A],
            scope_grants=[
                {
                    "scope_key": SCOPE_A,
                    "permissions": ["match_result_manage"],
                    "is_scope_admin": False,
                }
            ],
        )

    def run_route(self, ctx, users, *, save_side_effect=None):
        response_status = []

        def start_response(status, _headers):
            response_status.append(status)

        patches = [
            patch.object(scope_accounts, "_catalog_scope_options", return_value=self.scope_options),
            patch.object(scope_accounts, "load_users", return_value=users),
            patch.object(scope_accounts, "layout", side_effect=lambda _title, body, _ctx, alert="": alert + body),
            patch.object(scope_accounts, "audit_action"),
            patch.object(scope_accounts, "hash_password", return_value=("new-salt", "new-hash")),
            patch.object(scope_accounts, "save_users"),
            patch.object(scope_accounts, "revoke_user_sessions"),
        ]
        entered = [item.start() for item in patches]
        try:
            entered[5].side_effect = save_side_effect
            body = b"".join(scope_accounts.handle_scope_accounts_route(ctx, start_response)).decode()
            return response_status[0], body, entered[5], entered[6]
        finally:
            for item in reversed(patches):
                item.stop()

    def test_scope_admin_creates_owned_event_manager_from_preset(self):
        ctx = make_context(
            self.owner,
            form={
                "action": ["create"],
                "username": ["new_operator"],
                "display_name": ["新运营"],
                "password": ["secret1"],
                "scope_key": [SCOPE_A],
                "preset": ["event_editor"],
            },
        )

        status, _body, save_users_mock, _revoke_mock = self.run_route(
            ctx, [self.owner, self.child]
        )

        self.assertEqual(status, "200 OK")
        saved_users = save_users_mock.call_args.args[0]
        created = next(user for user in saved_users if user["username"] == "new_operator")
        self.assertEqual(created["role"], "event_manager")
        self.assertEqual(created["created_by_username"], "owner")
        self.assertEqual(created["manager_scope_keys"], [SCOPE_A])
        self.assertEqual(
            created["scope_grants"][0]["permissions"],
            ["match_schedule_manage", "match_result_manage", "prediction_manage"],
        )
        self.assertFalse(created["scope_grants"][0]["is_scope_admin"])

    def test_concurrent_account_create_conflict_returns_409(self):
        ctx = make_context(
            self.owner,
            form={
                "action": ["create"],
                "username": ["racing_operator"],
                "display_name": ["并发运营"],
                "password": ["secret1"],
                "scope_key": [SCOPE_A],
                "preset": ["event_editor"],
            },
        )

        status, body, _save_users_mock, _revoke_mock = self.run_route(
            ctx,
            [self.owner, self.child],
            save_side_effect=scope_accounts.RepositoryConflictError(
                "账号 racing_operator 已存在，请刷新后重试。"
            ),
        )

        self.assertEqual(status, "409 Conflict")
        self.assertIn("已存在", body)

    def test_scope_admin_cannot_create_another_scope_admin(self):
        ctx = make_context(
            self.owner,
            form={
                "action": ["create"],
                "username": ["forbidden_admin"],
                "display_name": ["越权账号"],
                "password": ["secret1"],
                "scope_key": [SCOPE_A],
                "preset": ["scope_admin"],
            },
        )

        status, body, save_users_mock, _revoke_mock = self.run_route(
            ctx, [self.owner, self.child]
        )

        self.assertEqual(status, "403 Forbidden")
        self.assertIn("不能授予", body)
        save_users_mock.assert_not_called()

    def test_platform_admin_can_create_scope_admin(self):
        ctx = make_context(
            self.admin,
            form={
                "action": ["create"],
                "username": ["regional_owner"],
                "display_name": ["赛区主管"],
                "password": ["secret1"],
                "scope_key": [SCOPE_A],
                "preset": ["scope_admin"],
            },
        )

        status, _body, save_users_mock, _revoke_mock = self.run_route(
            ctx, [self.admin]
        )

        self.assertEqual(status, "200 OK")
        created = save_users_mock.call_args.args[0][-1]
        self.assertTrue(created["scope_grants"][0]["is_scope_admin"])

    def test_custom_grants_are_parsed_per_scope(self):
        ctx = make_context(
            self.admin,
            form={
                "scope_key": [SCOPE_A, SCOPE_B],
                "preset": ["custom"],
                "scope_permission": [
                    scope_accounts._permission_value(SCOPE_A, "match_result_manage"),
                    scope_accounts._permission_value(SCOPE_B, "scope_audit_view"),
                ],
            },
        )

        grants, error = scope_accounts.build_requested_scope_grants(
            ctx, self.admin, {SCOPE_A, SCOPE_B}
        )

        self.assertEqual(error, "")
        self.assertEqual(
            grants,
            [
                {
                    "scope_key": SCOPE_A,
                    "permissions": ["match_result_manage"],
                    "is_scope_admin": False,
                },
                {
                    "scope_key": SCOPE_B,
                    "permissions": ["scope_audit_view"],
                    "is_scope_admin": False,
                },
            ],
        )

    def test_scope_admin_cannot_move_child_to_unowned_scope(self):
        ctx = make_context(
            self.owner,
            form={
                "action": ["save_grants"],
                "username": ["child"],
                "display_name": ["Child"],
                "scope_key": [SCOPE_B],
                "preset": ["audit_viewer"],
            },
        )

        status, body, save_users_mock, _revoke_mock = self.run_route(
            ctx, [self.owner, self.child]
        )

        self.assertEqual(status, "403 Forbidden")
        self.assertIn("不在当前账号可管理范围", body)
        save_users_mock.assert_not_called()

    def test_shared_child_password_reset_is_denied(self):
        shared_child = {
            **self.child,
            "scope_grants": [
                *self.child["scope_grants"],
                {
                    "scope_key": SCOPE_B,
                    "permissions": ["scope_audit_view"],
                    "is_scope_admin": False,
                },
            ],
            "manager_scope_keys": [SCOPE_A, SCOPE_B],
        }
        ctx = make_context(
            self.owner,
            form={
                "action": ["reset_password"],
                "username": ["child"],
                "password": ["newpass1"],
            },
        )

        status, _body, save_users_mock, revoke_mock = self.run_route(
            ctx, [self.owner, shared_child]
        )

        self.assertEqual(status, "403 Forbidden")
        save_users_mock.assert_not_called()
        revoke_mock.assert_not_called()

    def test_disabling_owned_child_revokes_sessions(self):
        ctx = make_context(
            self.owner,
            form={
                "action": ["set_active"],
                "username": ["child"],
                "active": ["0"],
                "user_authorization_etag": [
                    scope_accounts.build_user_authorization_etag(self.child)
                ],
            },
        )

        status, _body, save_users_mock, revoke_mock = self.run_route(
            ctx, [self.owner, self.child]
        )

        self.assertEqual(status, "200 OK")
        saved_child = next(
            user
            for user in save_users_mock.call_args.args[0]
            if user["username"] == "child"
        )
        self.assertFalse(saved_child["active"])
        revoke_mock.assert_called_once_with("child")

    def test_stale_enable_after_disable_returns_409(self):
        stale_etag = scope_accounts.build_user_authorization_etag(self.child)
        disabled_child = {**self.child, "active": False}
        ctx = make_context(
            self.owner,
            form={
                "action": ["set_active"],
                "username": ["child"],
                "active": ["1"],
                "user_authorization_etag": [stale_etag],
            },
        )

        status, body, save_users_mock, revoke_mock = self.run_route(
            ctx, [self.owner, disabled_child]
        )

        self.assertEqual(status, "409 Conflict")
        self.assertIn("已发生变化", body)
        save_users_mock.assert_not_called()
        revoke_mock.assert_not_called()

    def test_stale_password_reset_after_target_auth_change_returns_409(self):
        stale_etag = scope_accounts.build_user_authorization_etag(self.child)
        changed_child = {
            **self.child,
            "password_salt": "changed-salt",
            "password_hash": "changed-hash",
        }
        ctx = make_context(
            self.owner,
            form={
                "action": ["reset_password"],
                "username": ["child"],
                "password": ["newpass1"],
                "user_authorization_etag": [stale_etag],
            },
        )

        status, body, save_users_mock, revoke_mock = self.run_route(
            ctx, [self.owner, changed_child]
        )

        self.assertEqual(status, "409 Conflict")
        self.assertIn("已发生变化", body)
        save_users_mock.assert_not_called()
        revoke_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
