import unittest
from unittest.mock import patch

import web_app
from web.features import matches


class DimensionImportTests(unittest.TestCase):
    def setUp(self):
        self.competition_name = "测试赛事"
        self.season_name = "S1"
        self.data = {
            "teams": [
                {
                    "team_id": "team-1",
                    "name": "测试战队",
                    "competition_name": self.competition_name,
                    "season_name": self.season_name,
                }
            ],
            "players": [
                {
                    "player_id": "player-1",
                    "display_name": "真实选手",
                    "team_id": "team-1",
                }
            ],
            "matches": [],
        }
        self.rows = [
            {"选手姓名": value, "所属战队": "不存在的战队"}
            for value in ["NPC", "npc", "NpC", " npc "]
        ] + [
            {
                "比赛日期": "2026-08-01",
                "所属战队": "测试战队",
                "座位号": "1",
                "选手姓名": "真实选手",
                "当日积分": "5",
            }
        ]

    def test_player_dimension_rows_skip_case_insensitive_npc(self):
        parsed = matches.build_player_dimension_stats_from_rows(
            self.data,
            self.competition_name,
            self.season_name,
            self.rows,
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["player_id"], "player-1")
        self.assertEqual(parsed[0]["daily_points"], 5.0)

    def test_dimension_import_reports_skipped_npc_rows(self):
        ctx = web_app.RequestContext(
            method="POST",
            path="/matches/new",
            query={},
            form={},
            files={},
            current_user=None,
            now_label="now",
        )
        with patch.object(
            matches,
            "read_optional_sheet_rows",
            side_effect=[self.rows, []],
        ), patch.object(
            matches, "can_manage_competition_action", return_value=True
        ), patch.object(
            matches, "validate_match_competition_selection", return_value=""
        ), patch.object(
            matches, "validate_match_season_selection", return_value=""
        ):
            player_rows, team_rows, message = matches.import_dimension_stats_from_excel(
                ctx,
                self.data,
                object(),
                self.competition_name,
                self.season_name,
            )

        self.assertEqual(len(player_rows or []), 1)
        self.assertEqual(team_rows, [])
        self.assertIn("已自动跳过 NPC 4 条", message)

    def test_dimension_import_matches_team_name_case_insensitively(self):
        self.data["teams"][0]["name"] = "深圳锦鲤Club"
        rows = [
            {
                "比赛日期": "2026-08-09",
                "所属战队": "深圳锦鲤CLUB",
                "座位号": "5",
                "选手姓名": "真实选手",
                "当日积分": "0.5",
            }
        ]

        parsed = matches.build_player_dimension_stats_from_rows(
            self.data,
            self.competition_name,
            self.season_name,
            rows,
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["team_id"], "team-1")
        self.assertEqual(parsed[0]["player_id"], "player-1")


if __name__ == "__main__":
    unittest.main()
