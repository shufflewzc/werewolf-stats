import unittest
from unittest.mock import patch

import web_app
import season_grouping
from competition_meta import normalize_season_catalog_entry
from season_grouping import (
    EXPECTED_TEAM_COUNT,
    TARGET_COMPETITION_NAME,
    TARGET_SEASON_NAME,
    apply_placement_assignments,
    build_placement_assignment_preview,
    build_regular_season_team_leaderboards,
    build_team_leaderboard_sections,
    get_team_regular_season_group,
    is_target_scope,
    match_group_labels,
    placement_group_for_rank,
    progress_status,
)
from season_policy import build_tiered_league_policy, validate_season_policy
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
        self.assertTrue(
            all(
                all(badge["kind"] != "group" for badge in row["badges"])
                for rows in boards.values()
                for row in rows
            )
        )

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
        self.assertTrue(
            all(
                [badge["kind"] for badge in row.get("badges", [])] == ["group"]
                for row in leaderboards["teams"]
            )
        )
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

    def test_non_target_season_uses_configured_groups_sections_and_badges(self):
        competition_name = "测试城市联赛"
        season_name = "2027测试S3"
        policy = build_tiered_league_policy(
            group_labels=["A1", "A2", "B1", "B2"],
            group_size=2,
            sections=[
                {
                    "key": "ELITE",
                    "label": "精英组",
                    "title": "精英组积分榜",
                    "groups": ["A1", "A2"],
                },
                {
                    "key": "OPEN",
                    "label": "公开组",
                    "title": "公开组积分榜",
                    "groups": ["B1", "B2"],
                },
            ],
            progression={
                "ELITE": [
                    {"from": 1, "to": 1, "status": "直通", "style": "orange"},
                    {"from": 2, "to": 4, "status": "晋级", "style": "green"},
                ],
                "OPEN": [
                    {"from": 1, "to": 2, "status": "晋级", "style": "green"},
                    {"from": 3, "to": 4, "status": "淘汰", "style": "red"},
                ],
            },
        )
        teams = []
        players = []
        placement_matches = []
        for index in range(1, 9):
            team_id = f"custom-team-{index}"
            player_id = f"custom-player-{index}"
            teams.append(
                {
                    "team_id": team_id,
                    "name": f"自定义战队{index}",
                    "short_name": f"C{index}",
                    "logo": "",
                    "competition_name": competition_name,
                    "season_name": season_name,
                    "members": [player_id],
                    "stage_groups": [],
                }
            )
            players.append(
                {
                    "player_id": player_id,
                    "display_name": f"自定义选手{index}",
                    "team_id": team_id,
                }
            )
            placement_matches.append(
                {
                    "match_id": f"custom-placement-{index}",
                    "competition_name": competition_name,
                    "season": season_name,
                    "stage": "placement",
                    "round": index,
                    "game_no": 1,
                    "played_on": f"2027-01-{index:02d}",
                    "players": [
                        {
                            "player_id": player_id,
                            "team_id": team_id,
                            "points_earned": float(9 - index),
                            "result": "win",
                            "stance_result": "correct",
                        }
                    ],
                }
            )
        data = {
            "teams": teams,
            "players": players,
            "matches": placement_matches,
        }
        with patch.object(
            season_grouping,
            "resolve_season_policy_for_scope",
            return_value=policy,
        ):
            preview = build_placement_assignment_preview(
                data,
                competition_name,
                season_name,
            )
            self.assertTrue(preview["ready"])
            self.assertEqual(
                [row["proposed_group"] for row in preview["rows"]],
                ["A1", "A1", "A2", "A2", "B1", "B1", "B2", "B2"],
            )
            apply_placement_assignments(
                data,
                preview["revision"],
                competition_name,
                season_name,
            )
            data["matches"].append(
                {
                    "match_id": "custom-regular",
                    "competition_name": competition_name,
                    "season": season_name,
                    "stage": "regular_season",
                    "round": 1,
                    "game_no": 1,
                    "played_on": "2027-02-01",
                    "players": [
                        {
                            "player_id": team["members"][0],
                            "team_id": team["team_id"],
                            "points_earned": float(9 - index),
                            "result": "win",
                            "stance_result": "correct",
                        }
                        for index, team in enumerate(teams, start=1)
                    ],
                }
            )
            sections = build_team_leaderboard_sections(
                data,
                competition_name,
                season_name,
                "regular_season",
            )
        self.assertEqual(
            [(section["key"], section["title"]) for section in sections],
            [("ELITE", "精英组积分榜"), ("OPEN", "公开组积分榜")],
        )
        self.assertEqual([len(section["rows"]) for section in sections], [4, 4])
        self.assertEqual(
            [badge["text"] for badge in sections[0]["rows"][0]["badges"]],
            ["A1", "直通"],
        )
        self.assertEqual(
            sections[1]["rows"][2]["progress_status"],
            "淘汰",
        )

    def test_policy_validation_rejects_overlapping_rank_ranges(self):
        policy = build_tiered_league_policy(
            group_labels=["A", "B"],
            group_size=2,
            sections=[
                {
                    "key": "ALL",
                    "label": "全部",
                    "title": "全部榜",
                    "groups": ["A", "B"],
                }
            ],
            progression={},
        )
        policy["stages"]["placement"]["grouping"]["ranges"][1]["from"] = 2
        errors = validate_season_policy(policy)
        self.assertTrue(any("被多个分组区间覆盖" in error for error in errors))

    def test_tiered_policy_keeps_whitelisted_ranking_mode(self):
        policy = build_tiered_league_policy(
            group_labels=["A"],
            group_size=4,
            sections=[
                {
                    "key": "A",
                    "label": "A组",
                    "title": "A组榜",
                    "groups": ["A"],
                }
            ],
            progression={},
            ranking_mode="win_rate",
        )
        self.assertEqual(
            policy["stages"]["regular_season"]["standings"]["ranking"],
            "win_rate",
        )

    def test_legacy_s2_catalog_entry_is_migrated_to_explicit_policy(self):
        entry = normalize_season_catalog_entry(
            {
                "competition_name": TARGET_COMPETITION_NAME,
                "season_name": TARGET_SEASON_NAME,
            }
        )
        self.assertIsNotNone(entry)
        self.assertFalse(entry["season_policy"].get("inherit", False))
        self.assertEqual(entry["season_policy"]["preset"], "tiered_league")
        self.assertEqual(
            set(entry["season_policy"]["stages"]),
            {"placement", "regular_season"},
        )

        ordinary_entry = normalize_season_catalog_entry(
            {
                "competition_name": "普通赛事",
                "season_name": "普通赛季",
            }
        )
        self.assertTrue(ordinary_entry["season_policy"].get("inherit"))


if __name__ == "__main__":
    unittest.main()
