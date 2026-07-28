import unittest
from unittest.mock import patch

import web_app
from season_grouping import (
    EXPECTED_TEAM_COUNT,
    TARGET_COMPETITION_NAME,
    TARGET_SEASON_NAME,
    apply_placement_assignments,
    build_placement_assignment_preview,
    build_regular_season_team_leaderboards,
    get_team_regular_season_group,
    is_target_scope,
    match_group_labels,
    placement_group_for_rank,
    progress_status,
)
from web.features import match_page


def build_sample_data():
    teams = []
    players = []
    matches = []
    for index in range(1, EXPECTED_TEAM_COUNT + 1):
        team_id = f"team-{index:02d}"
        player_id = f"player-{index:02d}"
        teams.append(
            {
                "team_id": team_id,
                "name": f"战队{index:02d}",
                "short_name": f"T{index:02d}",
                "logo": "",
                "competition_name": TARGET_COMPETITION_NAME,
                "season_name": TARGET_SEASON_NAME,
                "members": [player_id],
                "stage_groups": [{"stage": "playoffs", "group_label": "保留组"}],
            }
        )
        players.append(
            {
                "player_id": player_id,
                "display_name": f"选手{index:02d}",
                "team_id": team_id,
                "photo": "",
                "is_star_player": False,
            }
        )
        matches.append(
            {
                "match_id": f"placement-{index:02d}",
                "competition_name": TARGET_COMPETITION_NAME,
                "season": TARGET_SEASON_NAME,
                "stage": "placement",
                "round": index,
                "game_no": 1,
                "played_on": f"2026-07-{index:02d}" if index <= 31 else "2026-08-01",
                "players": [
                    {
                        "player_id": player_id,
                        "team_id": team_id,
                        "points_earned": float(EXPECTED_TEAM_COUNT - index + 1),
                        "result": "win" if index % 2 else "loss",
                        "stance_result": "correct",
                    }
                ],
            }
        )
    return {"teams": teams, "players": players, "matches": matches}


