from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import match_page


class PredictionScopePermissionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = [
            {
                "competition_name": "赛事A",
                "region_name": "深圳市",
                "series_slug": "jcds",
                "series_name": "赛事A",
            },
            {
                "competition_name": "赛事B",
                "region_name": "北京市",
                "series_slug": "event-b",
                "series_name": "赛事B",
            },
        ]
        self.match_a = {
            "match_id": "a-s1-260820-01",
            "competition_name": "赛事A",
            "season": "S1",
            "played_on": "2026-08-20",
            "round": 1,
            "game_no": 1,
            "players": [{"player_id": "player-a", "team_id": "team-a", "seat": 1}],
        }
        self.match_b = {
            "match_id": "b-s1-260820-01",
            "competition_name": "赛事B",
            "season": "S1",
            "played_on": "2026-08-20",
            "round": 1,
            "game_no": 1,
            "players": [{"player_id": "player-b", "team_id": "team-b", "seat": 1}],
        }
        self.data = {
            "matches": [self.match_a, self.match_b],
            "players": [
                {"player_id": "player-a", "display_name": "选手A", "team_id": "team-a"},
                {"player_id": "player-b", "display_name": "选手B", "team_id": "team-b"},
            ],
            "teams": [
                {
                    "team_id": "team-a",
                    "name": "战队A",
                    "competition_name": "赛事A",
                    "season_name": "S1",
                    "members": ["player-a"],
                },
                {
                    "team_id": "team-b",
                    "name": "战队B",
                    "competition_name": "赛事B",
                    "season_name": "S1",
                    "members": ["player-b"],
                },
            ],
            "season_player_dimension_stats": [],
        }
        self.prediction_user = {
            "username": "prediction-a",
            "role": "event_manager",
            "scope_grants": [
                {
                    "scope_key": "深圳市::jcds",
                    "permissions": ["prediction_manage"],
                    "is_scope_admin": False,
                }
            ],
            "scope_grants_authoritative": True,
            "permissions": [],
            "manager_scope_keys": [],
        }
        self.legacy_match_user = {
            "username": "legacy-match",
            "role": "event_manager",
            "permissions": ["match_manage"],
            "manager_scope_keys": ["深圳市::jcds"],
        }
        self.catalog_patch = patch.object(
            match_page.legacy, "load_series_catalog", return_value=self.catalog
        )
        self.catalog_patch.start()

    def tearDown(self):
        self.catalog_patch.stop()

    def context(self, *, user=None, method="GET", query=None, form=None):
        return web_app.RequestContext(
            method=method,
            path="/prediction-admin",
            query=query or {},
            form=form or {},
            files={},
            current_user=self.prediction_user if user is None else user,
            now_label="2026-08-20 12:00:00 中国时间",
        )

    def test_explicit_prediction_grant_is_required_and_does_not_imply_match_edit(self):
        self.assertTrue(
            match_page.can_manage_prediction_scope(
                self.prediction_user, self.data, "赛事A"
            )
        )
        self.assertFalse(
            match_page.can_manage_prediction_scope(
                self.prediction_user, self.data, "赛事B"
            )
        )
        self.assertFalse(
            match_page.can_manage_match_result_scope(
                self.prediction_user, self.data, "赛事A"
            )
        )
        self.assertFalse(
            match_page.can_manage_prediction_scope(
                self.legacy_match_user, self.data, "赛事A"
            )
        )

    def test_get_page_lists_only_prediction_authorized_matches(self):
        ctx = self.context(query={"match_id": [self.match_a["match_id"]]})
        context = {
            "predictions": [],
            "match": self.match_a,
            "data": self.data,
            "competition_name": "赛事A",
            "season_name": "S1",
        }
        with (
            patch.object(match_page, "load_validated_data", return_value=self.data),
            patch.object(match_page, "_prediction_day_scenario_admin_html", return_value="SCENARIO"),
            patch.object(match_page, "_build_match_prediction_context", return_value=(context, "")),
            patch.object(match_page.legacy, "load_prediction_model_settings", return_value={}),
            patch.object(match_page, "layout", side_effect=lambda _title, body, _ctx, alert="": body),
        ):
            html = match_page.get_prediction_admin_page(ctx)
        self.assertIn(self.match_a["match_id"], html)
        self.assertNotIn(self.match_b["match_id"], html)
        self.assertIn("SCENARIO", html)

    def test_get_handler_rejects_unauthorized_selected_match(self):
        ctx = self.context(query={"match_id": [self.match_b["match_id"]]})
        responses = []
        with (
            patch.object(match_page, "load_validated_data", return_value=self.data),
            patch.object(match_page, "layout", side_effect=lambda _title, body, _ctx, alert="": body),
        ):
            match_page.handle_prediction_admin(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )
        self.assertEqual(responses[0][0], "403 Forbidden")

    def test_manual_probability_post_rechecks_scope(self):
        form = {"match_id": [self.match_a["match_id"]]}
        for key, _label, _operator, _threshold in match_page.PREDICTION_BUCKETS:
            form[f"player-a__{key}"] = [""]
        allowed_ctx = self.context(method="POST", form=form)
        denied_ctx = self.context(
            user=self.legacy_match_user,
            method="POST",
            form=form,
        )

        allowed_responses = []
        with (
            patch.object(match_page, "load_validated_data", return_value=self.data),
            patch.object(match_page, "load_manual_score_predictions", return_value={}),
            patch.object(match_page, "save_manual_score_predictions") as save_mock,
        ):
            match_page.handle_prediction_admin(
                allowed_ctx,
                lambda status, headers: allowed_responses.append((status, dict(headers))),
            )
        self.assertEqual(allowed_responses[0][0], "302 Found")
        save_mock.assert_called_once()

        denied_responses = []
        with (
            patch.object(match_page, "load_validated_data", return_value=self.data),
            patch.object(match_page, "get_prediction_admin_page", return_value="forbidden"),
            patch.object(match_page, "save_manual_score_predictions") as denied_save,
        ):
            match_page.handle_prediction_admin(
                denied_ctx,
                lambda status, headers: denied_responses.append((status, dict(headers))),
            )
        self.assertEqual(denied_responses[0][0], "403 Forbidden")
        denied_save.assert_not_called()

    def test_model_settings_remain_platform_admin_only(self):
        ctx = self.context(
            method="POST",
            form={"action": ["save_model_settings"]},
        )
        responses = []
        with (
            patch.object(match_page, "get_prediction_admin_page", return_value="forbidden"),
            patch.object(match_page.legacy, "save_prediction_model_settings") as save_mock,
        ):
            match_page.handle_prediction_admin(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
            )
        self.assertEqual(responses[0][0], "403 Forbidden")
        save_mock.assert_not_called()

    def test_scenario_post_rejects_legacy_match_manage_before_write(self):
        ctx = self.context(
            user=self.legacy_match_user,
            method="POST",
            form={
                "scenario_competition": ["赛事A"],
                "scenario_season": ["S1"],
                "scenario_date": ["2026-08-20"],
            },
        )
        responses = []
        with (
            patch.object(match_page, "get_prediction_admin_page", return_value="forbidden"),
            patch.object(match_page, "save_prediction_day_scenarios") as save_mock,
        ):
            match_page._handle_prediction_day_scenario_admin(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(responses[0][0], "403 Forbidden")
        save_mock.assert_not_called()

    def test_prediction_manager_can_publish_authorized_scenario(self):
        form = {
            "scenario_competition": ["赛事A"],
            "scenario_season": ["S1"],
            "scenario_date": ["2026-08-20"],
        }
        for index in range(1, 13):
            form[f"scenario_player_id_{index}"] = [""]
            form[f"scenario_player_{index}"] = [f"临时选手{index}"]
            form[f"scenario_team_{index}"] = ["战队A"]
            form[f"scenario_override_{index}"] = [""]
        ctx = self.context(method="POST", form=form)
        responses = []
        captured = {}
        with (
            patch.object(match_page.legacy, "list_seasons", return_value=["S1"]),
            patch.object(match_page, "load_prediction_day_scenarios", return_value={}),
            patch.object(
                match_page,
                "save_prediction_day_scenarios",
                side_effect=lambda payload: captured.update(payload),
            ),
            patch.object(match_page.legacy, "audit_action"),
        ):
            match_page._handle_prediction_day_scenario_admin(
                ctx,
                lambda status, headers: responses.append((status, dict(headers))),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(responses[0][0], "302 Found")
        self.assertEqual(len(captured), 1)
        scenario = next(iter(captured.values()))
        self.assertEqual(scenario["competition_name"], "赛事A")
        self.assertEqual(len(scenario["roster"]), 12)


if __name__ == "__main__":
    unittest.main()
