import json
import unittest
from pathlib import Path
from unittest.mock import patch

import web_app
from generate_stats import build_player_rows


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


if __name__ == "__main__":
    unittest.main()
