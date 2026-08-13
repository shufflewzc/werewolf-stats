from __future__ import annotations

import json
import random
import unittest
from collections import Counter, defaultdict
from copy import deepcopy
from unittest.mock import patch

import web_app
from web.features.match_page import (
    _handle_prediction_day_scenario_admin,
    _prediction_day_scope,
    _prediction_day_scenario_admin_html,
    _prediction_season_players,
    _prediction_season_teams,
    normalize_prediction_day_scenario,
    prediction_day_scenario_key,
)
from web.features.prediction_simulator import (
    SEED_COMPETITION,
    SEED_END_DATE,
    SEED_SEASON,
    build_history_model,
    draw_role_assignment,
    score_without_adjustment,
    simulate_three_game_day,
)


class ThreeGamePredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = web_app.load_validated_data()
        cls.jcds_competitions = {
            entry["competition_name"]
            for entry in web_app.load_series_catalog(cls.data)
            if entry["series_slug"] == "jcds"
        }
        cls.season_players = [
            player
            for player in _prediction_season_players(
                cls.data, SEED_COMPETITION, SEED_SEASON
            )
            if player["team_name"]
        ]
        cls.season_teams = _prediction_season_teams(
            cls.data, SEED_COMPETITION, SEED_SEASON
        )
        cls.season_team_names = [
            str(team.get("name") or "").strip()
            for team in cls.season_teams
            if str(team.get("name") or "").strip()
        ]
        if len(cls.season_players) < 12 or not cls.season_team_names:
            raise AssertionError("三局预测测试需要至少12名赛季选手和1支赛季战队")
        team_lookup = {team["team_id"]: team for team in cls.data["teams"]}
        cls.roster = []
        for index, player in enumerate(cls.data["players"][:12], start=1):
            team_id = str(player.get("team_id") or "")
            cls.roster.append(
                {
                    "seat": index,
                    "player_id": player["player_id"],
                    "player_name": player.get("display_name") or player["player_id"],
                    "team_id": team_id,
                    "team_name": team_lookup.get(team_id, {}).get("name") or "未知战队",
                    "manual_total_override": None,
                }
            )

    def simulate(self, roster=None, simulations=1_000):
        return simulate_three_game_day(
            self.data,
            roster or self.roster,
            competition_name=SEED_COMPETITION,
            season_name="2026广州公开赛S2",
            played_on="2026-06-01",
            jcds_competitions=self.jcds_competitions,
            simulations=simulations,
        )

    def test_s1_golden_daily_totals_and_camp_results(self) -> None:
        seed_matches = [
            match
            for match in self.data["matches"]
            if match.get("competition_name") == SEED_COMPETITION
            and match.get("season") == SEED_SEASON
            and str(match.get("played_on") or "") <= SEED_END_DATE
            and match.get("winning_camp") in {"villagers", "werewolves"}
        ]
        self.assertEqual(len(seed_matches), 114)
        camp_counts = Counter(match["winning_camp"] for match in seed_matches)
        self.assertEqual(camp_counts["werewolves"], 75)
        self.assertEqual(camp_counts["villagers"], 39)

        daily_totals = defaultdict(float)
        for match in seed_matches:
            for participant in match.get("players", []):
                player_id = str(participant.get("player_id") or "")
                if not player_id or player_id.upper() == "NPC":
                    continue
                daily_totals[(match["played_on"], player_id)] += score_without_adjustment(participant)
        totals = list(daily_totals.values())
        self.assertEqual(len(totals), 480)
        self.assertAlmostEqual(sum(totals) / len(totals), 7.65625, places=5)
        self.assertEqual(
            [
                sum(value < 0 for value in totals),
                sum(value < 5 for value in totals),
                sum(value < 10 for value in totals),
                sum(value > 10 for value in totals),
                sum(value > 15 for value in totals),
                sum(value > 18 for value in totals),
            ],
            [37, 142, 299, 166, 45, 9],
        )

    def test_role_assignment_is_always_four_four_four(self) -> None:
        rng = random.Random(20260804)
        for _ in range(100):
            assignment = draw_role_assignment(rng)
            self.assertEqual(Counter(assignment), {"wolf": 4, "god": 4, "civilian": 4})

    def test_fixed_input_is_fully_reproducible(self) -> None:
        first = self.simulate(simulations=500)
        second = self.simulate(simulations=500)
        self.assertEqual(first, second)

    def test_manual_total_correction_does_not_change_win_probabilities(self) -> None:
        baseline = self.simulate(simulations=800)
        adjusted_roster = [dict(row) for row in self.roster]
        adjusted_roster[0]["manual_total_override"] = 2.0
        adjusted = self.simulate(adjusted_roster, simulations=800)
        baseline_by_id = {item["player_id"]: item for item in baseline["predictions"]}
        adjusted_by_id = {item["player_id"]: item for item in adjusted["predictions"]}
        target_id = adjusted_roster[0]["player_id"]
        self.assertEqual(
            baseline_by_id[target_id]["game_win_probabilities"],
            adjusted_by_id[target_id]["game_win_probabilities"],
        )
        self.assertAlmostEqual(
            float(adjusted_by_id[target_id]["expected_total"])
            - float(baseline_by_id[target_id]["expected_total"]),
            2.0,
            places=2,
        )
        for player_id in baseline_by_id:
            if player_id == target_id:
                continue
            self.assertEqual(
                baseline_by_id[player_id]["expected_total"],
                adjusted_by_id[player_id]["expected_total"],
            )

    def test_probability_ranges_and_conservation(self) -> None:
        payload = self.simulate(simulations=1_000)
        for item in payload["predictions"]:
            self.assertTrue(all(0 <= value <= 1 for value in item["game_win_probabilities"]))
            win_probabilities = item["win_count_probabilities"]
            self.assertAlmostEqual(sum(entry["probability"] for entry in win_probabilities), 1.0, places=3)
            market_by_key = {market["key"]: market for market in item["market_probabilities"]}
            for market in market_by_key.values():
                self.assertGreaterEqual(market["probability"], 0)
                self.assertLessEqual(market["probability"], 1)
                self.assertGreaterEqual(market["equality_probability"], 0)
                self.assertLessEqual(market["equality_probability"], 1)
            self.assertAlmostEqual(
                market_by_key["lt_10"]["probability"]
                + market_by_key["gt_10"]["probability"]
                + market_by_key["lt_10"]["equality_probability"],
                1.0,
                places=3,
            )

    def test_unknown_profiles_fall_back_to_population_prior(self) -> None:
        roster = [
            {
                "seat": index,
                "scenario_player_id": f"scenario-{index}",
                "player_id": "",
                "player_name": f"陌生选手{index}",
                "team_id": "",
                "team_name": f"陌生战队{index}",
                "manual_total_override": None,
            }
            for index in range(1, 13)
        ]
        payload = self.simulate(roster, simulations=300)
        self.assertTrue(all(item["model_source"] == "population_prior" for item in payload["predictions"]))
        self.assertTrue(all(not item["profile_href"] for item in payload["predictions"]))

    def test_history_excludes_prediction_day_and_future_results(self) -> None:
        baseline = build_history_model(
            self.data,
            competition_name=SEED_COMPETITION,
            prediction_date="2026-06-01",
            jcds_competitions=self.jcds_competitions,
        )
        data_with_future = deepcopy(self.data)
        future_match = deepcopy(
            next(match for match in self.data["matches"] if match.get("players"))
        )
        future_match["match_id"] = "future-prediction-leak-check"
        future_match["played_on"] = "2026-06-01"
        future_match["winning_camp"] = "werewolves"
        for participant in future_match["players"]:
            participant["points_earned"] = 999
            participant["adjustment_points"] = 0
        data_with_future["matches"].append(future_match)
        after = build_history_model(
            data_with_future,
            competition_name=SEED_COMPETITION,
            prediction_date="2026-06-01",
            jcds_competitions=self.jcds_competitions,
        )
        self.assertEqual(baseline["history_match_count"], after["history_match_count"])
        self.assertEqual(baseline["wolf_prior"], after["wolf_prior"])
        self.assertEqual(baseline["seed_market_hit_counts"], after["seed_market_hit_counts"])

    def test_scenario_normalization_keeps_metadata_separate(self) -> None:
        scenario = normalize_prediction_day_scenario(
            {
                "competition_name": SEED_COMPETITION,
                "season_name": "2026广州公开赛S2",
                "played_on": "2026-08-04",
                "published": True,
                "roster": self.roster,
            }
        )
        self.assertIsNotNone(scenario)
        self.assertEqual(len(scenario["roster"]), 12)
        self.assertNotIn("matches", scenario)

    def test_season_player_candidates_merge_scope_sources_and_skip_npc(self) -> None:
        data = {
            "players": [
                {"player_id": "member", "display_name": "成员选手", "team_id": "team-s1"},
                {"player_id": "match-only", "display_name": "比赛选手", "team_id": ""},
                {"player_id": "dimension-only", "display_name": "维度选手", "team_id": ""},
                {"player_id": "other-season", "display_name": "其他赛季", "team_id": "team-s2"},
                {"player_id": "nPc", "display_name": "机器账号", "team_id": "team-s1"},
            ],
            "teams": [
                {
                    "team_id": "team-s1",
                    "name": "S1战队",
                    "competition_name": "测试赛事",
                    "season_name": "S1",
                    "members": ["member", "nPc"],
                },
                {
                    "team_id": "team-s2",
                    "name": "S2战队",
                    "competition_name": "测试赛事",
                    "season_name": "S2",
                    "members": ["other-season"],
                },
            ],
            "matches": [
                {
                    "match_id": "scope-match",
                    "competition_name": "测试赛事",
                    "season": "S1",
                    "played_on": "2026-08-01",
                    "round": 1,
                    "game_no": 1,
                    "players": [
                        {
                            "player_id": "match-only",
                            "player_name": "比赛选手",
                            "team_id": "team-s1",
                        },
                        {"player_id": "NPC", "player_name": "npc", "team_id": "team-s1"},
                    ],
                }
            ],
            "season_player_dimension_stats": [
                {
                    "competition_name": "测试赛事",
                    "season_name": "S1",
                    "played_on": "2026-08-02",
                    "player_id": "dimension-only",
                    "team_id": "team-s1",
                    "seat": 1,
                }
            ],
        }
        candidates = _prediction_season_players(data, "测试赛事", "S1")
        self.assertEqual(
            {item["player_id"] for item in candidates},
            {"member", "match-only", "dimension-only"},
        )
        self.assertTrue(all(item["team_name"] == "S1战队" for item in candidates))

    def test_admin_html_only_embeds_selected_season_choices(self) -> None:
        data = deepcopy(self.data)
        data["teams"].append(
            {
                "team_id": "other-season-team",
                "name": "其他赛季战队",
                "short_name": "其他",
                "logo": "",
                "competition_name": SEED_COMPETITION,
                "season_name": "其他赛季",
                "members": ["other-season-player"],
            }
        )
        data["players"].append(
            {
                "player_id": "other-season-player",
                "display_name": "只属于其他赛季的选手",
                "team_id": "other-season-team",
                "photo": "",
            }
        )
        ctx = web_app.RequestContext(
            method="GET",
            path="/prediction-admin",
            query={
                "scenario_competition": [SEED_COMPETITION],
                "scenario_season": [SEED_SEASON],
                "scenario_date": ["2026-08-04"],
            },
            form={},
            files={},
            current_user={"username": "admin", "role": "admin"},
            now_label="2026-08-04 12:00:00 中国时间",
        )
        with patch(
            "web.features.match_page.load_prediction_day_scenarios", return_value={}
        ):
            html = _prediction_day_scenario_admin_html(ctx, data)
        self.assertIn(self.season_players[0]["player_id"], html)
        self.assertIn('name="scenario_player_id_12"', html)
        self.assertNotIn("只属于其他赛季的选手", html)
        self.assertNotIn("其他赛季战队", html)
        self.assertIn("临时选手", html)

    def test_admin_html_resolves_legacy_unique_name_to_profile_id(self) -> None:
        player = next(
            candidate
            for candidate in self.season_players
            if sum(
                other["player_name"].casefold() == candidate["player_name"].casefold()
                for other in self.season_players
            )
            == 1
        )
        played_on = "2026-08-04"
        scenario = normalize_prediction_day_scenario(
            {
                "competition_name": SEED_COMPETITION,
                "season_name": SEED_SEASON,
                "played_on": played_on,
                "roster": [
                    {
                        "player_name": player["player_name"],
                        "team_name": player["team_name"],
                    }
                ],
            }
        )
        key = prediction_day_scenario_key(SEED_COMPETITION, SEED_SEASON, played_on)
        ctx = web_app.RequestContext(
            method="GET",
            path="/prediction-admin",
            query={
                "scenario_competition": [SEED_COMPETITION],
                "scenario_season": [SEED_SEASON],
                "scenario_date": [played_on],
            },
            form={},
            files={},
            current_user={"username": "admin", "role": "admin"},
            now_label="2026-08-04 12:00:00 中国时间",
        )
        with patch(
            "web.features.match_page.load_prediction_day_scenarios",
            return_value={key: scenario},
        ):
            html = _prediction_day_scenario_admin_html(ctx, self.data)
        self.assertIn(
            f'id="scenario-player-id-1" value="{player["player_id"]}"',
            html,
        )
        self.assertIn(f"赛季档案 · {player['team_name']} · {player['player_id']}", html)

    def scenario_context(
        self,
        *,
        duplicate: bool = False,
        override: str = "",
        formal_players: list[dict[str, str]] | None = None,
    ):
        match_id = str(self.data["matches"][0].get("match_id") or "")
        form = {
            "scenario_competition": [SEED_COMPETITION],
            "scenario_season": [SEED_SEASON],
            "scenario_date": ["2026-08-04"],
            "match_id": [match_id],
        }
        for index in range(1, 13):
            formal_player = formal_players[index - 1] if formal_players else None
            form[f"scenario_player_id_{index}"] = [
                formal_player["player_id"] if formal_player else ""
            ]
            form[f"scenario_player_{index}"] = [
                formal_player["player_name"]
                if formal_player
                else ("重复选手" if duplicate else f"发布选手{index}")
            ]
            form[f"scenario_team_{index}"] = [
                formal_player["team_name"]
                if formal_player
                else self.season_team_names[(index - 1) % len(self.season_team_names)]
            ]
            form[f"scenario_override_{index}"] = [override if index == 1 else ""]
        return web_app.RequestContext(
            method="POST",
            path="/prediction-admin",
            query={
                "scenario_competition": [SEED_COMPETITION],
                "scenario_season": [SEED_SEASON],
                "scenario_date": ["2026-08-04"],
            },
            form=form,
            files={},
            current_user={"username": "admin", "display_name": "管理员", "role": "admin"},
            now_label="2026-08-04 12:00:00 中国时间",
        )

    def same_name_profile_fixture(
        self,
    ) -> tuple[dict, list[dict[str, str]]]:
        data = deepcopy(self.data)
        team_ids = [str(team.get("team_id") or "") for team in self.season_teams[:2]]
        self.assertEqual(len(team_ids), 2)
        duplicate_ids = ["test-same-name-profile-a", "test-same-name-profile-b"]
        for player_id, team_id in zip(duplicate_ids, team_ids):
            data["players"].append(
                {
                    "player_id": player_id,
                    "display_name": "同名测试选手",
                    "team_id": team_id,
                    "photo": "",
                }
            )
            team = next(
                item for item in data["teams"] if item.get("team_id") == team_id
            )
            team.setdefault("members", []).append(player_id)
        candidates = _prediction_season_players(
            data, SEED_COMPETITION, SEED_SEASON
        )
        duplicates = [
            player for player in candidates if player["player_id"] in duplicate_ids
        ]
        selected_ids = set(duplicate_ids)
        duplicates.extend(
            player
            for player in candidates
            if player["player_id"] not in selected_ids
            and player["player_name"] != "同名测试选手"
        )
        return data, duplicates[:12]

    def test_admin_publish_rejects_duplicate_players(self) -> None:
        statuses = []
        with patch("web.features.match_page.load_prediction_day_scenarios", return_value={}), patch(
            "web.features.match_page.save_prediction_day_scenarios"
        ) as save_mock:
            _handle_prediction_day_scenario_admin(
                self.scenario_context(duplicate=True),
                lambda status, headers: statuses.append(status),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(statuses[0], "400 Bad Request")
        save_mock.assert_not_called()

    def test_admin_publish_validates_half_point_correction(self) -> None:
        statuses = []
        with patch("web.features.match_page.load_prediction_day_scenarios", return_value={}), patch(
            "web.features.match_page.save_prediction_day_scenarios"
        ) as save_mock:
            _handle_prediction_day_scenario_admin(
                self.scenario_context(override="1.2"),
                lambda status, headers: statuses.append(status),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(statuses[0], "400 Bad Request")
        save_mock.assert_not_called()

    def test_admin_publish_saves_one_version_for_scope_and_date(self) -> None:
        responses = []
        captured = {}

        def capture(payload):
            captured.update(payload)

        with patch("web.features.match_page.load_prediction_day_scenarios", return_value={}), patch(
            "web.features.match_page.save_prediction_day_scenarios", side_effect=capture
        ), patch("web.features.match_page.legacy.audit_action"):
            _handle_prediction_day_scenario_admin(
                self.scenario_context(override="1.5"),
                lambda status, headers: responses.append((status, dict(headers))),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(responses[0][0], "302 Found")
        location = responses[0][1]["Location"]
        self.assertTrue(location.startswith("/prediction-admin?"))
        self.assertIn("scenario_date=2026-08-04", location)
        self.assertIn("match_id=", location)
        self.assertEqual(len(captured), 1)
        scenario = next(iter(captured.values()))
        self.assertTrue(scenario["published"])
        self.assertEqual(len(scenario["roster"]), 12)
        self.assertEqual(scenario["roster"][0]["manual_total_override"], 1.5)

    def test_admin_publish_uses_selected_season_profile_identity(self) -> None:
        responses = []
        captured = {}
        ctx = self.scenario_context(formal_players=self.season_players[:12])
        ctx.form["scenario_player_1"] = ["被篡改的姓名"]
        ctx.form["scenario_team_1"] = ["被篡改的战队"]

        with patch(
            "web.features.match_page.load_prediction_day_scenarios", return_value={}
        ), patch(
            "web.features.match_page.save_prediction_day_scenarios",
            side_effect=lambda payload: captured.update(payload),
        ), patch("web.features.match_page.legacy.audit_action"):
            _handle_prediction_day_scenario_admin(
                ctx,
                lambda status, headers: responses.append(status),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(responses[0], "302 Found")
        roster = next(iter(captured.values()))["roster"]
        self.assertEqual(roster[0]["player_id"], self.season_players[0]["player_id"])
        self.assertEqual(roster[0]["player_name"], self.season_players[0]["player_name"])
        self.assertEqual(roster[0]["team_name"], self.season_players[0]["team_name"])

    def test_admin_publish_allows_distinct_same_name_profiles_by_id(self) -> None:
        data, selected = self.same_name_profile_fixture()
        responses = []
        captured = {}
        with patch(
            "web.features.match_page.load_prediction_day_scenarios", return_value={}
        ), patch(
            "web.features.match_page.save_prediction_day_scenarios",
            side_effect=lambda payload: captured.update(payload),
        ), patch("web.features.match_page.legacy.audit_action"):
            _handle_prediction_day_scenario_admin(
                self.scenario_context(formal_players=selected),
                lambda status, headers: responses.append(status),
                data,
                "save_day_scenario",
            )
        self.assertEqual(responses[0], "302 Found")
        roster = next(iter(captured.values()))["roster"]
        self.assertEqual(
            {roster[0]["player_id"], roster[1]["player_id"]},
            {"test-same-name-profile-a", "test-same-name-profile-b"},
        )

    def test_admin_publish_rejects_ambiguous_name_without_profile_id(self) -> None:
        data, selected = self.same_name_profile_fixture()
        selected = selected[:1] + selected[2:12]
        selected.append(
            next(
                player
                for player in self.season_players
                if player["player_id"] not in {row["player_id"] for row in selected}
            )
        )
        ctx = self.scenario_context(formal_players=selected)
        ctx.form["scenario_player_id_1"] = [""]
        statuses = []
        with patch(
            "web.features.match_page.load_prediction_day_scenarios", return_value={}
        ), patch("web.features.match_page.save_prediction_day_scenarios") as save_mock:
            _handle_prediction_day_scenario_admin(
                ctx,
                lambda status, headers: statuses.append(status),
                data,
                "save_day_scenario",
            )
        self.assertEqual(statuses[0], "400 Bad Request")
        save_mock.assert_not_called()

    def test_admin_publish_rejects_cross_season_profile_and_team(self) -> None:
        profile_ctx = self.scenario_context(formal_players=self.season_players[:12])
        profile_ctx.form["scenario_player_id_1"] = ["not-in-selected-season"]
        team_ctx = self.scenario_context()
        team_ctx.form["scenario_team_1"] = ["其他赛季战队"]
        for ctx in (profile_ctx, team_ctx):
            statuses = []
            with patch(
                "web.features.match_page.load_prediction_day_scenarios", return_value={}
            ), patch("web.features.match_page.save_prediction_day_scenarios") as save_mock:
                _handle_prediction_day_scenario_admin(
                    ctx,
                    lambda status, headers: statuses.append(status),
                    self.data,
                    "save_day_scenario",
                )
            self.assertEqual(statuses[0], "400 Bad Request")
            save_mock.assert_not_called()

    def test_admin_publish_rejects_npc_case_insensitively(self) -> None:
        ctx = self.scenario_context()
        ctx.form["scenario_player_1"] = ["nPc"]
        statuses = []
        with patch(
            "web.features.match_page.load_prediction_day_scenarios", return_value={}
        ), patch("web.features.match_page.save_prediction_day_scenarios") as save_mock:
            _handle_prediction_day_scenario_admin(
                ctx,
                lambda status, headers: statuses.append(status),
                self.data,
                "save_day_scenario",
            )
        self.assertEqual(statuses[0], "400 Bad Request")
        save_mock.assert_not_called()

    def test_admin_match_switch_updates_three_game_input_scope(self) -> None:
        match = self.data["matches"][0]
        ctx = web_app.RequestContext(
            method="GET",
            path="/prediction-admin",
            query={"match_id": [str(match.get("match_id") or "")]},
            form={},
            files={},
            current_user={"username": "admin", "role": "admin"},
            now_label="2026-08-04 12:00:00 中国时间",
        )
        _, competition_name, _, season_name, played_on = _prediction_day_scope(ctx, self.data)
        self.assertEqual(competition_name, str(match.get("competition_name") or ""))
        self.assertEqual(season_name, str(match.get("season") or ""))
        self.assertEqual(played_on, str(match.get("played_on") or ""))

    def test_admin_defaults_to_first_status_sorted_season(self) -> None:
        ctx = web_app.RequestContext(
            method="GET",
            path="/prediction-admin",
            query={},
            form={},
            files={},
            current_user={"username": "admin", "role": "admin"},
            now_label="2026-08-04 12:00:00 中国时间",
        )
        with patch(
            "web.features.match_page.legacy.load_series_catalog",
            return_value=[
                {"competition_name": "测试赛事", "series_slug": "jcds"}
            ],
        ), patch(
            "web.features.match_page.legacy.list_seasons",
            return_value=["进行中赛季", "未开始赛季", "待排期赛季", "已结束赛季"],
        ):
            _, competition_name, seasons, season_name, _ = _prediction_day_scope(
                ctx, {"matches": []}
            )
        self.assertEqual(competition_name, "测试赛事")
        self.assertEqual(seasons[0], "进行中赛季")
        self.assertEqual(season_name, "进行中赛季")

    def test_predictions_api_prefers_published_scenario_and_keeps_legacy_fields(self) -> None:
        roster = [
            {
                "seat": index,
                "scenario_player_id": f"scenario-api-{index}",
                "player_id": "",
                "player_name": f"接口选手{index}",
                "team_id": "",
                "team_name": f"接口战队{index}",
                "manual_total_override": None,
            }
            for index in range(1, 13)
        ]
        played_on = "2026-08-04"
        scenario = normalize_prediction_day_scenario(
            {
                "competition_name": SEED_COMPETITION,
                "season_name": SEED_SEASON,
                "played_on": played_on,
                "published": True,
                "roster": roster,
            }
        )
        key = prediction_day_scenario_key(SEED_COMPETITION, SEED_SEASON, played_on)
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/predictions",
            query={
                "competition": [SEED_COMPETITION],
                "season": [SEED_SEASON],
                "played_on": [played_on],
            },
            form={},
            files={},
            current_user=None,
            now_label="2026-08-04 12:00:00 中国时间",
        )
        with patch(
            "web.features.match_page.load_prediction_day_scenarios",
            return_value={key: scenario},
        ):
            payload = web_app.build_predictions_api_base_payload(ctx)
        self.assertEqual(payload["roster_source"], "published_scenario")
        self.assertEqual(payload["model_metadata"]["version"], "jcds_three_game_v1")
        self.assertEqual(len(payload["predictions"]), 12)
        for term in ("盘口", "赔率", "下注", "投注", "走水", "通杀"):
            self.assertNotIn(term, payload["notice"])
        item = payload["predictions"][0]
        for field in (
            "player_id",
            "player_name",
            "team_name",
            "expected_points",
            "expected_total",
            "game_win_probabilities",
            "expected_wins",
            "win_count_probabilities",
            "market_probabilities",
            "manual_override_applied",
        ):
            self.assertIn(field, item)
        self.assertEqual(len(item["game_win_probabilities"]), 3)
        self.assertEqual(len(item["market_probabilities"]), 6)

    def test_prediction_day_share_scene_is_deterministic_and_compact(self) -> None:
        first = web_app.build_prediction_day_share_scene(
            SEED_COMPETITION, SEED_SEASON, "2026-08-04"
        )
        second = web_app.build_prediction_day_share_scene(
            SEED_COMPETITION, SEED_SEASON, "2026-08-04"
        )
        self.assertEqual(first, second)
        self.assertRegex(first, r"^d1:[0-9a-f]{24}$")
        self.assertLessEqual(len(first), 32)
        with self.assertRaises(ValueError):
            web_app.build_prediction_day_share_scene(
                SEED_COMPETITION, SEED_SEASON, "2026-02-30"
            )

    def test_prediction_day_schedule_requires_same_twelve_players_three_times(self) -> None:
        matches = [
            {
                "players": [
                    {"player_id": f"player-{index}"}
                    for index in range(1, 13)
                ]
            }
            for _ in range(3)
        ]
        self.assertTrue(web_app.prediction_day_schedule_is_complete(matches))
        matches[2]["players"][-1]["player_id"] = "replacement"
        self.assertFalse(web_app.prediction_day_schedule_is_complete(matches))

    def test_prediction_day_share_target_supports_published_scenario(self) -> None:
        played_on = "2026-08-04"
        scenario = normalize_prediction_day_scenario(
            {
                "competition_name": SEED_COMPETITION,
                "season_name": SEED_SEASON,
                "played_on": played_on,
                "published": True,
                "roster": self.roster,
            }
        )
        key = prediction_day_scenario_key(SEED_COMPETITION, SEED_SEASON, played_on)
        with patch(
            "web.features.match_page.load_prediction_day_scenarios",
            return_value={key: scenario},
        ):
            targets = web_app.list_prediction_day_share_targets(self.data)
            target = next(
                item
                for item in targets
                if item["competition"] == SEED_COMPETITION
                and item["season"] == SEED_SEASON
                and item["played_on"] == played_on
            )
            resolved = web_app.resolve_prediction_day_share_scene(
                target["scene"], self.data
            )
        self.assertEqual(resolved["competition"], SEED_COMPETITION)
        self.assertEqual(resolved["played_on"], played_on)
        self.assertTrue(resolved["series"])

    def test_prediction_day_share_entry_returns_exact_scope_and_day(self) -> None:
        scene = web_app.build_prediction_day_share_scene(
            SEED_COMPETITION, SEED_SEASON, "2026-08-04"
        )
        target = {
            "scene": scene,
            "competition": SEED_COMPETITION,
            "season": SEED_SEASON,
            "played_on": "2026-08-04",
            "region": "广州",
            "series": "jcds",
            "seriesName": "京城大师赛",
        }
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/miniprogram/share-entry",
            query={"scene": [scene]},
            form={},
            files={},
            current_user=None,
            now_label="2026-08-04 12:00:00 中国时间",
        )
        statuses = []
        with patch(
            "web_app.resolve_prediction_day_share_scene", return_value=target
        ):
            body = b"".join(
                web_app.handle_miniprogram_share_entry(
                    ctx, lambda status, headers: statuses.append(status)
                )
            )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(statuses, ["200 OK"])
        self.assertEqual(payload["target"], "prediction_day")
        self.assertEqual(payload["played_on"], "2026-08-04")
        self.assertEqual(payload["scope"]["series"], "jcds")

    def test_prediction_day_share_scene_rejects_digest_collision(self) -> None:
        scene = web_app.build_prediction_day_share_scene(
            SEED_COMPETITION, SEED_SEASON, "2026-08-04"
        )
        first = {"scene": scene, "competition": "赛事甲"}
        second = {"scene": scene, "competition": "赛事乙"}
        with patch(
            "web_app.list_prediction_day_share_targets",
            return_value=[first, second],
        ):
            self.assertIsNone(web_app.resolve_prediction_day_share_scene(scene, {}))

    def test_existing_player_share_entry_remains_compatible(self) -> None:
        player_ids_with_matches = {
            str(participant.get("player_id") or "")
            for match in self.data["matches"]
            for participant in match.get("players", [])
            if str(participant.get("player_id") or "")
        }
        player_id = next(
            player["player_id"]
            for player in self.data["players"]
            if player["player_id"] in player_ids_with_matches
        )
        ctx = web_app.RequestContext(
            method="GET",
            path="/api/miniprogram/share-entry",
            query={"scene": [f"p:{player_id}"]},
            form={},
            files={},
            current_user=None,
            now_label="2026-08-04 12:00:00 中国时间",
        )
        statuses = []
        body = b"".join(
            web_app.handle_miniprogram_share_entry(
                ctx, lambda status, headers: statuses.append(status)
            )
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(statuses, ["200 OK"])
        self.assertEqual(payload["player_id"], player_id)
        self.assertNotIn("target", payload)

    def test_prediction_and_player_share_codes_use_separate_cache_entries(self) -> None:
        played_on = "2026-08-04"
        prediction_scene = web_app.build_prediction_day_share_scene(
            SEED_COMPETITION, SEED_SEASON, played_on
        )
        target = {
            "scene": prediction_scene,
            "competition": SEED_COMPETITION,
            "season": SEED_SEASON,
            "played_on": played_on,
            "region": "广州",
            "series": "jcds",
            "seriesName": "京城大师赛",
        }
        prediction_ctx = web_app.RequestContext(
            method="GET",
            path="/api/miniprogram/share-code",
            query={
                "share_type": ["prediction_day"],
                "competition": [SEED_COMPETITION],
                "season": [SEED_SEASON],
                "played_on": [played_on],
            },
            form={},
            files={},
            current_user=None,
            now_label="2026-08-04 12:00:00 中国时间",
        )
        player_id = self.data["players"][0]["player_id"]
        player_ctx = web_app.RequestContext(
            method="GET",
            path="/api/miniprogram/share-code",
            query={"player_id": [player_id]},
            form={},
            files={},
            current_user=None,
            now_label="2026-08-04 12:00:00 中国时间",
        )
        fake_png = b"\x89PNG\r\n\x1a\nshare-code"
        web_app.WECHAT_MINIPROGRAM_SHARE_CODE_CACHE.clear()
        statuses = []
        try:
            with patch("web_app.load_validated_data", return_value=self.data), patch(
                "web_app.list_prediction_day_share_targets", return_value=[target]
            ), patch(
                "web_app.request_wechat_miniprogram_share_code",
                return_value=(fake_png, "image/png"),
            ) as request_mock:
                for ctx in (prediction_ctx, prediction_ctx, player_ctx, player_ctx):
                    body = b"".join(
                        web_app.handle_miniprogram_share_code(
                            ctx, lambda status, headers: statuses.append(status)
                        )
                    )
                    self.assertEqual(body, fake_png)
            self.assertEqual(request_mock.call_count, 2)
            requested_scenes = {call.args[0] for call in request_mock.call_args_list}
            self.assertEqual(
                requested_scenes, {prediction_scene, f"p:{player_id}"}
            )
            self.assertEqual(statuses, ["200 OK"] * 4)
        finally:
            web_app.WECHAT_MINIPROGRAM_SHARE_CODE_CACHE.clear()


if __name__ == "__main__":
    unittest.main()
    build_history_model,
