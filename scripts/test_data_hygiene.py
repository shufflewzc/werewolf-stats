import unittest

from web.features.data_hygiene import (
    _case_insensitive_duplicate_groups,
    _delete_empty_player,
    _delete_player_impact,
    _merge_player,
    _player_season_scope_map,
)


def build_data():
    return {
        "players": [
            {"player_id": "player-foo", "display_name": "Foo", "team_id": "team-a"},
            {"player_id": "player-foo-2", "display_name": "foo", "team_id": "team-b"},
            {"player_id": "player-foo-old", "display_name": "FOO", "team_id": "team-old"},
        ],
        "teams": [
            {
                "team_id": "team-a",
                "name": "A",
                "competition_name": "赛事",
                "season_name": "S2",
                "members": ["player-foo"],
                "captain_player_id": "player-foo",
            },
            {
                "team_id": "team-b",
                "name": "B",
                "competition_name": "赛事",
                "season_name": "S2",
                "members": ["player-foo-2"],
                "captain_player_id": None,
            },
            {
                "team_id": "team-old",
                "name": "Old",
                "competition_name": "赛事",
                "season_name": "S1",
                "members": ["player-foo-old"],
                "captain_player_id": None,
            },
        ],
        "matches": [
            {
                "competition_name": "赛事",
                "season": "S2",
                "players": [{"player_id": "player-foo", "player_name": "Foo"}],
                "mvp_player_id": "player-foo",
                "svp_player_id": "",
                "scapegoat_player_id": "",
            }
        ],
        "season_player_dimension_stats": [],
    }


class DataHygieneTests(unittest.TestCase):
    def test_delete_empty_player_rejects_captain(self):
        data = build_data()
        data["matches"] = []
        player = data["players"][0]
        player["profile_status"] = "auto_created"

        with self.assertRaisesRegex(ValueError, "担任战队队长"):
            _delete_empty_player(data, [], "player-foo")

        self.assertIn(
            "player-foo",
            {item["player_id"] for item in data["players"]},
        )

    def test_delete_empty_player_removes_non_captain_roster_reference(self):
        data = build_data()
        data["matches"] = []
        player = data["players"][1]
        player["profile_status"] = "auto_created"

        impact = _delete_empty_player(data, [], "player-foo-2")

        self.assertEqual(impact["roster_team_ids"], ["team-b"])
        self.assertNotIn(
            "player-foo-2",
            {item["player_id"] for item in data["players"]},
        )
        self.assertEqual(data["teams"][1]["members"], [])

    def test_delete_impact_detects_dimension_and_account_references(self):
        data = build_data()
        data["season_player_dimension_stats"] = [{"player_id": "player-foo-2"}]
        users = [{"player_id": "player-foo-2", "linked_player_ids": []}]

        impact = _delete_player_impact(data, users, "player-foo-2")

        self.assertEqual(impact["bindings"], 1)
        self.assertEqual(impact["dimension_rows"], 1)

    def test_case_only_names_are_grouped_within_the_same_season(self):
        data = build_data()
        groups = _case_insensitive_duplicate_groups(
            data["players"],
            _player_season_scope_map(data),
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], ("赛事", "S2"))
        self.assertEqual(
            {player["player_id"] for player in groups[0][1]},
            {"player-foo", "player-foo-2"},
        )

    def test_merge_rejects_players_from_different_seasons(self):
        with self.assertRaisesRegex(ValueError, "同一赛事赛季"):
            _merge_player(
                build_data(),
                [],
                "player-foo-old",
                "player-foo-2",
                "赛事",
                "S2",
            )

    def test_merge_moves_same_season_references(self):
        data = build_data()
        users = [{"player_id": "player-foo", "linked_player_ids": ["player-foo"]}]

        moved = _merge_player(
            data,
            users,
            "player-foo",
            "player-foo-2",
            "赛事",
            "S2",
        )

        self.assertEqual(moved, 1)
        self.assertEqual(data["matches"][0]["players"][0]["player_id"], "player-foo-2")
        self.assertEqual(data["matches"][0]["mvp_player_id"], "player-foo-2")
        self.assertEqual(users[0]["player_id"], "player-foo-2")
        self.assertTrue(users[0]["user_player_bindings_write"])
        self.assertNotIn("player-foo", {player["player_id"] for player in data["players"]})


if __name__ == "__main__":
    unittest.main()
