import unittest
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

from web.features import matches
from web_app import RequestContext
from validate_data import validate_matches


class MatchEditSaveTests(unittest.TestCase):
    def test_resolved_form_helpers_are_removed_before_validation(self):
        current = matches.build_placeholder_match(
            "测试赛事", "S2", "finals", 1, 1, "2026-09-09", "", "1号房"
        )
        current.update(match_id="gz-s-260909-01", winning_camp="werewolves", format="预女猎白", duration_minutes=60)
        components = dict(result_points=0, vote_points=0, behavior_points=0,
                          special_points=-1, adjustment_points=-10)
        participant = dict(player_id="player-test", team_id="team-test", seat=3,
                           role="预言家", camp="villagers", result="loss", points_earned=-11,
                           **components, score_breakdown=components.copy(),
                           stance_result="none", notes="背锅-1；追加扣分-10")
        current["players"] = [participant]
        current["scapegoat_player_id"] = "player-test"
        updated = deepcopy(current)
        for award in ("mvp", "svp", "scapegoat"):
            updated[f"{award}_player_name"] = "测试选手" if award == "scapegoat" else ""
            updated[f"{award}_player_ref"] = "0" if award == "scapegoat" else ""
        updated["players"][0].update(player_name="测试选手", team_name="测试战队")
        untouched = deepcopy(current)
        untouched.update(match_id="gz-s-260909-02", game_no=2)
        data = {"matches": [current, untouched]}
        saved = []

        def save(state, users):
            errors = validate_matches(state["matches"], {"team-test"}, {"player-test"})
            self.assertEqual([], errors)
            saved.extend(deepcopy(state["matches"]))
            return []

        ctx = RequestContext(method="POST", path="/matches/gz-s-260909-01/edit",
                             query={}, form={}, files={}, current_user={"role": "admin"}, now_label="")
        with ExitStack() as stack:
            for name, value in {
                "load_validated_data": data, "parse_match_form": updated,
                "resolve_match_entities": [], "require_competition_action": None,
                "validate_match_competition_selection": "", "validate_match_season_selection": "",
                "validate_match_stage_selection": "", "load_users": [],
                "ensure_placeholder_players_for_matches": [],
                "ensure_placeholder_users_for_player_ids": [],
            }.items():
                stack.enter_context(patch.object(matches, name, return_value=value))
            stack.enter_context(patch.object(matches.legacy, "canonicalize_match_ids",
                side_effect=lambda rows, **kwargs: (rows, current["match_id"])))
            stack.enter_context(patch.object(matches, "save_repository_state", side_effect=save))
            matches.handle_match_edit(ctx, lambda *args: None, current["match_id"])

        self.assertEqual(current, saved[0])
        self.assertEqual(untouched, saved[1])
        self.assertIn("player_name", updated["players"][0])


if __name__ == "__main__":
    unittest.main()
