import unittest
from unittest.mock import patch

from web_app import build_search_api_payload


class MiniProgramSearchTests(unittest.TestCase):
    def test_player_search_uses_full_scoped_list_and_matches_aliases(self):
        ctx = object()
        players_payload = {
            "players": [
                {
                    "player_id": "player-105",
                    "display_name": "当前名称",
                    "aliases": ["东邪"],
                    "team_name": "测试战队",
                    "points_total": "12.00",
                    "win_rate": "50.0%",
                }
            ]
        }

        with patch(
            "web.features.player_page.build_players_api_payload",
            return_value=players_payload,
        ) as build_players, patch(
            "web.features.competitions.build_teams_api_payload",
            return_value={"teams": []},
        ), patch(
            "web.features.guilds.build_guilds_api_payload",
            return_value={"cards": []},
        ):
            payload = build_search_api_payload(ctx, "东邪")

        build_players.assert_called_once_with(ctx, paginate_results=False)
        self.assertEqual([item["id"] for item in payload["results"]], ["player-105"])


if __name__ == "__main__":
    unittest.main()