class SeasonGroupingTests(unittest.TestCase):
    def test_scope_is_strictly_limited_to_target_s2(self):
        self.assertTrue(is_target_scope(TARGET_COMPETITION_NAME, TARGET_SEASON_NAME))
        self.assertFalse(is_target_scope(TARGET_COMPETITION_NAME, "2026广州公开赛S1"))
        self.assertFalse(is_target_scope("飞行杯", TARGET_SEASON_NAME))

    def test_placement_rank_boundaries(self):
        expected = {
            1: "S1",
            4: "S1",
            5: "S2",
            8: "S2",
            9: "S3",
            12: "S3",
            13: "S4",
            16: "S4",
            17: "F1",
            20: "F1",
            21: "F2",
            24: "F2",
            25: "F3",
            28: "F3",
            29: "F4",
            32: "F4",
        }
        for rank, group_label in expected.items():
            self.assertEqual(placement_group_for_rank(rank), group_label)
        self.assertEqual(placement_group_for_rank(0), "")
        self.assertEqual(placement_group_for_rank(33), "")

    def test_preview_and_apply_persist_exactly_four_teams_per_group(self):
        data = build_sample_data()
        preview = build_placement_assignment_preview(data)
        self.assertTrue(preview["ready"])
        self.assertEqual(preview["team_count"], 32)
        counts = {}
        for row in preview["rows"]:
            counts[row["proposed_group"]] = counts.get(row["proposed_group"], 0) + 1
        self.assertEqual(set(counts.values()), {4})

        updated_count, _ = apply_placement_assignments(data, preview["revision"])
        self.assertEqual(updated_count, 32)
        self.assertEqual(get_team_regular_season_group(data["teams"][0]), "S1")
        self.assertEqual(get_team_regular_season_group(data["teams"][-1]), "F4")
        self.assertIn(
            {"stage": "playoffs", "group_label": "保留组"},
            data["teams"][0]["stage_groups"],
        )

    def test_apply_rejects_stale_preview(self):
        data = build_sample_data()
        preview = build_placement_assignment_preview(data)
        data["matches"][-1]["players"][0]["points_earned"] = 1000
        with self.assertRaisesRegex(ValueError, "排行榜已变化"):
            apply_placement_assignments(data, preview["revision"])

    def test_regular_boards_have_sixteen_teams_and_status_boundaries(self):
        data = build_sample_data()
        preview = build_placement_assignment_preview(data)
        apply_placement_assignments(data, preview["revision"])
        participants = []
        for index, team in enumerate(data["teams"], start=1):
            tier_rank = index if index <= 16 else index - 16
            participants.append(
                {
                    "player_id": team["members"][0],
                    "team_id": team["team_id"],
                    "points_earned": float(17 - tier_rank),
                    "result": "win",
                    "stance_result": "correct",
                }
            )
        data["matches"].append(
            {
                "match_id": "regular-1",
                "competition_name": TARGET_COMPETITION_NAME,
                "season": TARGET_SEASON_NAME,
                "stage": "regular_season",
                "round": 1,
                "game_no": 1,
                "players": participants,
            }
        )
        boards = build_regular_season_team_leaderboards(data)
        self.assertEqual(len(boards["S"]), 16)
        self.assertEqual(len(boards["F"]), 16)
        self.assertEqual([row["progress_status"] for row in boards["S"][:2]], ["直通", "直通"])
        self.assertEqual(boards["S"][2]["progress_status"], "晋级")
        self.assertEqual(boards["S"][10]["progress_status"], "晋级")
        self.assertEqual(boards["S"][11]["progress_status"], "淘汰")
        self.assertEqual(boards["F"][0]["progress_status"], "直通")
        self.assertEqual(boards["F"][1]["progress_status"], "晋级")
        self.assertEqual(boards["F"][7]["progress_status"], "晋级")
        self.assertEqual(boards["F"][8]["progress_status"], "淘汰")

    def test_progress_status_boundaries(self):
        self.assertEqual(progress_status("S", 2), "直通")
        self.assertEqual(progress_status("S", 3), "晋级")
        self.assertEqual(progress_status("S", 11), "晋级")
        self.assertEqual(progress_status("S", 12), "淘汰")
        self.assertEqual(progress_status("F", 1), "直通")
        self.assertEqual(progress_status("F", 2), "晋级")
        self.assertEqual(progress_status("F", 8), "晋级")
        self.assertEqual(progress_status("F", 9), "淘汰")

    def test_placement_group_is_team_only_and_personal_boards_stay_unchanged(self):
        data = build_sample_data()
        preview = build_placement_assignment_preview(data)
        apply_placement_assignments(data, preview["revision"])
        placement_matches = [
            match for match in data["matches"] if match["stage"] == "placement"
        ]
        leaderboards = web_app.build_dashboard_leaderboards(
            data,
            placement_matches,
            TARGET_COMPETITION_NAME,
            TARGET_SEASON_NAME,
        )
        self.assertTrue(all(row.get("regular_season_group") for row in leaderboards["teams"]))
        for board_name in ("players", "mvp", "svp"):
            self.assertTrue(
                all("regular_season_group" not in row for row in leaderboards[board_name])
            )

    def test_match_collects_multiple_subgroups_without_touching_other_scopes(self):
        data = build_sample_data()
        preview = build_placement_assignment_preview(data)
        apply_placement_assignments(data, preview["revision"])
        target_match = {
            "competition_name": TARGET_COMPETITION_NAME,
            "season": TARGET_SEASON_NAME,
            "stage": "regular_season",
            "players": [
                {"team_id": "team-01"},
                {"team_id": "team-09"},
                {"team_id": "team-02"},
            ],
        }
        self.assertEqual(match_group_labels(data, target_match), ["S1", "S3"])
        other_match = {
            **target_match,
            "season": "2026广州公开赛S1",
        }
        self.assertEqual(match_group_labels(data, other_match), [])

    def test_target_match_api_exposes_groups_on_match_teams_and_participants(self):
        data = build_sample_data()
        preview = build_placement_assignment_preview(data)
        apply_placement_assignments(data, preview["revision"])
        regular_match = {
            "match_id": "regular-api",
            "competition_name": TARGET_COMPETITION_NAME,
            "season": TARGET_SEASON_NAME,
            "stage": "regular_season",
            "round": 1,
            "game_no": 1,
            "played_on": "2026-08-01",
            "winning_camp": "villagers",
            "scoring_rule": {"version": 1, "score_model": "standard", "components": []},
            "players": [
                {
                    "seat": 1,
                    "player_id": "player-01",
                    "team_id": "team-01",
                    "role": "预言家",
                    "camp": "villagers",
                    "result": "win",
                    "points_earned": 10,
                    "stance_result": "correct",
                },
                {
                    "seat": 2,
                    "player_id": "player-09",
                    "team_id": "team-09",
                    "role": "狼人",
                    "camp": "werewolves",
                    "result": "loss",
                    "points_earned": 3,
                    "stance_result": "incorrect",
                },
            ],
        }
        data["matches"].append(regular_match)
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/matches/regular-api",
            query={},
            form={},
            files={},
            current_user=None,
            now_label="now",
        )
        with (
            patch.object(match_page, "load_validated_data", return_value=data),
            patch.object(match_page, "build_match_score_predictions", return_value=[]),
        ):
            payload = match_page.build_match_api_payload(ctx, "regular-api")
        self.assertEqual(payload["match"]["group_labels"], ["S1", "S3"])
        self.assertEqual(
            [row["regular_season_group"] for row in payload["team_scores"]],
            ["S1", "S3"],
        )
        self.assertEqual(
            [row["regular_season_group"] for row in payload["participants"]],
            ["S1", "S3"],
        )

    def test_target_status_does_not_generate_postseason_lists(self):
        data = build_sample_data()
        preview = build_placement_assignment_preview(data)
        apply_placement_assignments(data, preview["revision"])
        regular_match = {
            "match_id": "regular-display-only",
            "competition_name": TARGET_COMPETITION_NAME,
            "season": TARGET_SEASON_NAME,
            "stage": "regular_season",
            "group_label": "S组",
            "round": 1,
            "game_no": 1,
            "players": [
                {
                    "player_id": "player-01",
                    "team_id": "team-01",
                    "points_earned": 10,
                    "result": "win",
                    "stance_result": "correct",
                }
            ],
        }
        context = web_app.build_dashboard_promotion_context(
            data,
            [regular_match],
            TARGET_COMPETITION_NAME,
            TARGET_SEASON_NAME,
            None,
            None,
        )
        self.assertEqual(context["final_rows"], [])
        self.assertEqual(context["playoff_rows"], [])
        self.assertIn("不自动生成季后赛名单", context["rules"][0])


if __name__ == "__main__":
    unittest.main()
