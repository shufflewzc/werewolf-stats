from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import console, matches, scope_accounts


SCOPE_KEY = "深圳市::sz-league"


def make_user(
    *permission_keys: str,
    username: str = "operator",
    is_scope_admin: bool = False,
) -> dict[str, object]:
    return {
        "username": username,
        "display_name": username,
        "role": "event_manager",
        "permissions": [],
        "manager_scope_keys": [SCOPE_KEY],
        "scope_grants_authoritative": True,
        "scope_grants": [
            {
                "scope_key": SCOPE_KEY,
                "permissions": list(permission_keys),
                "is_scope_admin": is_scope_admin,
            }
        ],
    }


def make_context(
    path: str,
    *,
    user: dict[str, object] | None,
    method: str = "GET",
    query: dict[str, list[str]] | None = None,
    form: dict[str, list[str]] | None = None,
) -> web_app.RequestContext:
    return web_app.RequestContext(
        method=method,
        path=path,
        query=query or {},
        form=form or {},
        files={},
        current_user=user,
        now_label="2026-08-20 10:00:00 中国时间",
        remote_addr="127.0.0.1",
        request_id="req_console_routing_test",
        session_token="test-session",
    )


class ConsoleRoutingIntegrationTests(unittest.TestCase):
    def call_app(self, ctx: web_app.RequestContext):
        response: dict[str, object] = {}

        def start_response(status, headers, _exc_info=None):
            response["status"] = status
            response["headers"] = dict(headers)

        environ = {
            "REQUEST_METHOD": ctx.method,
            "PATH_INFO": ctx.path,
            "QUERY_STRING": "",
            "REMOTE_ADDR": ctx.remote_addr,
            "HTTP_USER_AGENT": "console-routing-test",
        }
        with (
            patch.object(web_app, "build_context", return_value=ctx),
            patch.object(web_app, "validate_csrf_token", return_value=True),
            patch.object(web_app, "request_rate_limited", return_value=(False, 0)),
            patch.object(web_app, "duplicate_write_request", return_value=False),
            patch.object(web_app, "enqueue_access_log"),
        ):
            response["body"] = b"".join(web_app.app(environ, start_response))
        return response

    def test_all_console_routes_redirect_anonymous_users_to_login(self):
        paths = (
            "/console",
            "/console/matches",
            "/console/matches/create",
            "/console/matches/batch-create",
            "/console/imports",
            "/console/imports/matches",
            "/console/imports/dimensions",
            "/console/imports/assets",
            "/console/imports/review",
            "/console/accounts",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.call_app(make_context(path, user=None))
                self.assertEqual(response["status"], "302 Found")
                self.assertIn("/login?next=", response["headers"]["Location"])
                self.assertIn(path, response["headers"]["Location"])

    def test_console_overview_and_search_dispatch_to_console_feature(self):
        admin = make_user(username="admin")
        for path in ("/console", "/console/matches"):
            with self.subTest(path=path):
                seen: list[str] = []

                def fake_handler(ctx, start_response):
                    seen.append(ctx.path)
                    start_response("209 Console Route", [("Content-Type", "text/plain")])
                    return [b"console-route"]

                with patch.object(console, "handle_console_route", side_effect=fake_handler):
                    response = self.call_app(make_context(path, user=admin))
                self.assertEqual(response["status"], "209 Console Route")
                self.assertEqual(response["body"], b"console-route")
                self.assertEqual(seen, [path])

    def test_operation_routes_dispatch_to_match_task_handler_with_original_path(self):
        admin = make_user(username="admin")
        paths = (
            "/console/matches/create",
            "/console/matches/batch-create",
            "/console/imports",
            "/console/imports/matches",
            "/console/imports/dimensions",
            "/console/imports/assets",
            "/console/imports/review",
        )
        for path in paths:
            with self.subTest(path=path):
                seen: list[str] = []

                def fake_handler(ctx, start_response):
                    seen.append(ctx.path)
                    start_response("209 Match Task", [("Content-Type", "text/plain")])
                    return [b"match-task"]

                with patch.object(web_app, "handle_match_create", side_effect=fake_handler):
                    response = self.call_app(make_context(path, user=admin))
                self.assertEqual(response["status"], "209 Match Task")
                self.assertEqual(response["body"], b"match-task")
                self.assertEqual(seen, [path])

    def test_accounts_route_dispatches_to_scoped_account_handler(self):
        actor = make_user(is_scope_admin=True)
        seen: list[str] = []

        def fake_handler(ctx, start_response):
            seen.append(ctx.path)
            start_response("209 Scope Accounts", [("Content-Type", "text/plain")])
            return [b"scope-accounts"]

        with patch.object(
            scope_accounts,
            "handle_scope_accounts_route",
            side_effect=fake_handler,
        ):
            response = self.call_app(make_context("/console/accounts", user=actor))

        self.assertEqual(response["status"], "209 Scope Accounts")
        self.assertEqual(response["body"], b"scope-accounts")
        self.assertEqual(seen, ["/console/accounts"])

    def test_permissionless_user_gets_403_for_console_and_task_routes(self):
        user = make_user()
        operation_paths = (
            "/console/matches/create",
            "/console/matches/batch-create",
            "/console/imports",
            "/console/imports/matches",
            "/console/imports/dimensions",
            "/console/imports/assets",
            "/console/accounts",
        )
        for path in operation_paths:
            with self.subTest(path=path):
                response = self.call_app(make_context(path, user=user))
                self.assertEqual(response["status"], "403 Forbidden")

        with (
            patch.object(console, "load_validated_data", return_value={"matches": []}),
            patch.object(console, "accessible_competitions", return_value=[]),
        ):
            for path in ("/console", "/console/matches"):
                with self.subTest(path=path):
                    response = self.call_app(make_context(path, user=user))
                    self.assertEqual(response["status"], "403 Forbidden")

    def test_match_edit_route_requires_result_permission_for_target_scope(self):
        data = {
            "matches": [
                {
                    "match_id": "sz-s4-260813-01",
                    "competition_name": "深圳联赛",
                }
            ]
        }
        catalog = [
            {
                "competition_name": "深圳联赛",
                "region_name": "深圳市",
                "series_slug": "sz-league",
            }
        ]
        with (
            patch.object(web_app, "load_validated_data", return_value=data),
            patch.object(web_app, "load_series_catalog", return_value=catalog),
            patch.object(web_app, "handle_match_edit") as edit_handler,
        ):
            denied = self.call_app(
                make_context(
                    "/matches/sz-s4-260813-01/edit",
                    user=make_user("match_import_manage"),
                )
            )
        self.assertEqual(denied["status"], "403 Forbidden")
        edit_handler.assert_not_called()

        def fake_edit_handler(ctx, start_response, match_id):
            self.assertEqual(match_id, "sz-s4-260813-01")
            start_response("209 Match Edit", [("Content-Type", "text/plain")])
            return [b"match-edit"]

        with (
            patch.object(web_app, "load_validated_data", return_value=data),
            patch.object(web_app, "load_series_catalog", return_value=catalog),
            patch.object(web_app, "handle_match_edit", side_effect=fake_edit_handler),
        ):
            allowed = self.call_app(
                make_context(
                    "/matches/sz-s4-260813-01/edit",
                    user=make_user("match_result_manage"),
                )
            )
        self.assertEqual(allowed["status"], "209 Match Edit")
        self.assertEqual(allowed["body"], b"match-edit")

    def test_review_rejects_another_users_job_with_403_on_get_and_post(self):
        user = make_user("match_import_manage")
        job = {
            "batch_id": "import-secret",
            "created_by": "another-operator",
            "status": "awaiting_confirmation",
            "metadata": {},
        }
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                ctx = make_context(
                    "/console/imports/review",
                    user=user,
                    method=method,
                    query={"job_id": ["import-secret"]},
                    form={
                        "job_id": ["import-secret"],
                        "action": ["confirm_import_preflight"],
                    },
                )
                with patch.object(matches, "get_preflight", return_value=job):
                    response = self.call_app(ctx)
                self.assertEqual(response["status"], "403 Forbidden")

    def test_sidebar_hides_tasks_not_granted_by_granular_permissions(self):
        cases = (
            (
                make_user("match_schedule_manage"),
                {
                    "/console/matches",
                    "/console/matches/create",
                    "/console/matches/batch-create",
                },
                {
                    "/console/imports/matches",
                    "/console/imports/dimensions",
                    "/console/imports/assets",
                    "/prediction-admin",
                    "/console/accounts",
                },
            ),
            (
                make_user("match_import_manage"),
                {"/console/matches", "/console/imports/matches", "/console/imports"},
                {
                    "/console/matches/create",
                    "/console/imports/dimensions",
                    "/console/imports/assets",
                    "/prediction-admin",
                    "/console/accounts",
                },
            ),
            (
                make_user("dimension_data_manage"),
                {"/console/matches", "/console/imports/dimensions", "/console/imports"},
                {
                    "/console/matches/create",
                    "/console/imports/matches",
                    "/console/imports/assets",
                    "/prediction-admin",
                    "/console/accounts",
                },
            ),
            (
                make_user("season_asset_manage"),
                {"/console/matches", "/console/imports/assets", "/console/imports"},
                {
                    "/console/matches/create",
                    "/console/imports/matches",
                    "/console/imports/dimensions",
                    "/prediction-admin",
                    "/console/accounts",
                },
            ),
            (
                make_user("scope_audit_view"),
                {"/console/matches", "/console/imports"},
                {
                    "/console/matches/create",
                    "/console/imports/matches",
                    "/console/imports/dimensions",
                    "/console/imports/assets",
                    "/prediction-admin",
                    "/console/accounts",
                },
            ),
        )
        for user, visible_paths, hidden_paths in cases:
            with self.subTest(permission=user["scope_grants"][0]["permissions"]):
                ctx = make_context("/console", user=user)
                html = web_app.layout("控制台", "<p>body</p>", ctx)
                for path in visible_paths:
                    self.assertIn(f'href="{path}"', html)
                for path in hidden_paths:
                    self.assertNotIn(f'href="{path}"', html)
                self.assertNotIn('href="/accounts"', html)
                self.assertNotIn('href="/permissions"', html)

    def test_scope_admin_sidebar_contains_all_scoped_tasks_but_not_platform_admin(self):
        ctx = make_context("/console", user=make_user(is_scope_admin=True))
        html = web_app.layout("控制台", "<p>body</p>", ctx)
        for path in (
            "/console/matches",
            "/console/matches/create",
            "/console/matches/batch-create",
            "/console/imports/matches",
            "/console/imports/dimensions",
            "/console/imports/assets",
            "/console/imports",
            "/prediction-admin",
            "/series-manage",
            "/console/accounts",
        ):
            self.assertIn(f'href="{path}"', html)
        self.assertNotIn('href="/accounts"', html)
        self.assertNotIn('href="/permissions"', html)
        self.assertLess(
            html.index('href="/console/accounts"'),
            html.index('href="/console/matches"'),
        )

    def test_admin_sidebar_is_viewport_bound_with_independent_navigation_scroll(self):
        user = make_user(is_scope_admin=True)
        html = web_app.layout(
            "控制台",
            "<p>body</p>",
            make_context("/console", user=user),
        )

        self.assertIn("height: calc(100vh - 1rem);", html)
        self.assertIn("scrollbar-gutter: stable;", html)
        self.assertIn("overscroll-behavior: contain;", html)
        self.assertIn(
            "height: max(12rem, calc(100vh - 13.5rem));",
            html,
        )
        self.assertIn("height: auto;", html)

    def test_common_operation_page_has_console_return_with_scope_preserved(self):
        user = make_user("match_schedule_manage")
        html = web_app.layout(
            "新增比赛",
            "<p>body</p>",
            make_context(
                "/console/matches/create",
                user=user,
                query={"competition": ["深圳联赛"], "season": ["S4"]},
            ),
        )

        self.assertIn("返回控制台", html)
        self.assertIn(
            'href="/console?competition=%E6%B7%B1%E5%9C%B3%E8%81%94%E8%B5%9B&amp;season=S4"',
            html,
        )

        overview = web_app.layout(
            "控制台",
            "<p>body</p>",
            make_context("/console", user=user),
        )
        self.assertNotIn(">返回控制台</a>", overview)

    def test_all_console_paths_use_admin_layout(self):
        user = make_user(is_scope_admin=True)
        for path in (
            "/console",
            "/console/matches",
            "/console/matches/create",
            "/console/matches/batch-create",
            "/console/imports",
            "/console/imports/matches",
            "/console/imports/dimensions",
            "/console/imports/assets",
            "/console/imports/review",
            "/console/accounts",
        ):
            with self.subTest(path=path):
                html = web_app.layout(
                    "管理任务",
                    '<div id="routing-marker"></div>',
                    make_context(path, user=user),
                )
                self.assertIn('<body class="app-admin">', html)
                self.assertIn('<aside class="admin-sidebar">', html)

    def test_public_predictions_api_keeps_its_existing_dispatch(self):
        marker = {"called": False}

        def fake_predictions_api(ctx, start_response):
            marker["called"] = True
            self.assertEqual(ctx.path, "/api/predictions")
            start_response("209 Public Predictions", [("Content-Type", "application/json")])
            return [b'{"public":true}']

        ctx = make_context("/api/predictions", user=None)
        with (
            patch.object(web_app, "handle_predictions_api", side_effect=fake_predictions_api),
            patch.object(web_app, "handle_match_create") as console_task_handler,
            patch.object(console, "handle_console_route") as console_handler,
        ):
            response = self.call_app(ctx)

        self.assertEqual(response["status"], "209 Public Predictions")
        self.assertEqual(response["body"], b'{"public":true}')
        self.assertTrue(marker["called"])
        console_task_handler.assert_not_called()
        console_handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
