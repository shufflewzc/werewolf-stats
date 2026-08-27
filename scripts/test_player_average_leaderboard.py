from __future__ import annotations

from copy import deepcopy
import unittest

from generate_stats import build_player_average_rows


class PlayerAverageLeaderboardTests(unittest.TestCase):
    def test_average_board_filters_inactive_players_and_keeps_total_rows_unchanged(self):
        total_rows = [
            {
                "player_id": "total-first",
                "display_name": "总分优先",
                "games_played": 4,
                "points_earned_total": 20.0,
                "average_points": 5.0,
                "win_rate": 0.75,
                "stance_rate": 0.8,
                "rank": 1,
            },
            {
                "player_id": "average-first",
                "display_name": "场均优先",
                "games_played": 1,
                "points_earned_total": 10.0,
                "average_points": 10.0,
                "win_rate": 0.0,
                "stance_rate": 0.0,
                "rank": 2,
            },
            {
                "player_id": "inactive",
                "display_name": "未出场",
                "games_played": 0,
                "points_earned_total": 0.0,
                "average_points": 0.0,
                "win_rate": 0.0,
                "stance_rate": 0.0,
                "rank": 0,
            },
        ]
        original_rows = deepcopy(total_rows)

        average_rows = build_player_average_rows(total_rows)

        self.assertEqual(
            [row["player_id"] for row in average_rows],
            ["average-first", "total-first"],
        )
        self.assertEqual([row["rank"] for row in average_rows], [1, 2])
        self.assertEqual(total_rows, original_rows)

    def test_average_board_uses_documented_tie_breakers(self):
        rows = [
            {
                "player_id": "name-last",
                "display_name": "B",
                "games_played": 2,
                "points_earned_total": 10.0,
                "average_points": 5.0,
                "win_rate": 0.5,
                "stance_rate": 0.5,
                "rank": 1,
            },
            {
                "player_id": "stance-first",
                "display_name": "丙",
                "games_played": 2,
                "points_earned_total": 10.0,
                "average_points": 5.0,
                "win_rate": 0.5,
                "stance_rate": 1.0,
                "rank": 2,
            },
            {
                "player_id": "name-first",
                "display_name": "A",
                "games_played": 2,
                "points_earned_total": 10.0,
                "average_points": 5.0,
                "win_rate": 0.5,
                "stance_rate": 0.5,
                "rank": 3,
            },
            {
                "player_id": "total-first",
                "display_name": "丁",
                "games_played": 3,
                "points_earned_total": 15.0,
                "average_points": 5.0,
                "win_rate": 0.0,
                "stance_rate": 0.0,
                "rank": 4,
            },
        ]

        average_rows = build_player_average_rows(rows)

        self.assertEqual(
            [row["player_id"] for row in average_rows],
            ["total-first", "stance-first", "name-first", "name-last"],
        )


if __name__ == "__main__":
    unittest.main()
