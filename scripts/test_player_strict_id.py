import unittest
from types import SimpleNamespace

from web.features.player_page import _resolve_requested_player_id


class PlayerStrictIdTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "players": [
                {"player_id": "primary", "display_name": "同名选手"},
                {"player_id": "scoped", "display_name": "同名选手"},
            ],
            "matches": [
                {
                    "competition_name": "测试赛事",
                    "season": "S1",
                    "players": [{"player_id": "scoped", "team_id": "team-1"}],
                }
            ],
        }

    def test_strict_request_keeps_bound_player_id(self):
        ctx = SimpleNamespace(query={
            "competition": ["测试赛事"],
            "season": ["S1"],
            "strict_player_id": ["1"],
        })
        self.assertEqual(_resolve_requested_player_id(ctx, self.data, "primary"), "primary")

    def test_regular_request_keeps_existing_scope_mapping(self):
        ctx = SimpleNamespace(query={
            "competition": ["测试赛事"],
            "season": ["S1"],
        })
        self.assertEqual(_resolve_requested_player_id(ctx, self.data, "primary"), "scoped")


if __name__ == "__main__":
    unittest.main()
