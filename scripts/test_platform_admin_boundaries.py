from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import competitions
from web.features import matches as matches_feature


def make_user(*, role: str = "event_manager") -> dict[str, object]:
    return {
        "username": "operator",
        "role": role,
        "permissions": [],
        "scope_grants": [
            {
                "scope_key": "test-region::test-series",
                "permissions": [],
                "is_scope_admin": True,
            }
        ],
        "scope_grants_authoritative": True,
    }


def make_ctx(
    *,
    user: dict[str, object] | None = None,
    method: str = "GET",
    path: str = "/",
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
        now_label="2026-08-20 12:00:00 中国时间",
    )


def call_handler(handler, *args):
    response: dict[str, object] = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    body = handler(args[0], start_response, *args[1:])
    response["body"] = b"".join(body).decode("utf-8") if body else ""
    return response


class DestructiveControlVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.scope_admin = make_user()
        self.platform_admin = make_user(role="admin")

    def test_dimension_upload_only_shows_season_clear_to_platform_admin(self):
        def render(user):
            ctx = make_ctx(user=user, path="/console/imports/dimensions")
            with (
                patch.object(matches_feature, "build_match_competition_field", return_value="<select></select>"),
                patch.object(matches_feature, "build_match_season_field", return_value="<select></select>"),
            ):
                return matches_feature.build_dimension_import_panel(ctx)

        scoped_html = render(self.scope_admin)
        admin_html = render(self.platform_admin)

        self.assertIn('value="import_dimension_excel"', scoped_html)
        self.assertNotIn('value="clear_dimension_stats"', scoped_html)
        self.assertIn('value="clear_dimension_stats"', admin_html)

    def test_import_history_only_shows_rollback_to_platform_admin(self):
        batch = {
            "batch_id": "imp-1",
            "status": "succeeded",
            "action": "dimension.import_excel",
            "created_by": "operator",
            "metadata": {"permission_scope_keys": ["test-region::test-series"]},
        }

        def render(user):
            with (
                patch.object(matches_feature, "load_import_batches", return_value=[deepcopy(batch)]),
                patch.object(matches_feature, "can_view_import_batch", return_value=True),
            ):
                return matches_feature.build_import_batches_panel(
                    make_ctx(user=user, path="/console/imports")
                )

        scoped_html = render(self.scope_admin)
        admin_html = render(self.platform_admin)

        self.assertNotIn('value="rollback_import_batch"', scoped_html)
        self.assertIn("仅平台管理员可回滚", scoped_html)
        self.assertIn('value="rollback_import_batch"', admin_html)

    def test_match_management_only_shows_batch_delete_to_platform_admin(self):
        data = {"matches": [], "teams": [], "players": []}

        def render(user):
            with (
                patch.object(matches_feature, "load_validated_data", return_value=deepcopy(data)),
                patch.object(matches_feature, "build_match_competition_field", return_value="<select></select>"),
                patch.object(matches_feature, "build_match_season_field", return_value="<select></select>"),
                patch.object(matches_feature, "resolve_stage_options_for_scope", return_value={}),
            ):
                return matches_feature.build_match_management_panel(
                    make_ctx(user=user, path="/console/matches")
                )

        scoped_html = render(self.scope_admin)
        admin_html = render(self.platform_admin)

        self.assertIn('value="batch_mark_team_score_excluded"', scoped_html)
        self.assertNotIn('value="batch_delete_matches"', scoped_html)
        self.assertIn('value="batch_delete_matches"', admin_html)

    def test_dimension_day_delete_only_shows_to_platform_admin(self):
        data = {
            "matches": [],
            "teams": [],
            "players": [{"player_id": "p1", "display_name": "选手一"}],
            "season_player_dimension_stats": [
                {
                    "competition_name": "测试赛事",
                    "season_name": "S1",
                    "played_on": "2026-08-20",
                    "player_id": "p1",
                }
            ],
            "season_team_dimension_stats": [],
        }

        def render(user):
            with (
                patch.object(matches_feature, "load_validated_data", return_value=deepcopy(data)),
                patch.object(matches_feature, "can_manage_competition_action", return_value=True),
                patch.object(matches_feature, "layout", side_effect=lambda _title, body, *_args, **_kwargs: body),
            ):
                return matches_feature.get_dimension_stats_manage_page(
                    make_ctx(user=user, path="/dimension-stats")
                )

        scoped_html = render(self.scope_admin)
        admin_html = render(self.platform_admin)

        self.assertNotIn('value="delete_dimension_day"', scoped_html)
        self.assertIn("仅平台管理员可删除", scoped_html)
        self.assertIn('value="delete_dimension_day"', admin_html)


class DestructivePostBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scope_admin = make_user()

    def test_dimension_day_delete_rejects_scope_admin_before_delete(self):
        ctx = make_ctx(
            user=self.scope_admin,
            method="POST",
            path="/dimension-stats",
            form={
                "action": ["delete_dimension_day"],
                "competition_name": ["测试赛事"],
                "season": ["S1"],
                "played_on": ["2026-08-20"],
                "danger_confirmation": ["删除维度"],
            },
        )
        with (
            patch.object(matches_feature, "load_validated_data", return_value={"matches": [], "teams": [], "players": []}),
            patch.object(matches_feature, "get_dimension_stats_manage_page", return_value="forbidden"),
            patch.object(matches_feature, "clear_season_dimension_stats_for_day") as delete_rows,
            patch.object(matches_feature, "audit_action") as audit,
        ):
            response = call_handler(matches_feature.handle_dimension_stats_manage, ctx)

        self.assertEqual(response["status"], "403 Forbidden")
        delete_rows.assert_not_called()
        audit.assert_not_called()

    def test_import_rollback_rejects_scope_admin_before_rollback(self):
        ctx = make_ctx(
            user=self.scope_admin,
            method="POST",
            path="/console/imports",
            form={
                "action": ["rollback_import_batch"],
                "batch_id": ["imp-1"],
                "danger_confirmation": ["回滚 imp-1"],
            },
        )
        batch = {"batch_id": "imp-1", "status": "succeeded"}
        with (
            patch.object(matches_feature, "load_validated_data", return_value={"matches": [], "teams": [], "players": []}),
            patch.object(matches_feature, "load_import_batches", return_value=[batch]),
            patch.object(matches_feature, "can_view_import_batch", return_value=True),
            patch.object(matches_feature, "get_match_create_page", return_value="forbidden"),
            patch.object(matches_feature, "rollback_import_batch") as rollback,
            patch.object(matches_feature, "audit_action") as audit,
        ):
            response = call_handler(matches_feature.handle_match_create, ctx)

        self.assertEqual(response["status"], "403 Forbidden")
        rollback.assert_not_called()
        audit.assert_not_called()

    def test_batch_match_delete_rejects_scope_admin_before_write(self):
        ctx = make_ctx(
            user=self.scope_admin,
            method="POST",
            path="/console/matches",
            form={
                "action": ["batch_delete_matches"],
                "match_ids": ["match-1"],
                "danger_confirmation": ["删除比赛"],
            },
        )
        with (
            patch.object(matches_feature, "load_validated_data", return_value={"matches": [{"match_id": "match-1"}], "teams": [], "players": []}),
            patch.object(matches_feature, "get_match_create_page", return_value="forbidden"),
            patch.object(matches_feature, "save_repository_state") as save,
            patch.object(matches_feature, "audit_action") as audit,
        ):
            response = call_handler(matches_feature.handle_match_create, ctx)

        self.assertEqual(response["status"], "403 Forbidden")
        save.assert_not_called()
        audit.assert_not_called()

    def test_clear_season_dimensions_rejects_scope_admin_before_delete(self):
        ctx = make_ctx(
            user=self.scope_admin,
            method="POST",
            path="/console/imports/dimensions",
            form={
                "action": ["clear_dimension_stats"],
                "competition_name": ["测试赛事"],
                "season": ["S1"],
                "danger_confirmation": ["清空维度"],
            },
        )
        with (
            patch.object(matches_feature, "load_validated_data", return_value={"matches": [], "teams": [], "players": []}),
            patch.object(matches_feature, "get_match_create_page", return_value="forbidden"),
            patch.object(matches_feature, "clear_season_dimension_stats") as clear,
            patch.object(matches_feature, "audit_action") as audit,
        ):
            response = call_handler(matches_feature.handle_match_create, ctx)

        self.assertEqual(response["status"], "403 Forbidden")
        clear.assert_not_called()
        audit.assert_not_called()


class AiSummaryWriteBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scope_admin = make_user()

    def _assert_rejected(self, handler, ctx, *handler_args):
        with patch.object(web_app, "layout", side_effect=lambda _title, body, *_args, **_kwargs: body):
            response = call_handler(handler, ctx, *handler_args)
        self.assertEqual(response["status"], "403 Forbidden")

    def test_scope_admin_cannot_save_or_generate_season_summary(self):
        handlers = (competitions.handle_competitions, competitions.handle_ai_analysis)
        actions = ("save_ai_season_summary", "generate_ai_season_summary")
        for handler in handlers:
            for action in actions:
                with self.subTest(handler=handler.__name__, action=action):
                    ctx = make_ctx(
                        user=self.scope_admin,
                        method="POST",
                        path="/ai-analysis" if handler is competitions.handle_ai_analysis else "/competitions",
                        form={
                            "action": [action],
                            "competition_name": ["测试赛事"],
                            "season_name": ["S1"],
                            "summary_content": ["非法写入"],
                        },
                    )
                    with (
                        patch.object(competitions.legacy, "AI_PUBLIC_FEATURES_ENABLED", True),
                        patch.object(competitions, "save_ai_season_summary") as save,
                        patch.object(competitions, "_generate_and_save_ai_season_summary") as generate_direct,
                        patch.object(competitions, "generate_ai_season_summary") as generate_legacy,
                    ):
                        self._assert_rejected(handler, ctx)
                    save.assert_not_called()
                    generate_direct.assert_not_called()
                    generate_legacy.assert_not_called()

    def test_scope_admin_cannot_save_or_generate_daily_summary(self):
        for action in ("save_ai_daily_brief", "generate_ai_daily_brief"):
            with self.subTest(action=action):
                ctx = make_ctx(
                    user=self.scope_admin,
                    method="POST",
                    path="/days/2026-08-20",
                    query={"competition": ["测试赛事"], "season": ["S1"]},
                    form={"action": [action], "report_content": ["非法写入"]},
                )
                with (
                    patch.object(competitions.legacy, "AI_PUBLIC_FEATURES_ENABLED", True),
                    patch.object(competitions, "save_ai_match_day_report") as save,
                ):
                    self._assert_rejected(
                        competitions.handle_match_day,
                        ctx,
                        "2026-08-20",
                    )
                save.assert_not_called()

    def test_scope_admin_cannot_save_or_generate_team_summary(self):
        for action in ("save_ai_team_season_summary", "generate_ai_team_season_summary"):
            with self.subTest(action=action):
                ctx = make_ctx(
                    user=self.scope_admin,
                    method="POST",
                    path="/teams/team-1",
                    form={
                        "action": [action],
                        "competition_name": ["测试赛事"],
                        "season_name": ["S1"],
                        "summary_content": ["非法写入"],
                    },
                )
                with (
                    patch.object(web_app, "AI_PUBLIC_FEATURES_ENABLED", True),
                    patch.object(web_app, "save_ai_team_season_summary") as save,
                    patch.object(web_app, "generate_ai_team_season_summary") as generate,
                ):
                    self._assert_rejected(web_app.handle_team_page, ctx, "team-1")
                save.assert_not_called()
                generate.assert_not_called()

    def test_scope_admin_cannot_save_or_generate_player_summary(self):
        for action in ("save_ai_player_season_summary", "generate_ai_player_season_summary"):
            with self.subTest(action=action):
                ctx = make_ctx(
                    user=self.scope_admin,
                    method="POST",
                    path="/players/player-1",
                    form={
                        "action": [action],
                        "competition_name": ["测试赛事"],
                        "season_name": ["S1"],
                        "summary_content": ["非法写入"],
                    },
                )
                with (
                    patch.object(web_app, "AI_PUBLIC_FEATURES_ENABLED", True),
                    patch.object(web_app, "save_ai_player_season_summary") as save,
                    patch.object(web_app, "generate_ai_player_season_summary") as generate,
                ):
                    self._assert_rejected(web_app.handle_player_page, ctx, "player-1")
                save.assert_not_called()
                generate.assert_not_called()

    def test_scope_admin_cannot_ask_ai_data_question(self):
        ctx = make_ctx(
            user=self.scope_admin,
            method="POST",
            path="/ai-analysis",
            form={
                "action": ["ask_ai_data_question"],
                "competition_name": ["测试赛事"],
                "season_name": ["S1"],
                "question": ["谁的表现最好？"],
                "response_mode": ["json"],
            },
        )
        with (
            patch.object(competitions.legacy, "AI_PUBLIC_FEATURES_ENABLED", True),
            patch.object(competitions, "generate_ai_data_question_answer") as generate,
            patch.object(competitions, "record_ai_conversation") as record,
        ):
            self._assert_rejected(competitions.handle_ai_analysis, ctx)
        generate.assert_not_called()
        record.assert_not_called()

    def test_anonymous_user_cannot_ask_ai_data_question(self):
        ctx = make_ctx(
            user=None,
            method="POST",
            path="/ai-analysis",
            form={
                "action": ["ask_ai_data_question"],
                "competition_name": ["测试赛事"],
                "season_name": ["S1"],
                "question": ["谁的表现最好？"],
            },
        )
        with (
            patch.object(competitions.legacy, "AI_PUBLIC_FEATURES_ENABLED", True),
            patch.object(competitions, "generate_ai_data_question_answer") as generate,
            patch.object(competitions, "record_ai_conversation") as record,
        ):
            self._assert_rejected(competitions.handle_ai_analysis, ctx)
        generate.assert_not_called()
        record.assert_not_called()

    def test_public_daily_payload_keeps_existing_summary_read_only(self):
        scope = {
            "grouped_matches": {},
            "selected_competition": "测试赛事",
            "selected_season": "S1",
            "completed_day_matches": [],
            "day_matches": [],
            "ai_settings": {
                "base_url": "https://ai.example.test",
                "api_key": "secret",
                "model": "test-model",
            },
            "ai_report": {
                "content": "公开日报正文",
                "generated_at": "2026-08-20",
                "model": "test-model",
            },
            "next_path": "/dashboard",
            "day_team_rows": [],
            "day_player_rows": [],
            "catalog": [],
            "data": {"matches": [], "teams": [], "players": []},
            "player_lookup": {},
            "team_lookup": {},
        }
        with patch.object(competitions.legacy, "AI_PUBLIC_FEATURES_ENABLED", True):
            public_payload = competitions.build_match_day_api_payload(
                make_ctx(user=None, path="/api/days/2026-08-20"),
                "2026-08-20",
                deepcopy(scope),
            )
            admin_payload = competitions.build_match_day_api_payload(
                make_ctx(user=make_user(role="admin"), path="/api/days/2026-08-20"),
                "2026-08-20",
                deepcopy(scope),
            )

        self.assertTrue(public_payload["ai_report"]["exists"])
        self.assertEqual(public_payload["ai_report"]["content"], "公开日报正文")
        self.assertFalse(public_payload["ai_report"]["can_generate"])
        self.assertFalse(public_payload["ai_report"]["can_edit"])
        self.assertTrue(admin_payload["ai_report"]["can_generate"])
        self.assertTrue(admin_payload["ai_report"]["can_edit"])


if __name__ == "__main__":
    unittest.main()
