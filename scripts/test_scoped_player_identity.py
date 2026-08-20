import json
import unittest
from unittest.mock import patch

import web_app


def sample_data():
    return {
        "players": [
            {
                "player_id": "player-s1",
                "display_name": "本人 S1",
                "team_id": "team-s1",
                "photo": "assets/players/default-player.svg",
            },
            {
                "player_id": "player-s2",
                "display_name": "本人 S2",
                "team_id": "team-s2",
                "photo": "assets/players/default-player.svg",
            },
            {
                "player_id": "player-s1-other",
                "display_name": "本人 S1 重复",
                "team_id": "team-s1-other",
                "photo": "assets/players/default-player.svg",
            },
        ],
        "teams": [
            {
                "team_id": "team-s1",
                "name": "S1 战队",
                "competition_name": "测试赛事",
                "season_name": "S1",
            },
            {
                "team_id": "team-s2",
                "name": "S2 战队",
                "competition_name": "测试赛事",
                "season_name": "S2",
            },
            {
                "team_id": "team-s1-other",
                "name": "S1 另一战队",
                "competition_name": "测试赛事",
                "season_name": "S1",
            },
        ],
        "matches": [],
    }


class ScopedPlayerIdentityTests(unittest.TestCase):
    def test_resolves_exact_team_scope_without_match_history(self):
        user = {
            "player_id": "player-s1",
            "linked_player_ids": ["player-s2"],
        }
        result = web_app.resolve_user_player_for_scope(
            sample_data(), user, "测试赛事", "S2"
        )
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["player"]["player_id"], "player-s2")

    def test_does_not_fall_back_to_another_season(self):
        user = {"player_id": "player-s1", "linked_player_ids": []}
        result = web_app.resolve_user_player_for_scope(
            sample_data(), user, "测试赛事", "S2"
        )
        self.assertEqual(result, {
            "status": "not_in_scope",
            "player": None,
            "candidates": [],
        })

    def test_reports_legacy_same_scope_conflict(self):
        user = {
            "player_id": "player-s1",
            "linked_player_ids": ["player-s1-other"],
        }
        result = web_app.resolve_user_player_for_scope(
            sample_data(), user, "测试赛事", "S1"
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(
            {item["player_id"] for item in result["candidates"]},
            {"player-s1", "player-s1-other"},
        )

    def test_binding_conflict_uses_team_scope_without_matches(self):
        user = {"player_id": "player-s1", "linked_player_ids": []}
        conflict = web_app.find_season_binding_conflict(
            sample_data(), user, "player-s1-other"
        )
        self.assertEqual(conflict, (
            "player-s1",
            ["测试赛事 / S1"],
        ))

    def test_any_bound_player_is_owned_by_user(self):
        user = {
            "player_id": "player-s1",
            "linked_player_ids": ["player-s2"],
        }
        self.assertTrue(web_app.user_has_bound_player_id(user, "player-s2"))

    def test_current_player_endpoint_requires_login(self):
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/miniprogram/current-player",
            query={"session_token": ["invalid"], "competition": ["测试赛事"], "season": ["S1"]},
            form={},
            files={},
            current_user=None,
            now_label="now",
        )
        response = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = headers

        with patch.object(web_app, "load_session_username", return_value=None):
            body = web_app.handle_miniprogram_current_player(ctx, start_response)
        self.assertEqual(response["status"], "401 Unauthorized")
        self.assertEqual(json.loads(body[0])["error"], "请先登录。")

    def test_current_player_endpoint_returns_scoped_identity(self):
        user = {
            "username": "tester",
            "player_id": "player-s1",
            "linked_player_ids": ["player-s2"],
        }
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/miniprogram/current-player",
            query={"session_token": ["token"], "competition": ["测试赛事"], "season": ["S2"]},
            form={},
            files={},
            current_user=None,
            now_label="now",
        )
        response = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = headers

        with (
            patch.object(web_app, "load_session_username", return_value="tester"),
            patch.object(web_app, "load_users", return_value=[user]),
            patch.object(web_app, "load_validated_data", return_value=sample_data()),
            patch.object(
                web_app,
                "resolve_api_scope_request",
                return_value=(
                    {"competition": "测试赛事", "season": "S2"},
                    None,
                ),
            ),
        ):
            body = web_app.handle_miniprogram_current_player(ctx, start_response)
        payload = json.loads(body[0])
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(payload["status"], "matched")
        self.assertEqual(payload["player"]["player_id"], "player-s2")

    def test_miniprogram_binding_rejects_same_scope_player(self):
        user = {
            "username": "tester",
            "player_id": "player-s1",
            "linked_player_ids": [],
        }
        ctx = web_app.RequestContext(
            method="POST",
            path="/api/miniprogram/bind-player",
            query={},
            form={"session_token": ["token"], "player_id": ["player-s1-other"]},
            files={},
            current_user=None,
            now_label="now",
        )
        response = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = headers

        with (
            patch.object(web_app, "load_session_username", return_value="tester"),
            patch.object(web_app, "load_users", return_value=[user]),
            patch.object(web_app, "load_validated_data", return_value=sample_data()),
        ):
            body = web_app.handle_miniprogram_bind_player(ctx, start_response)
        payload = json.loads(body[0])
        self.assertEqual(response["status"], "409 Conflict")
        self.assertEqual(payload["code"], "PLAYER_SCOPE_ALREADY_BOUND")

    def test_miniprogram_can_unbind_own_player(self):
        user = {
            "username": "tester",
            "display_name": "测试账号",
            "player_id": "player-s1",
            "linked_player_ids": ["player-s2"],
        }
        ctx = web_app.RequestContext(
            method="POST",
            path="/api/miniprogram/unbind-player",
            query={},
            form={"session_token": ["token"], "player_id": ["player-s1"]},
            files={},
            current_user=None,
            now_label="now",
        )
        response = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = headers

        with (
            patch.object(web_app, "load_session_username", return_value="tester"),
            patch.object(web_app, "load_users", return_value=[user]),
            patch.object(web_app, "load_validated_data", return_value=sample_data()),
            patch.object(web_app, "save_repository_state", return_value=[]),
            patch.object(web_app, "audit_action"),
        ):
            body = web_app.handle_miniprogram_unbind_player(ctx, start_response)
        payload = json.loads(body[0])
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(payload["user"]["bound_player_ids"], ["player-s2"])


if __name__ == "__main__":
    unittest.main()
