import unittest
from copy import deepcopy

import web_app
from validate_data import validate_matches
from web.features import console


class ScheduledFormatTests(unittest.TestCase):
    def setUp(self):
        self.match = dict(
            match_id="gz-lal4-260916-01", competition_name="逻辑与谎言广州赛区",
            season="广州赛区第四赛季", stage="placement", round=1, game_no=1,
            score_model="standard", scoring_rule={}, exclude_from_team_scores=False,
            played_on="2026-09-16", group_label="ABC", table_label="1号房",
            format="预女猎白", duration_minutes=0, winning_camp="draw",
            mvp_player_id="", svp_player_id="", scapegoat_player_id="",
            players=[], notes="预定赛程",
        )

    def test_preassigned_format_is_valid_pending_and_not_played(self):
        self.assertEqual(validate_matches([self.match], set(), set()), [])
        self.assertEqual(console._match_status(self.match), "pending")
        self.assertFalse(web_app.is_match_counted_as_played(self.match))

    def test_incomplete_results_are_not_accepted_as_scheduled(self):
        for change in ({"winning_camp": "werewolves"}, {"duration_minutes": 60},
                       {"players": [{}]}, {"players": None}, {"format": ""},
                       {"mvp_player_id": "fake-player"}):
            with self.subTest(change=change):
                candidate = {**deepcopy(self.match), **change}
                self.assertTrue(validate_matches([candidate], set(), set()))

    def test_legacy_placeholder_still_works(self):
        self.match["format"] = "待补录"
        self.assertEqual(validate_matches([self.match], set(), set()), [])
        self.assertEqual(console._match_status(self.match), "pending")

    def test_recorded_match_stays_recorded(self):
        self.match.update(winning_camp="werewolves", duration_minutes=60,
                          players=[{"player_id": "test-player"}])
        self.assertFalse(web_app.is_placeholder_match(self.match))
        self.assertTrue(web_app.is_match_counted_as_played(self.match))
        self.assertEqual(console._match_status(self.match), "recorded")


if __name__ == "__main__":
    unittest.main()
