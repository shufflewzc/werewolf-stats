from __future__ import annotations

import unittest

from export_public_dataset import (
    DatasetExportError,
    available_scopes,
    select_metadata,
    select_public_data,
)


class PublicDatasetExportTests(unittest.TestCase):
    @staticmethod
    def scope_data(competition: str, season: str, suffix: str) -> dict:
        team_id = f"team-{suffix}"
        player_id = f"player-{suffix}"
        return {
            "teams": [
                {
                    "team_id": team_id,
                    "name": f"战队{suffix}",
                    "short_name": suffix,
                    "logo": "assets/teams/default-team.svg",
                    "active": True,
                    "founded_on": "2026-01-01",
                    "competition_name": competition,
                    "season_name": season,
                    "guild_id": "private-guild",
                    "captain_player_id": player_id,
                    "stage_groups": [],
                    "members": [player_id],
                    "notes": "",
                }
            ],
            "players": [
                {
                    "player_id": player_id,
                    "display_name": f"选手{suffix}",
                    "team_id": team_id,
                    "photo": "assets/players/default-player.svg",
                    "aliases": [],
                    "active": True,
                    "is_star_player": False,
                    "profile_status": "verified",
                    "created_source": "manual",
                    "joined_on": "2026-01-01",
                    "notes": "",
                }
            ],
            "matches": [],
            "season_player_dimension_stats": [],
            "season_team_dimension_stats": [],
        }

    @staticmethod
    def combine(*datasets: dict) -> dict:
        return {
            key: [item for dataset in datasets for item in dataset.get(key, [])]
            for key in (
                "teams",
                "players",
                "matches",
                "season_player_dimension_stats",
                "season_team_dimension_stats",
            )
        }

    def test_available_scopes_include_catalog_only_seasons(self):
        data = self.scope_data("赛事A", "S1", "s1")
        scopes = available_scopes(
            data,
            [{"competition_name": "赛事A", "season_name": "S2"}],
        )
        self.assertEqual(scopes, [("赛事A", "S1"), ("赛事A", "S2")])

    def test_select_one_scope_keeps_only_reference_closure(self):
        s1 = self.scope_data("赛事A", "S1", "s1")
        s2 = self.scope_data("赛事A", "S2", "s2")
        selected = select_public_data(self.combine(s1, s2), {("赛事A", "S1")})
        self.assertEqual([team["team_id"] for team in selected["teams"]], ["team-s1"])
        self.assertEqual(selected["teams"][0]["guild_id"], "")
        self.assertEqual([player["player_id"] for player in selected["players"]], ["player-s1"])

    def test_npc_participant_and_award_do_not_require_player_profile(self):
        data = self.scope_data("赛事A", "S1", "s1")
        data["matches"] = [
            {
                "match_id": "aa-s-260101-01",
                "competition_name": "赛事A",
                "season": "S1",
                "mvp_player_id": "NPC",
                "svp_player_id": "",
                "scapegoat_player_id": "",
                "played_on": "2026-01-01",
                "round": 1,
                "game_no": 1,
                "players": [{"player_id": "NPC", "team_id": "team-s1"}],
            }
        ]
        selected = select_public_data(data, {("赛事A", "S1")})
        self.assertEqual([player["player_id"] for player in selected["players"]], ["player-s1"])

    def test_cross_scope_team_reference_is_rejected(self):
        s1 = self.scope_data("赛事A", "S1", "s1")
        s2 = self.scope_data("赛事A", "S2", "s2")
        s1["matches"] = [
            {
                "match_id": "aa-s1-260101-01",
                "competition_name": "赛事A",
                "season": "S1",
                "played_on": "2026-01-01",
                "round": 1,
                "game_no": 1,
                "players": [{"player_id": "player-s1", "team_id": "team-s2"}],
            }
        ]
        with self.assertRaisesRegex(DatasetExportError, "找不到的战队引用"):
            select_public_data(self.combine(s1, s2), {("赛事A", "S1")})

    def test_metadata_is_filtered_to_selected_scope(self):
        metadata = select_metadata(
            series_catalog=[
                {"competition_name": "赛事A", "created_by": "private-admin"},
                {"competition_name": "赛事B"},
            ],
            season_catalog=[
                {
                    "competition_name": "赛事A",
                    "season_name": "S1",
                    "series_slug": "a",
                    "registered_team_ids": ["team-s1"],
                },
                {
                    "competition_name": "赛事A",
                    "season_name": "S2",
                    "series_slug": "a",
                    "registered_team_ids": ["team-s2"],
                },
            ],
            scoring_rule_templates=[{"slug": "standard"}],
            selected_scopes={("赛事A", "S1")},
            selected_team_ids={"team-s1"},
        )
        self.assertEqual(len(metadata["series_catalog"]), 1)
        self.assertNotIn("created_by", metadata["series_catalog"][0])
        self.assertEqual(len(metadata["season_catalog"]), 1)
        self.assertEqual(metadata["scoring_rule_templates"], [{"slug": "standard"}])


if __name__ == "__main__":
    unittest.main()
