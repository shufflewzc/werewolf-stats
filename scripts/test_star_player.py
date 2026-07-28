import json
import unittest
from pathlib import Path
from unittest.mock import patch

import web_app
from generate_stats import build_player_rows
from web.features import match_page


ROOT = Path(__file__).resolve().parents[1]


def sample_data():
    return {
        "players": [
            {
                "player_id": "star",
                "display_name": "明星甲",
                "team_id": "team",
                "photo": "assets/players/default-player.svg",
                "aliases": [],
                "active": True,
                "is_star_player": True,
                "joined_on": "2026-01-01",
                "notes": "",
            },
            {
                "player_id": "regular",
                "display_name": "普通乙",
                "team_id": "team",
                "photo": "assets/players/default-player.svg",
                "aliases": [],
                "active": True,
                "is_star_player": False,
                "joined_on": "2026-01-01",
                "notes": "",
            },
        ],
        "teams": [
            {
                "team_id": "team",
                "name": "测试队",
                "short_name": "测试",
                "competition_name": "测试赛事",
                "season_name": "S1",
            }
        ],
        "matches": [],
    }


class StarPlayerTests(unittest.TestCase):
    def test_player_rows_keep_star_identity_without_affecting_rank(self):
        rows = build_player_rows(sample_data(), "测试赛事", "S1")
        by_id = {row["player_id"]: row for row in rows}
        self.assertIs(by_id["star"]["is_star_player"], True)
        self.assertIs(by_id["regular"]["is_star_player"], False)

    def test_scoped_current_player_returns_star_flag(self):
        result = web_app.resolve_user_player_for_scope(
            sample_data(),
            {"player_id": "star", "linked_player_ids": []},
            "测试赛事",
            "S1",
        )
        self.assertEqual(result["status"], "matched")
        self.assertIs(result["player"]["is_star_player"], True)

    def test_batch_label_endpoint_returns_boolean_flags(self):
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/miniprogram/player-labels",
            query={"player_ids": ["star,regular"]},
            form={},
            files={},
            current_user=None,
            now_label="now",
        )
        response = {}

        def start_response(status, headers):
            response["status"] = status
            response["headers"] = headers

        with patch.object(web_app, "load_validated_data", return_value=sample_data()):
            body = web_app.handle_miniprogram_player_labels(ctx, start_response)
        payload = json.loads(body[0])
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(
            {item["player_id"]: item["is_star_player"] for item in payload["players"]},
            {"star": True, "regular": False},
        )

    def test_all_player_identity_pages_use_shared_badge(self):
        pages = [
            "players/players.wxml",
            "player-detail/player-detail.wxml",
            "match-detail/match-detail.wxml",
            "dashboard/dashboard.wxml",
            "predictions/predictions.wxml",
            "day-detail/day-detail.wxml",
            "team-detail/team-detail.wxml",
            "compare/compare.wxml",
            "mine/mine.wxml",
            "player-bind/player-bind.wxml",
        ]
        for page in pages:
            content = (ROOT / "miniprogram/pages" / page).read_text(encoding="utf-8")
            self.assertIn("star-player-badge", content, page)

    def test_match_detail_payload_marks_star_participants_and_awards(self):
        data = sample_data()
        data["matches"] = [
            {
                "match_id": "match-1",
                "competition": "测试赛事",
                "season": "S1",
                "stage": "regular",
                "round": 1,
                "game_no": 1,
                "played_on": "2026-01-01",
                "winning_camp": "werewolves",
                "mvp_player_id": "star",
                "svp_player_id": "regular",
                "players": [
                    {
                        "seat": 1,
                        "player_id": "star",
                        "team_id": "team",
                        "role": "狼人",
                        "camp": "werewolves",
                        "result": "win",
                        "points_earned": 10,
                    },
                    {
                        "seat": 2,
                        "player_id": "regular",
                        "team_id": "team",
                        "role": "预言家",
                        "camp": "villagers",
                        "result": "loss",
                        "points_earned": 3,
                    },
                ],
            }
        ]
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/matches/match-1",
            query={},
            form={},
            files={},
            current_user=None,
            now_label="now",
        )
        with (
            patch.object(match_page, "load_validated_data", return_value=data),
            patch.object(match_page, "build_match_score_predictions", return_value=[]),
        ):
            payload = match_page.build_match_api_payload(ctx, "match-1")

        self.assertEqual(
            {item["player_id"]: item["is_star_player"] for item in payload["participants"]},
            {"star": True, "regular": False},
        )
        self.assertIs(payload["awards"][0]["is_star_player"], True)
        self.assertIs(payload["awards"][1]["is_star_player"], False)

    def test_recent_match_cards_open_the_match_detail_page(self):
        for page in ["player-detail", "team-detail"]:
            wxml = (ROOT / "miniprogram/pages" / page / f"{page}.wxml").read_text(encoding="utf-8")
            javascript = (ROOT / "miniprogram/pages" / page / f"{page}.js").read_text(encoding="utf-8")
            self.assertIn('bindtap="openMatch"', wxml, page)
            self.assertIn('data-match-id="{{item.match_id}}"', wxml, page)
            self.assertIn("/pages/match-detail/match-detail?match_id=", javascript, page)


if __name__ == "__main__":
    unittest.main()
