import unittest
from unittest.mock import patch

import web_app


class TeamNameMatchingTests(unittest.TestCase):
    def setUp(self):
        self.competition_name = "京城大师赛广州公开赛"
        self.season_name = "2026广州公开赛S2"
        self.team = {
            "team_id": "jcds-gz-s-061",
            "name": "深圳锦鲤Club",
            "short_name": "深圳锦鲤Club",
            "competition_name": self.competition_name,
            "season_name": self.season_name,
            "members": ["player-player-208"],
        }
        self.player = {
            "player_id": "player-player-208",
            "display_name": "苹苹梨",
            "team_id": self.team["team_id"],
        }
        self.data = {
            "teams": [self.team],
            "players": [self.player],
            "matches": [],
        }

    def test_find_team_by_name_in_scope_is_case_insensitive(self):
        matched = web_app.find_team_by_name_in_scope(
            self.data,
            self.competition_name,
            self.season_name,
            "深圳锦鲤CLUB",
        )

        self.assertIs(matched, self.team)

    def test_match_import_reuses_canonical_team_and_player(self):
        incoming = {
            "competition_name": self.competition_name,
            "season": self.season_name,
            "stage": "regular_season",
            "players": [
                {
                    "player_name": "苹苹梨",
                    "team_name": "深圳锦鲤CLUB",
                }
            ],
        }

        with patch.object(
            web_app,
            "resolve_participation_mode_for_scope",
            return_value=web_app.PARTICIPATION_MODE_TEAM,
        ):
            errors = web_app.resolve_match_entities(self.data, [incoming])

        self.assertEqual(errors, [])
        self.assertEqual(len(self.data["teams"]), 1)
        self.assertEqual(len(self.data["players"]), 1)
        self.assertEqual(incoming["players"][0]["team_id"], self.team["team_id"])
        self.assertEqual(incoming["players"][0]["team_name"], self.team["name"])
        self.assertEqual(incoming["players"][0]["player_id"], self.player["player_id"])

    def test_manual_creation_rejects_case_only_duplicate(self):
        error = web_app.validate_team_creation(
            "深圳锦鲤CLUB",
            "深圳锦鲤CLUB",
            self.competition_name,
            self.season_name,
            [self.team],
        )

        self.assertEqual(error, "同一赛事赛季内已经存在同名战队。")


if __name__ == "__main__":
    unittest.main()
