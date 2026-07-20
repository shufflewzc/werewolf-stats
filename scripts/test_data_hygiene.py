import unittest

from web.features.data_hygiene import (
    _case_insensitive_duplicate_groups,
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
        self.assertNotIn("player-foo", {player["player_id"] for player in data["players"]})


if __name__ == "__main__":
    unittest.main()
